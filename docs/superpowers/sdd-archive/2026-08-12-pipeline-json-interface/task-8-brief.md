### Task 8: Dispatch-level locking + `--json` on existing commands

**Files:**
- Modify: `pipeline/__main__.py` (all subcommands), `pipeline/subject.py` (add `group_bbox_detail`)
- Test: `tests/test_cli.py` (additions), `tests/test_subject.py` (addition)

**Interfaces:**
- Produces:
  - Every mutating subcommand (`ingest`, `preview`, `croppreview`, `approve`, `render`, `verify`) wrapped in `publish.acquire_lock()` at dispatch. **`run` is NOT wrapped** (process_all locks internally — Global Constraints). `status` and (Task 9's) `crops` never lock.
  - `--json` flag on `ingest`, `preview`, `approve`, `run` (results wired in their own tasks; this task wires `preview --json` → `{"stem", "style", "preview", "temperature", "exposure", "review_revision_before", "review_revision_after"}` via the same result builder as `adjust` (shared helper `adjust.preview_result(stem, style, revision_before)`) — factor the result dict out of `adjust.apply` into `adjust.preview_result` when implementing).
  - `subject.group_bbox_detail(image_path) -> tuple[dict|None, str]` returning `(bbox, "faces")`, `(None, "no_faces")`, or `(None, "detector_error")`; `group_bbox` becomes a thin wrapper returning only the bbox (existing callers unaffected).
- Legacy stdout guard: without `--json`, `ingest`/`preview`/`approve`/`run`/`status` print exactly what they print today.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli.py additions
import json
import subprocess
import sys


def _run(args, cwd=None, env=None):
    return subprocess.run([sys.executable, "-m", "pipeline", *args],
                          capture_output=True, text=True, env=env)


def test_mutating_command_reports_lock_held(tmp_repo, monkeypatch):
    import os
    (tmp_repo / "run").mkdir(exist_ok=True)
    (tmp_repo / "run/driver.lock").write_text(str(os.getpid()))  # live PID
    env = dict(os.environ, PIPELINE_ROOT=str(tmp_repo))
    p = _run(["ingest", "--json"], env=env)
    assert p.returncode == 1
    env_line = json.loads(p.stdout.strip().splitlines()[-1])
    assert env_line["error"]["code"] == "LOCK_HELD"


def test_status_never_locks(tmp_repo, monkeypatch):
    import os
    (tmp_repo / "run").mkdir(exist_ok=True)
    (tmp_repo / "run/driver.lock").write_text(str(os.getpid()))
    env = dict(os.environ, PIPELINE_ROOT=str(tmp_repo))
    p = _run(["status"], env=env)
    assert p.returncode == 0        # legacy status works while lock held


def test_legacy_status_output_unchanged(tmp_repo):
    import os
    env = dict(os.environ, PIPELINE_ROOT=str(tmp_repo))
    p = _run(["status"], env=env)
    assert p.returncode == 0
    assert p.stdout == "photos: none ingested\n"
```

```python
# tests/test_subject.py addition
def test_group_bbox_is_thin_wrapper_over_detail(monkeypatch):
    from pipeline import subject
    sentinel = {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}
    monkeypatch.setattr(subject, "group_bbox_detail",
                        lambda path: (sentinel, "faces"))
    assert subject.group_bbox("whatever.jpg") is sentinel
    monkeypatch.setattr(subject, "group_bbox_detail",
                        lambda path: (None, "detector_error"))
    assert subject.group_bbox("whatever.jpg") is None
```

(Additionally refactor the existing Vision tests in `tests/test_subject.py` — keep their skipif markers — to call `group_bbox_detail` and assert the basis string alongside the bbox: `"faces"` when a bbox is returned, `"no_faces"` for the zero-face image.)

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_cli.py -q` → FAIL (`--json` unknown argument).

- [ ] **Step 3: Implement**

Rewrite `pipeline/__main__.py` dispatch so each subcommand declares `mutating=True/False` and optional `--json`; a single helper runs the body:

```python
def _dispatch(ns, fn, mutating):
    from . import ingest, jsonio, publish, render

    def body():
        if mutating:
            with publish.acquire_lock():
                return fn(ns)
        return fn(ns)

    if getattr(ns, "json", False):
        return jsonio.run_json(
            lambda: body() or {},
            adapters={render.RenderError: "RENDER_FAILED",
                      ingest.IngestError: "BAD_INPUT",
                      FileNotFoundError: "NOT_FOUND"})
    return _wrap(lambda _ns: body())(ns)
```

The `run --json` handler (Task 12) additionally catches the toolchain-drift `RuntimeError` raised by `process_all` (message starts `"toolchain drift"`) and re-raises `jsonio.CommandError("TOOLCHAIN_FAILED", str(e))`; verify failures inside a collected run surface per-stem as `VERIFY_FAILED` entries in `result.failed`, not as exceptions.

Mutating set: ingest, preview, croppreview, approve, render, verify, adjust. Non-mutating: status, crops. `run`: dispatched WITHOUT the lock wrapper (its `fn` calls `process_all`, which locks). Keep every legacy handler body identical so no-flag output is unchanged. **`verify --json` gets its own JSON body** (never the legacy `_verify`, which raises `SystemExit` — a `BaseException` that `run_json` deliberately does not catch, so it would exit with no envelope): call `driver.verify_photo(stem)` directly; problems → `raise jsonio.CommandError("VERIFY_FAILED", "; ".join(problems))`, clean → `{"stem": stem, "verify": "clean"}`. Add a CLI test asserting `verify --json` on a failing photo exits 1 with a `VERIFY_FAILED` envelope as the last stdout line.

`pipeline/subject.py`: rename the body of `group_bbox` to `group_bbox_detail`, returning `(bbox, "faces")` on detection, `(None, "no_faces")` for zero faces, `(None, "detector_error")` in the existing exception paths; re-implement `group_bbox` as `return group_bbox_detail(image_path)[0]`.

- [ ] **Step 4: Run to verify pass** — `.venv/bin/python -m pytest tests/test_cli.py tests/test_subject.py -q` → PASS.

- [ ] **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/__main__.py pipeline/subject.py tests/test_cli.py tests/test_subject.py
git commit -m "feat(pipeline): dispatch-level locking + --json plumbing + group_bbox_detail"
```

---

