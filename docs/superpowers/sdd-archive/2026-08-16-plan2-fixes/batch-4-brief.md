# Batch 4 — CodeRabbit's findings on PR #6

Read `README.md` in this directory first; its scope contract still binds.

Batches 1–3 are committed (`f93ec85`, `964d708`, `852b0e5`) and open as PR #6,
which is green. CodeRabbit reviewed that PR and posted **two** findings. The user
has decided how far to take each. Two items only — do not expand.

## 1. Bound concurrent decodes in `PreviewImageCache` (Major, partial fix)

`PreviewImageCache.swift:59-72`.

**This is a regression batch 3 introduced, and that is why it is in scope.**
Before batch 3, the ImageIO decode ran inside the actor, so decodes were
serialized — an implicit concurrency bound of 1. Moving the decode to
`Task.detached` fixed the serialization but removed the bound: every distinct
`Key` now spawns its own detached decode, so a fast scroll through a large grid
can start many concurrent ImageIO decodes. Same-key sharing via `inFlight` is
correct and must be preserved.

**Do:** add a bound on how many decodes may run concurrently across different
keys. Choose the mechanism (an `AsyncSemaphore`-style gate, a small worker pool,
whatever fits the actor cleanly) and justify the limit you pick in your report —
it should exceed a typical visible-grid page so ordinary browsing never queues,
while capping a scroll storm.

**Do NOT** implement per-key waiter tracking or cancellation propagation. The
user explicitly deferred that half: `guard !Task.isCancelled` at `:72` already
discards the result for a cancelled caller, the detached decode continues
because the synchronous ImageIO decoder cannot observe cancellation, and a real
fix there is a design change to the cache. **File it, do not build it.**

While you are in this function, one thing CodeRabbit did not flag and you may
fix because it is two lines: `inFlight.removeValue(forKey: key)` at `:71` runs
for *every* waiter, so a caller arriving after the first waiter resumes starts a
duplicate detached decode for a key whose decode has just finished. Remove the
entry once, by the owner, not by every waiter. Say what you did.

Test the bound: N concurrent requests for N distinct keys, with the test-seam
decoder, must never exceed the limit in flight at once — and must all still
complete. This test has to fail against an unbounded implementation; that is
your RED.

## 2. Strengthen `SettingsStatusValidationTests` (Minor)

`SettingsStatusValidationTests.swift:5-20`.

The test asserts only `allowsSave`. If the transient classification regressed to
`.valid`, the test would still pass while the UI reported a healthy status —
**this is exactly the "test that cannot fail" class batch 2 existed to
eliminate, in a test written during this very fix round.** Treat it as such.

**Do:**
- Assert the full classification state for both cases, not just `allowsSave` —
  the transient case must be the transient state *and* allow Save; the invalid
  case must be the invalid state *and* block Save.
- Add the missing branch: an `INTERNAL` error whose message begins with
  `"could not launch:"` is a *configuration* failure and must block Save.

Two mutations required here, both demonstrated: classify the transient branch as
`.valid` (the state assertion must fail even though `allowsSave` would still
pass), and classify the launch-failure branch as transient.

## Out of scope

Everything in `README.md`'s out-of-scope list, unchanged. Also now explicitly
out: `PreviewImageCache` cancellation propagation and per-key waiter tracking
(item 1 above), which the user deferred deliberately.

## Gates and reporting

```bash
swift build --disable-sandbox --package-path app/PrintworksCore
swift test  --disable-sandbox --package-path app/PrintworksCore
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -configuration Release \
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build
.venv/bin/python -m pytest tests/ -q
```

Run `swift test` several times — item 1's test is concurrency-sensitive and one
green run does not prove it stable.

Write `batch-4-report.md` here, with mutation evidence per test. **Do not
commit.** Your report IS your checkpoint — and note that on batch 3 the stop
hook rewrote `HANDOFF.md` anyway and your report claimed it had not. Before you
finish, actually run `git status --short -- HANDOFF.md`; if it shows modified,
run `git checkout -- HANDOFF.md` and say so in the report.
