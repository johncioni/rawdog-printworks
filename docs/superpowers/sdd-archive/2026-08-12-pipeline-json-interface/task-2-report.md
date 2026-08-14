# Task 2 report: atomic state writes + side-effect-free status read

## What I built

**`pipeline/recipe.py`**
- Added `os` and `tempfile` imports.
- `save(stem, data)` — unchanged signature; body is now write-temp + `os.replace`
  in the recipe's own directory (`tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.")`),
  with `except BaseException: os.unlink(tmp); raise` cleanup.

**`pipeline/manifest.py`**
- Added `os` and `tempfile` imports.
- `save(m)` — same atomic pattern, temp created in `paths.root()`, replaced onto
  `paths.manifest_path()`.
- `rebuild(persist=True)` — signature gained `persist`; the trailing `save(m)` is
  now guarded by `if persist:`. Default keeps existing behavior exactly.
- `load_readonly()` — new. Mirrors `load()` except the recovery branch calls
  `rebuild(persist=False)`, so it never writes a repo file.

**Tests** — 3 added verbatim from the brief:
- `tests/test_manifest.py::test_load_readonly_never_writes_manifest`
- `tests/test_manifest.py::test_save_is_atomic_no_partial_file_on_same_name`
- `tests/test_recipe.py::test_recipe_save_atomic_leaves_no_temp`

No existing test was modified. No existing production behavior changed:
`load()` still calls `rebuild()` with persistence intact, so the manifest-recovery
write happens exactly as before.

## Deviations

1. **Manifest temp prefix is `f"{p.name}."`, not the brief's `f".{p.name}."`.**
   `paths.manifest_path().name` is already `".manifest"`, so the brief's prose
   prefix produces temps named `..manifest.*`. The brief's own verbatim test asserts
   no leftovers `startswith(".manifest.")` — with a `..manifest.*` name that
   assertion could never fire, making the test vacuous. Using `f"{p.name}."`
   yields `.manifest.XXXX`, which is what the test actually pins.
   `recipe.py` keeps the brief's `f".{p.name}."` unchanged: the recipe test asserts
   an exact directory listing, so it catches a leftover under any name. (Recipe
   temps also cannot be mistaken for recipes — `glob("*.yaml")` does not match
   `.P1.yaml.XXXX`.)

2. **No `git add` / `git commit` (brief Step 5).** The task assignment says the
   controller commits; I ran no git commands.

3. **`pipeline/__main__.py` untouched — handoff note.** `_status()` still calls
   `manifest.load()`, so the CLI `status` command retains today's byte-for-byte
   behavior including its manifest-rebuild write. `load_readonly()` is the
   primitive that removes that side effect; **Task 6 (status --json snapshot) must
   rewire `_status()` to `manifest.load_readonly()`** to satisfy the global
   "status is side-effect-free" constraint. It is not fixed by this task alone.

## Test evidence

Baseline before any change:

```
$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/ -q
178 passed in 15.81s
```

Step 2 — new tests fail as expected:

```
$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/test_manifest.py tests/test_recipe.py -q
>       m = manifest.load_readonly()
E       AttributeError: module 'pipeline.manifest' has no attribute 'load_readonly'
tests/test_manifest.py:180: AttributeError
FAILED tests/test_manifest.py::test_load_readonly_never_writes_manifest
1 failed, 31 passed in 0.38s
```

(The two atomicity tests passed pre-change, as the brief anticipated; they pin the
property rather than drive it.)

Step 4 — targeted pass:

```
$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/test_manifest.py tests/test_recipe.py -q
32 passed in 0.33s
```

Step 5 — full gate:

```
$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/ -q
181 passed in 13.97s
```

178 -> 181, exactly the 3 added tests, zero regressions.

## Self-review

Beyond the suite, I ran an out-of-band script (scratchpad, not committed) against a
throwaway `PIPELINE_ROOT` to check the properties the unit tests only partly reach:

- `load()` still writes `.manifest` on the recovery branch: **True** (unchanged behavior).
- A serialization failure mid-write (`json.dumps` raising `TypeError`,
  `yaml.safe_dump` raising `RepresenterError`): both `save`s propagate the error,
  the **previous file is left byte-identical**, and no temp survives — root
  contained only `.manifest`, recipes dir only `P1.yaml`.
- `load_readonly()` returns a dict equal to `load()`'s for the same repo state.

Other review points considered:

- `load_readonly` is defined above `rebuild`; resolution is at call time, so ordering
  is fine.
- Kept the brief's `os.unlink(tmp)` without `missing_ok` and added no `fsync`. The
  unlink-masks-error edge case is unreachable: `os.replace` is the last statement in
  the `try`, so any exception reaching the handler happened while the temp still
  existed. Durability beyond `os.replace` was not in scope.
- Both temps are created in the same directory as their target, so `os.replace` is a
  same-filesystem rename and therefore atomic.
- **File-mode change, accepted:** `tempfile.mkstemp` creates at 0600, whereas the old
  `write_text` created at umask (typically 0644), so a newly created `.manifest` or
  recipe YAML is now owner-only. Overwrites of an existing file inherit the temp's
  0600 too, since `os.replace` carries the temp's mode. This is inherent to the
  pattern the brief mandates, affects no CLI output or test, and the repo is
  single-user local state — flagging it rather than deviating.
