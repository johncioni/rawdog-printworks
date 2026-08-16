### Task 13: Golden contract fixtures + no-flag regression sweep

**Files:**
- Create: `tests/test_json_contract.py`, `tests/fixtures/json_contract/` (committed outputs)
- Test: itself

**Interfaces:**
- Consumes: everything above, via `pipeline.__main__.main([...])` in-process with `jsonio._real_stdout` monkeypatched to a buffer.
- Produces: committed fixtures — each file is the **normalized final envelope only** (one JSON object): `status_empty.json`, `status_ingested.json`, `adjust_ok.json`, `crops_suggested.json`, `approve_stale_review.json`, `ingest_result.json`, `run_partial_failure.json`, `envelope_lock_held.json`; plus `adjust_stream.ndjson` — the full normalized NDJSON line list (events + envelope) from the adjust scenario, for Plan 2's streaming-parser tests. Plan 2's XCTest decodes the `.json` files as envelopes and the `.ndjson` file line-by-line.
- JSON-mode state hygiene: `jsonio` keeps module state (`_out`, redirected `sys.stdout`); the test module uses an autouse fixture that saves/restores `sys.stdout` and resets `jsonio._out = None` around every scenario, or back-to-back in-process `main()` calls bleed into each other.
- Scenario definitions (exact; each seeds a fresh `tmp_repo` with the styles/lock/lab-profile pattern from `tests/test_status.py`, monkeypatched `toolchain.verify → []`, `toolchain.entries_for → {}`, and a fake `driver.preview_photo` writing deterministic bytes):
  1. `status_empty` — no photos; `main(["status", "--json"])`.
  2. `status_ingested` — one recipe (fixed bytes `b"raw-bytes"`, delivery fields set), manifest state `ingested`, previews recorded via the fake; `main(["status", "--json"])`.
  3. `adjust_ok` + `adjust_stream` — same repo; `main(["adjust", "--stem", "P1", "--style", "natural", "--temperature", "5600", "--json"])`; envelope → `adjust_ok.json`, full captured line list → `adjust_stream.ndjson`.
  4. `crops_suggested` — recipe with recorded dims, no persisted crops, `subject.group_bbox_detail` monkeypatched to a fixed bbox; `main(["crops", "--stem", "P1", "--json"])`.
  5. `approve_stale_review` — review-file with `expected_review_revision: "sha256:wrong"`; `main(["approve", "--stem", "P1", "--review-file", path, "--json"])`.
  6. `ingest_result` — one placeable source + one stem conflict via `--from`; `main(["ingest", "--from", src1, src2, "--delivery-id", "fixture-uuid", "--json"])`.
  7. `run_partial_failure` — two approved stems, `verify_photo` monkeypatched to fail for one; `main(["run", "--json"])`.
  8. `envelope_lock_held` — lock file held by a live PID (`os.getpid()`); `main(["ingest", "--json"])`.
- Normalization (deterministic fixtures): replace the tmp repo path with `<REPO>`, every 64-hex sha with `<SHA256>`, every `sha256:…` revision with `<REVISION>`, RFC 3339 timestamps with `<TIMESTAMP>`. The normalizer lives in the test module and is applied before compare/write.
- Regen mode: `REGEN_CONTRACT_FIXTURES=1 .venv/bin/python -m pytest tests/test_json_contract.py` rewrites the fixtures; default mode compares and fails on drift.

- [ ] **Step 1: Write the test module** — one test per scenario from the Interfaces list, each: seed per the scenario definition → run `main([...])` in-process with `jsonio._real_stdout` monkeypatched to a buffer → normalize → `assert normalized == fixture_path.read_text()` (or write when `REGEN_CONTRACT_FIXTURES=1`, then still assert). Include two legacy-output guards: `main(["status"])` stdout equals `"photos: none ingested\n"` exactly, and `main(["ingest"])` on an empty `Input/` equals today's output exactly (capture today's format before implementing by running the command). Module skeleton (the harness is fixed; each remaining scenario reuses `run_scenario` with its own seeding per the Interfaces table):

```python
# tests/test_json_contract.py
import io
import json
import os
import re
import sys
from pathlib import Path

import pytest

from pipeline import jsonio
from pipeline.__main__ import main

FIXTURES = Path(__file__).parent / "fixtures" / "json_contract"
REGEN = os.environ.get("REGEN_CONTRACT_FIXTURES") == "1"


@pytest.fixture(autouse=True)
def _json_mode_hygiene(monkeypatch):
    # jsonio keeps module state; in-process back-to-back main() calls bleed
    # without this. Restores sys.stdout and resets the saved NDJSON stream.
    saved = sys.stdout
    monkeypatch.setattr(jsonio, "_out", None)
    yield
    sys.stdout = saved


def normalize(text, repo):
    text = text.replace(str(repo), "<REPO>")
    text = re.sub(r"sha256:[0-9a-f]{64}", "<REVISION>", text)
    text = re.sub(r"\b[0-9a-f]{64}\b", "<SHA256>", text)
    text = re.sub(r"\d{4}-\d{2}-\d{2}T[0-9:.+\-]+Z?", "<TIMESTAMP>", text)
    return text


def run_scenario(monkeypatch, repo, argv, fixture_name):
    buf = io.StringIO()
    monkeypatch.setattr(jsonio, "_real_stdout", lambda: buf)
    exit_code = main(argv)
    output = normalize(buf.getvalue(), repo)
    path = FIXTURES / fixture_name
    if REGEN:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output)
    assert output == path.read_text()
    return exit_code, output


def test_status_empty(tmp_repo, monkeypatch, _seed_minimal):
    exit_code, output = run_scenario(
        monkeypatch, tmp_repo, ["status", "--json"], "status_empty.json")
    assert exit_code == 0
    envelope = json.loads(output.strip().splitlines()[-1])
    assert envelope["ok"] is True

# …one test per remaining scenario (Interfaces list #2-#8), each seeding
# exactly what its table row names, then calling run_scenario. The
# adjust scenario writes TWO fixtures: envelope line → adjust_ok.json,
# the full captured NDJSON → adjust_stream.ndjson.
```

`_seed_minimal` is a small local fixture applying the styles/lock/lab-profile seeding pattern (copy the real lab profile; monkeypatch `toolchain.verify → []`, `toolchain.entries_for → {}`).

- [ ] **Step 2: Generate fixtures** — `REGEN_CONTRACT_FIXTURES=1 .venv/bin/python -m pytest tests/test_json_contract.py -q` then inspect each file by eye against spec §4.3.

- [ ] **Step 3: Run in compare mode** — `.venv/bin/python -m pytest tests/test_json_contract.py -q` → PASS.

- [ ] **Step 4: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add tests/test_json_contract.py tests/fixtures/json_contract/
git commit -m "test(pipeline): golden JSON contract fixtures + legacy output guards"
```

---

## Review-round decisions (covers this plan AND `2026-08-12-printworks-app.md`)

Codex xhigh full review of both plans: 4 Critical, 14 Major, 1 Minor — all 19 applied (plans rev 2). Scoped verify of the fix diff: 10 PASS, 9 FAIL; all 9 closed in rev 3 (post-render input-equality check + valid RAW test fixtures; `gather_material` snapshots preview hashes so approve/status make zero re-reads; `remove_section_if_empty` on reset; validate-always + save-before-replace preview ordering; `basis: String?` in Swift + flagged spellings everywhere; `verify --json` typed body instead of `SystemExit`; runnable staged-source test; `adjust_stream.ndjson` consumed by a Plan 2 contract test; full `LineCollector` + pre-run terminationHandler; contract/smoke test harness skeletons).

Final scoped verify (rev 3.1 diff): #2, #8, #9, #11, #13 PASS; five residual textual items closed in rev 3.2 — status preview existence derived from the snapshot (not a fresh `exists()`); `remove_section_if_empty` preserves comment-bearing sections; `preview_photo`'s failure contract stated honestly (post-save/pre-replace window degrades to stale, never falsely fresh); `preview` handler resolves positional/flag args before use; smoke stub invoked via `executableOverride`. Loop closed — remaining defects have two further nets (each task's failing-test cycle and the per-task SDD reviewer).

Two findings were deliberately applied in **lighter form** than prescribed — judged for soundness, with accepted residuals:
- **#2 (immutable staged profile copies for preview renders):** applied as a pre/post input-hash equality gate instead — a preview is recorded only if its inputs hashed identically before AND after the render. Residual: an edit made and fully reverted *within one render* is undetectable; accepted for a single-user machine where every mutating command is lock-serialized (same risk class as the spec's §10 deferrals).
- **#18 (every contract/smoke test written out in full):** applied as complete harness code (fixtures, normalizer, stub layout) plus one fully-written scenario as the binding pattern, with the remaining scenarios exactly enumerated in the Interfaces tables. Residual: implementers transcribe the enumerated scenarios into the harness; each task's own reviewer gates the result.

## Self-Review (run after writing, before offering execution)

1. **Spec coverage:** §4.2 command table → Tasks 5–12; §4.3 contract → Tasks 1, 6, 13; atomic writes/status purity → Task 2; pp3/ownership → Tasks 3, 7; provenance/revision → Task 4; `group_bbox_detail` → Task 8; locking model → Tasks 7, 8 + Global Constraints. Spec §5–§7 (UI) and §8's Swift/XCTest halves are **Plan 2**.
2. **Placeholder scan:** none — every step carries runnable code or an exact mechanical instruction anchored to code shown in an earlier task.
3. **Type consistency:** `CommandError(code, message, result=None)` used in Tasks 7, 9, 10, 11, 12; `preview_photo(stem, style) -> Path` consumed in Tasks 7 (monkeypatched) and 5; `review_revision(stem, rec)` consumed in Tasks 6, 7, 10; `stage_sources` result keys match Task 11's CLI composition; `process_all(stems, force, collect)` matches Task 12's CLI call.
