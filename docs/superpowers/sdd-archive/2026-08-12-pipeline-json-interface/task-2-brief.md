### Task 2: Atomic state writes + side-effect-free status read

**Files:**
- Modify: `pipeline/recipe.py:33-36` (`save`), `pipeline/manifest.py:15-27` (`load`/`save`), `pipeline/manifest.py:113-132` (`rebuild`)
- Test: `tests/test_manifest.py`, `tests/test_recipe.py` (additions)

**Interfaces:**
- Produces:
  - `recipe.save(stem, data)` — unchanged signature, now write-temp + `os.replace` in the same directory.
  - `manifest.save(m)` — same, atomic.
  - `manifest.rebuild(persist=True)` — existing behavior when `persist=True` (default); `persist=False` computes and returns the manifest **without writing**.
  - `manifest.load_readonly()` — like `load()` but uses `rebuild(persist=False)` in the recovery branch; never writes.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_manifest.py` and `tests/test_recipe.py`)

```python
# tests/test_manifest.py additions
def test_load_readonly_never_writes_manifest(tmp_repo):
    from pipeline import manifest, paths, recipe
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))
    assert not paths.manifest_path().exists()
    m = manifest.load_readonly()
    assert "P1" in m["photos"]
    assert not paths.manifest_path().exists()          # the point


def test_save_is_atomic_no_partial_file_on_same_name(tmp_repo):
    from pipeline import manifest, paths
    manifest.save({"photos": {}})
    # os.replace leaves no sibling temp files behind
    leftovers = [p for p in paths.root().iterdir()
                 if p.name.startswith(".manifest.") ]
    assert leftovers == []
```

```python
# tests/test_recipe.py additions
def test_recipe_save_atomic_leaves_no_temp(tmp_repo):
    from pipeline import paths, recipe
    recipe.save("P1", recipe.new("P1", "aa" * 32, 100, 80))
    assert (paths.recipes_dir() / "P1.yaml").exists()
    assert [p.name for p in paths.recipes_dir().iterdir()] == ["P1.yaml"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_manifest.py tests/test_recipe.py -q`
Expected: FAIL — `load_readonly` missing (the atomic tests may pass trivially before the change; that's fine, they pin the property).

- [ ] **Step 3: Implement**

In `pipeline/recipe.py` replace `save` body:

```python
import os, tempfile  # add to imports

def save(stem, data):
    p = _path(stem)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(yaml.safe_dump(data, sort_keys=True))
        os.replace(tmp, p)
    except BaseException:
        os.unlink(tmp)
        raise
```

In `pipeline/manifest.py`: same pattern for `save(m)` (temp in `paths.root()`, prefix `f".{p.name}."`, `os.replace`); change `rebuild()` signature to `rebuild(persist=True)` and guard the final `save(m)` with `if persist:`; add:

```python
def load_readonly():
    p = paths.manifest_path()
    if p.exists():
        return json.loads(p.read_text())
    if any(paths.recipes_dir().glob("*.yaml")):
        return rebuild(persist=False)
    return {"photos": {}}
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_manifest.py tests/test_recipe.py -q` — PASS.

- [ ] **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/recipe.py pipeline/manifest.py tests/test_manifest.py tests/test_recipe.py
git commit -m "feat(pipeline): atomic recipe/manifest writes + read-only manifest path"
```

---

