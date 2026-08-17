# RAWdog Printworks — Lab Profile Selection Design

**Date:** 2026-08-17
**Status:** Draft — §10 (published-version retention) OPEN, blocks approval
**Depends on:** `2026-08-11-raw-print-pipeline-design.md` (rev 8) — §"Lab profile
(versioned, configurable)" defines the profile schema and field classes this
extends. `2026-08-12-macos-app-design.md` — the app this adds a surface to.

## 1. Goal

Let the operator choose which print lab the pipeline exports for, instead of the
single hardcoded `generic-v1`. Ship a small set of researched profiles for real
labs, surface the choice in the macOS app, and make the cost of switching
visible before it is paid.

One active lab, repo-wide. Per-delivery and per-photo selection are explicitly
out of scope (§11).

## 2. What already exists

The mechanism is mostly built; it is wired to a constant.

- `pipeline/labprofile.py` loads a profile by name, validates that its thirteen
  fields are exactly the known set, and exposes `review_view` / `render_view`.
- `recipe.fingerprint` already folds `review_view(lab)` into the approval
  fingerprint, so review-class values are part of what an operator approves.
- `manifest.effective_state` (`manifest.py:67`) demotes any approved-or-later
  photo whose current fingerprint no longer matches the stored one. Both
  `status.py:53` and `driver.py:743` call it.

**Therefore backward transitions on a lab switch need no new code.** Changing
the active profile changes the fingerprint; the next `status` reports every
affected photo as `review_required`, with nothing persisted and no migration.

As of `5679791`, both consumers resolve the profile through
`labprofile.active()` — previously `driver.py` and `provenance.py` each
hardcoded the name independently, which could have made the approval
fingerprint and the artifact dependency hashes disagree about which lab was in
force.

## 3. Selection state

A committed `config/active-lab.yaml`:

```yaml
# The repo's active lab profile. Changing this re-enters review for every
# approved photo whose review-class fields differ from the outgoing profile.
profile: generic-v1
```

`labprofile.active()` resolves it:

- **File absent → `generic-v1`.** Every existing checkout and every existing
  fingerprint is unaffected until someone deliberately switches.
- **File malformed, or names a profile that does not exist → raise**, for every
  caller that needs a resolved profile. A silent fallback to `generic-v1` would
  render against a different lab than the file names, which is the failure this
  whole design exists to prevent. The repair tools are the deliberate exception
  below — they never resolve a profile, so they have nothing to guess at.
- **Resolved once per process.** Not for speed: so that an edit during a long
  `run` cannot make some photos use one lab and the rest another. `lab set`
  invalidates the memo after writing, or it would report the outgoing profile
  as active for the rest of its own invocation. Tests reset it too.

**The repair tools must survive a broken pointer.** `lab list` and `lab set`
are exactly what an operator reaches for when `active-lab.yaml` is malformed or
names a deleted profile, so they degrade gracefully: report the breakage, still
list the available profiles, still permit a `set` that fixes it. Only the
render and approve paths hard-fail, because those are the ones that must never
guess which lab they are building for.

It must be committed rather than stored in `.manifest`, which is gitignored;
this input feeds the approval fingerprint and has to travel with the repo.

## 4. Schema: the `meta` block

`load()` validates `set(p) - {"meta"}` against the thirteen known fields, making
`meta` the single permitted extra key:

```yaml
meta:
  source: https://…       # the lab's published prep guide
  checked: 2026-08-17     # when that page was read
  verified: false         # the operator has not confirmed it
```

`meta` is structurally incapable of affecting output. Every hash path filters
through a whitelist — `review_view` (fingerprint), `render_view` + an explicit
`ppi` (artifact dependencies, `manifest.py:108-111`) — and the published
`provenance.json` carries only `fingerprint`, `raw_sha256`, `toolchain` and
`artifacts` (`driver.py:612-617`). No code path hashes the raw profile dict.
§9 makes this a regression test rather than a claim.

`verified` is operator-owned. Every profile this project ships for a real lab
starts `false`; the operator sets it `true` after checking the lab's current
spec sheet. `generic-v1` is not a real lab and carries no `meta` block.

## 5. Which labs ship, and the sourcing rule

"Support all lab options" is not achievable as stated: there are hundreds of
labs, their specs change without notice, and an unverified profile that looks
authoritative is a liability. This ships **four to six commonly used labs**,
each researched at implementation time from that lab's own published prep
guide, plus a documented procedure for adding others.

**A profile ships only if every lab-determined field is sourced.** No inferred
values, no inherited placeholders standing in for a published figure.

The thirteen fields split on an axis orthogonal to the review/render/order
classes — those describe *invalidation*; this describes *authority*:

| Class | Fields |
|---|---|
| **Lab-determined** — must be sourced or the profile does not ship | `submission_format`, `color_space`, `ppi`, `embed_icc`, `max_file_bytes`, `filename_rules`, `bleed`, `safe_edge_percent`, `lab_color_correction` |
| **Operator policy** — carries the `generic-v1` value by definition | `jpeg_quality`, `checkout_crop_review`, `strip_metadata_beyond_allowlist`, `keep_capture_date` |

No lab publishes whether the operator wants capture dates preserved. Requiring
those four to be "sourced" would ship zero profiles; treating the lab-determined
nine as optional would ship guesses. The partition is the point.

If a lab publishes only some of its nine, that lab is omitted and the omission
is recorded in the implementation plan, not silently dropped.

## 6. Command surface

Three subcommands under `lab`, following the existing `--json` envelope
convention (`2026-08-12-macos-app-design.md` §4.2-4.3):

| Command | Lock | Effect |
|---|---|---|
| `lab list` | none | Every profile: name, `verified`, which is active |
| `lab show [<name>]` | none | Fields grouped by class; defaults to the active profile |
| `lab set <name> --dry-run` | none | Reports the switch's impact; writes nothing |
| `lab set <name>` | driver lock | Writes `config/active-lab.yaml` |

`--dry-run` computes each photo's fingerprint under the *candidate* profile and
reports which would demote. Pure computation, so the preview is exact rather
than estimated. **It takes no lock** — a lock would make choosing a lab block on
a running render, and it writes nothing. `manifest.save` is write-temp +
`os.replace` (`manifest.py:42-50`), so a lock-free read cannot tear.

It must also report **crops that would become invalid**. `geometry.validate_crop`
raises when a crop window would require upscaling at the target PPI
(`geometry.py:51`), and that raise happens at *approve* time. Without this, a
switch to a higher-PPI lab would demote a photo to `review_required` and only
then reveal it cannot be re-approved at all. Reporting demotions but not
un-approvable crops would understate the cost the command exists to state.

`lab set` **reports and proceeds**; it does not refuse when photos would demote.
Consistent with the m12 ruling on the long-running-subprocess watchdog: surface
the cost, let the operator decide.

`status --json` gains a top-level `lab` block — active name, `verified`, and the
review-class values. Additive, so existing consumers are unaffected; it becomes
a new golden contract fixture.

## 7. App surface

The picker is **not** part of the Settings sheet's save flow. Settings writes
the repo path and python path to `UserDefaults` — app-local preferences. A lab
change is repo state, takes the driver lock, and can demote photos; putting both
behind one "Save" would make that button do two categorically different things,
one of them destructive. It gets its own section and its own explicit action,
with a confirmation — the F1/F2 lesson from the fix round, where an unguarded
control reached a whole-repo mutation.

1. The picker populates from `lab list --json`. Unverified profiles are badged.
2. Selecting a candidate runs `lab set <name> --dry-run` and shows the result.
3. Confirmation names the real cost: how many photos return to review, plus an
   unverified warning where applicable.
4. On confirm, `lab set <name>`, then the app re-reads `status`. Demotions
   arrive through the existing state display.

The app computes no impact and holds no lab logic — it renders what Python
reports, which is what keeps this inside the app's global constraints (no
pipeline logic in Swift, no repo writes from Swift, argv-only invocation).

The lab action is gated by the same busy state as other mutating controls, so it
cannot be invoked while a command is in flight.

## 8. Published provenance

`provenance.json` currently records `fingerprint`, `raw_sha256`, `toolchain` and
`artifacts` — **not the lab**. With one hardcoded profile that was adequate;
with several it means a published version cannot say which lab it targeted.

Add a `lab` key: profile name plus its review and render views. Nothing hashes
provenance content (`status.py:45-48` reads only `artifacts`), so this changes
no fingerprint and forces no re-render. Sets published before this change lack
the key, and readers must treat it as optional.

## 9. Testing

Repo convention: every new test is demonstrated failing against deliberately
broken code before it is accepted.

- `active()` — absent file → `generic-v1`; valid file → the named profile;
  malformed file → raises; a named-but-missing profile → raises; the
  once-per-process memo resets between tests.
- **`meta` cannot change a fingerprint.** Load `generic-v1` with and without a
  `meta` block; assert `recipe.fingerprint` is byte-identical. This is the
  regression guard for §4's safety claim, and the reason `meta` is allowed in
  the schema at all.
- `lab set` writes the pointer and the affected photos report `review_required`
  on the next `status`; `--dry-run` leaves the pointer byte-identical **and**
  leaves the driver lock acquirable while it runs.
- `--dry-run` flags a crop that would fail `validate_crop` under the candidate
  PPI. Constructed from a crop window with real headroom at 300 PPI and none at
  the candidate's, so the test fails if only demotions are reported.
- A malformed `active-lab.yaml` and one naming a deleted profile both leave
  `lab list` and `lab set` usable, and both make `run` refuse.
- `lab set` leaves no stale memo: the active profile it reports after writing is
  the incoming one, not the outgoing one.
- Golden `--json` fixtures for `lab list`, `lab show`, `lab set`, and the new
  `status.lab` block.
- Every shipped profile loads and validates, parametrized over
  `config/lab-profiles/` — a typo in a shipped YAML fails in CI, not mid-order.
- `provenance.json` gains `lab`; a set published without the key still reads.
- Swift: decoding `status.lab`, including when it is absent.

## 10. OPEN — published-version retention

**This blocks the spec. It is new scope discovered during review, not a detail.**

Publication retains exactly one version, enforced twice: `publish.publish`
rmtrees every non-current version after swapping the symlink
(`publish.py:150-152`), and `publish.recover()` does the same at the start of
every `run` (`publish.py:258-261`). The operator therefore cannot preserve an
old version by hand — recovery reaps it on the next run.

With one hardcoded lab this was harmless: a re-render produced equivalent
output. With lab switching it is not. `v001` is the record of the files
physically submitted to lab A; switching to lab B and re-rendering deletes it,
along with the `provenance.json` that §8 teaches to name its lab. The design
gains the ability to say which lab a version targeted and simultaneously
guarantees that record is destroyed on the next switch.

Three ways forward:

- **(a) Documented out-of-scope.** Retention stays at one version; the operator
  copies a submission set elsewhere before switching labs. Cheapest, and puts a
  data-loss footgun behind a documentation line.
- **(b) Lab-aware retention.** Do not prune a version whose provenance `lab`
  differs from the incoming publish's. Cheap *because* §8 adds `lab` to
  provenance — but `publish.recover()`'s pruning rule must be taught the same
  exception, or it reaps what publish preserved.
- **(c) Retain N versions.** Simplest to state, least targeted; unbounded growth
  at ~150 MB per version.

Recommendation: **(b)**, because it retains exactly what has a distinct
submission history and nothing else, and the information it needs is already
being added. But it modifies the atomic-publication subsystem and its recovery
path, which is load-bearing — so it is the operator's call, not the spec's.

Whichever is chosen, `publish.publish` and `publish.recover` must agree; a
divergence between them is how a preserved version silently disappears.

## 11. Out of scope

- **Per-delivery and per-photo lab selection.** One active lab, repo-wide.
- **Rendering for several labs from one approval.** Would add a lab dimension to
  `Output/`; a different design.
- **Editing profiles from inside the app.** Profiles are committed repo state,
  authored as YAML and reviewed in a diff like every other durable input.
- **Automatic re-approval after a switch.** Backward transitions are the
  designed behaviour; approval is a human act.
- **Verifying a lab's spec on the operator's behalf.** `verified` is set by the
  operator, never by this project.

## 12. Risk

Every shipped profile is a transcription of a third-party page that can change
without notice, and its values determine physical prints. `verified: false` is a
mitigation, not a fix: it makes the trust level legible, it does not make the
numbers right. The app warns before a switch to an unverified profile, and this
document records that no profile shipped by this project has been checked
against a real order.
