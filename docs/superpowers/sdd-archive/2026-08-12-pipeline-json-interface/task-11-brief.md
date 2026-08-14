### Task 11: `ingest --from` / `--delivery-id`

**Files:**
- Modify: `pipeline/ingest.py` (`run` signature, new `stage_sources`), `pipeline/recipe.py:14-26` (`new` gains optional metadata), `pipeline/__main__.py` (`ingest` flags + JSON result)
- Test: `tests/test_ingest.py` (additions)

**Interfaces:**
- Produces:
  - `recipe.new(stem, raw_sha256, width, height, delivery_id=None, ingested_at=None)` — the two new keys are set **only when not None** (flag-less ingest produces byte-identical legacy recipes).
  - `ingest.stage_sources(sources: list[Path]) -> dict` — for each source file (recursing one level into dropped directories, case-insensitive `.rw2` filter): copy to `Input/.staging-<uuid4hex>/<name>`, hash the **temp** (never the live source), then decide: hash in `_archived_hashes()` or an already-staged/`Input/` file with same hash → `skipped` (`"duplicate content"`); same stem exists in `Input/` or manifest with different hash → `conflicts` (`"stem exists with different content"`), staged copy deleted; otherwise `os.replace` temp into `Input/`. Unreadable source → `failed` entry `{"file", "code": "BAD_INPUT", "message"}`. Returns `{"placed": [names], "skipped": [...], "conflicts": [...], "failed": [...]}`; always removes the staging dir.
  - `ingest.run(delivery_id=None)` — existing behavior; when `delivery_id` is not None, passes `delivery_id` and `ingested_at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")` into `recipe.new`.
  - JSON result for the command (built in `__main__.py` from `stage_sources` + `run` outputs): `{"ingested": [...], "skipped": [...], "conflicts": [...], "failed": [...]}`; non-empty `failed` → `CommandError("PARTIAL_FAILURE", f"{len(failed)} file(s) failed", result=result)`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_ingest.py`)

```python
def test_recipe_new_without_flags_is_legacy_bytes(tmp_repo):
    from pipeline import recipe
    legacy = recipe.new("P1", "aa" * 32, 100, 80)
    assert "delivery_id" not in legacy and "ingested_at" not in legacy
    tagged = recipe.new("P1", "aa" * 32, 100, 80,
                        delivery_id="u-1", ingested_at="2026-08-12T00:00:00Z")
    assert tagged["delivery_id"] == "u-1"


def test_stage_sources_hashes_temp_and_places(tmp_repo):
    from pipeline import ingest, paths
    src = tmp_repo / "elsewhere"; src.mkdir()
    f = src / "P9.RW2"; f.write_bytes(b"raw-bytes")
    result = ingest.stage_sources([f])
    assert result["placed"] == ["P9.RW2"]
    assert (paths.input_dir() / "P9.RW2").read_bytes() == b"raw-bytes"
    assert not any(p.name.startswith(".staging-")
                   for p in paths.input_dir().iterdir())


def test_stage_sources_conflict_and_duplicate(tmp_repo):
    from pipeline import ingest, paths
    (paths.input_dir() / "P9.RW2").write_bytes(b"original")
    src = tmp_repo / "elsewhere"; src.mkdir()
    # Same CONTENT under a new stem is still a content duplicate → skipped
    # (spec §4.2/§5.4: content-hash dedup), never placed.
    dup = src / "P8.RW2"; dup.write_bytes(b"original")
    clash = src / "P9.RW2"; clash.write_bytes(b"DIFFERENT") # same stem, new content → conflict
    result = ingest.stage_sources([dup, clash])
    assert result["placed"] == []
    assert result["skipped"][0]["file"] == "P8.RW2"
    assert result["conflicts"][0]["file"] == "P9.RW2"
    assert (paths.input_dir() / "P9.RW2").read_bytes() == b"original"
    assert not (paths.input_dir() / "P8.RW2").exists()


def test_stage_sources_hashes_the_staged_temp_not_the_live_source(
        tmp_repo, monkeypatch):
    from pathlib import Path
    from pipeline import ingest, paths
    src = tmp_repo / "elsewhere"; src.mkdir()
    f = src / "P9.RW2"; f.write_bytes(b"first-bytes")

    # Capture the ORIGINAL function before patching — patching the module
    # attribute and calling through the module would recurse.
    original_copy2 = ingest.shutil.copy2

    def mutating_copy(source, dest):
        original_copy2(source, dest)
        Path(source).write_bytes(b"MUTATED-AFTER-COPY")   # source changes mid-flight
    monkeypatch.setattr(ingest.shutil, "copy2", mutating_copy)

    result = ingest.stage_sources([f])
    # Decision and placement reflect the STAGED bytes; the mutated live
    # source never influences the outcome or lands in Input/.
    assert result["placed"] == ["P9.RW2"]
    assert (paths.input_dir() / "P9.RW2").read_bytes() == b"first-bytes"


def test_run_records_delivery_metadata_only_when_given(tmp_repo, monkeypatch):
    from pipeline import ingest, recipe
    monkeypatch.setattr(ingest, "exif_summary", lambda p: {
        "Make": "Panasonic", "Model": "DC-GH7", "ImageWidth": 5776,
        "ImageHeight": 4336, "Orientation": "Horizontal (normal)",
        "LensModel": "L", "ISO": 200, "ExposureTime": "1/100",
        "AspectRatio": "4:3"})
    (tmp_repo / "Input/P7.rw2").write_bytes(b"bytes-7")
    ingest.run(delivery_id="uuid-7")
    rec = recipe.load("P7")
    assert rec["delivery_id"] == "uuid-7"
    assert rec["ingested_at"].endswith("Z")
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_ingest.py -q` → FAIL.

- [ ] **Step 3: Implement**

`recipe.new`: add keyword-only params; after building the dict, `if delivery_id is not None: data["delivery_id"] = delivery_id` and same for `ingested_at`.

`ingest.stage_sources`:

```python
import uuid
import os


def _iter_sources(sources):
    for source in map(Path, sources):
        if source.is_dir():
            yield from (p for p in sorted(source.iterdir())
                        if p.is_file() and p.suffix.lower() == ".rw2")
        elif source.suffix.lower() == ".rw2":
            yield source


def stage_sources(sources):
    result = {"placed": [], "skipped": [], "conflicts": [], "failed": []}
    staging = paths.input_dir() / f".staging-{uuid.uuid4().hex}"
    staging.mkdir(parents=True)
    known_hashes = _archived_hashes()
    known_hashes |= {_sha256(p) for p in paths.input_dir().iterdir()
                     if p.is_file() and p.suffix.lower() == ".rw2"}
    manifest_stems = set(manifest.load()["photos"])
    input_stems = {p.stem for p in paths.input_dir().iterdir()
                   if p.is_file() and p.suffix.lower() == ".rw2"}
    try:
        for source in _iter_sources(sources):
            try:
                temp = staging / source.name
                shutil.copy2(source, temp)
                digest = _sha256(temp)           # hash the staged copy
            except OSError as error:
                result["failed"].append({"file": source.name,
                                         "code": "BAD_INPUT",
                                         "message": str(error)})
                continue
            if digest in known_hashes:
                temp.unlink()
                result["skipped"].append({"file": source.name,
                                          "reason": "duplicate content"})
                continue
            if source.stem in manifest_stems | input_stems:
                temp.unlink()
                result["conflicts"].append(
                    {"file": source.name,
                     "reason": "stem exists with different content"})
                continue
            os.replace(temp, paths.input_dir() / source.name)
            known_hashes.add(digest)
            input_stems.add(source.stem)
            result["placed"].append(source.name)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return result
```

`ingest.run(delivery_id=None)`: thread the two values into `recipe.save(stem, recipe.new(..., delivery_id=delivery_id, ingested_at=_now_utc() if delivery_id else None))` with `_now_utc()` as specified in Interfaces. `__main__.py`: `ingest` gains `--from` (`nargs="+"`), `--delivery-id`, `--json`; JSON handler composes `stage_sources` (when `--from`) + `run(delivery_id)` results into the contract shape, mapping `run()`'s `"ok"` entries to `ingested` and its `"failed: …"` strings into `failed` entries (`code: "BAD_INPUT"`); raises `PARTIAL_FAILURE` with attached result when `failed` non-empty. Legacy no-flag path calls `_ingest()` unchanged.

- [ ] **Step 4: Run to verify pass**, **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/ingest.py pipeline/recipe.py pipeline/__main__.py tests/test_ingest.py
git commit -m "feat(pipeline): ingest --from staged-copy ingest + delivery metadata"
```

---

