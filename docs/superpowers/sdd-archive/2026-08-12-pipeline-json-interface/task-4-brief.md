### Task 4: `pipeline/provenance.py` — input hashes, preview provenance, review_revision

**Files:**
- Create: `pipeline/provenance.py`
- Test: `tests/test_provenance.py`

**Interfaces:**
- Consumes: `recipe.load/fingerprint`, `render.style_hashes/seed_hash`, `toolchain.entries_for/RENDER_TOOLS`, `driver._lock`/`driver._lab` equivalents (re-implement locally to avoid importing driver: read `config/toolchain.lock` and `labprofile.load("generic-v1")`).
- Produces:
  - `style_input_hash(stem, style, rec, material=None) -> str` — sha256 of the canonical JSON of `{"raw": rec["raw_sha256"], "style": material["style_hashes"][style], "seed": material["seed_hash"], "render_tools": toolchain.entries_for(material["lock"], toolchain.RENDER_TOOLS), "overrides": rec["overrides"]}` (compact, sorted keys; `material=None` → `gather_material(stem)`). This is exactly the material that determines preview pixels — which requires (Task 5) that targeted previews actually render with the denoise extra profile when `overrides["denoise"]` is set, and verify the RAW hash, or the hash certifies inputs that weren't used.
  - `content_hash(path) -> str|None` — sha256 of file bytes, `None` if missing. **No caching**: a mtime/size cache would let a same-size, restored-mtime replacement return a stale hash, defeating the spec's same-mtime guarantee (§4.2). Preview hashing is ~24 MB per status call (~25 ms) — cheap at human refresh rates.
  - `gather_material(stem) -> dict` — reads `render.style_hashes(stem)`, `render.seed_hash()`, the toolchain lock, the lab profile, **and each style's preview content hash** once, returning `{"style_hashes", "seed_hash", "lock", "lab", "preview_hashes"}`; every function below accepts an optional `material=` and, when given, performs **zero additional file reads** — `approve_review` and `status` derive revision, staleness, and fingerprint from exactly one snapshot (the single-snapshot rule; re-reading previews inside `stale_styles`/`review_revision` would reopen the check-vs-persist window).
  - `record_preview(rec, stem, style, preview_path, inputs_hash) -> None` — sets `rec.setdefault("previews", {})[style] = {"inputs": inputs_hash, "content": content_hash(preview_path)}` (caller saves the recipe). **`inputs_hash` is computed by the caller BEFORE rendering starts** (Task 5) — recording a post-render hash would certify inputs edited during the render.
  - `stale_styles(stem, rec, material=None) -> list[str]` — styles where recorded `inputs` ≠ current `style_input_hash` OR recorded `content` ≠ current preview file hash OR no provenance recorded. Sorted.
  - `review_revision(stem, rec, material=None) -> str` — `"sha256:" + sha256(json({"fp": recipe.fingerprint(stem, rec, material["style_hashes"], material["seed_hash"], material["lock"], material["lab"]), "previews": {style: content_hash(previews_dir()/f"{stem}_{style}_preview.jpg") for style in paths.STYLES}}))` — reuses the fingerprint's canonical blob so `status` and `approve` cannot drift.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_provenance.py
import json

import pytest

from pipeline import paths, provenance, recipe


@pytest.fixture
def seeded(tmp_repo, monkeypatch):
    from pipeline import render, toolchain
    for s in paths.STYLES:
        (tmp_repo / "config/styles" / f"{s}.pp3").write_text(f"# {s}\n")
    (tmp_repo / "config/toolchain.lock").write_text(json.dumps(
        {"rawtherapee-cli": {"version": "5.12"}}))
    import pathlib, shutil as _sh
    _REPO = pathlib.Path(__file__).resolve().parent.parent
    _sh.copy2(_REPO / "config/lab-profiles/generic-v1.yaml",
              tmp_repo / "config/lab-profiles/generic-v1.yaml")
    monkeypatch.setattr(toolchain, "entries_for", lambda lock, names: {})
    rec = recipe.new("P1", "aa" * 32, 5776, 4336)
    recipe.save("P1", rec)
    return rec


def _fake_preview(tmp_repo, style, data=b"jpgbytes"):
    p = tmp_repo / "previews" / f"P1_{style}_preview.jpg"
    p.write_bytes(data)
    return p


def _record(rec, style, p):
    provenance.record_preview(
        rec, "P1", style, p, provenance.style_input_hash("P1", style, rec))


def test_record_and_no_stale(seeded, tmp_repo):
    rec = recipe.load("P1")
    for style in paths.STYLES:
        _record(rec, style, _fake_preview(tmp_repo, style))
    recipe.save("P1", rec)
    assert provenance.stale_styles("P1", recipe.load("P1")) == []


def test_same_size_restored_mtime_swap_is_stale(seeded, tmp_repo):
    import os
    rec = recipe.load("P1")
    p = _fake_preview(tmp_repo, "natural", b"AAAAAAAA")
    for style in paths.STYLES:
        _record(rec, style, _fake_preview(tmp_repo, style)
                if style != "natural" else p)
    recipe.save("P1", rec)
    st = p.stat()
    p.write_bytes(b"BBBBBBBB")                       # same size
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))  # restored mtime
    assert "natural" in provenance.stale_styles("P1", recipe.load("P1"))


def test_missing_provenance_is_stale(seeded):
    assert provenance.stale_styles("P1", recipe.load("P1")) == sorted(paths.STYLES)


def test_swapped_preview_content_is_stale(seeded, tmp_repo):
    rec = recipe.load("P1")
    p = _fake_preview(tmp_repo, "natural")
    _record(rec, "natural", p)
    for style in paths.STYLES:
        if style != "natural":
            _record(rec, style, _fake_preview(tmp_repo, style))
    recipe.save("P1", rec)
    p.write_bytes(b"different pixels")            # swap the JPG, inputs unchanged
    assert "natural" in provenance.stale_styles("P1", recipe.load("P1"))


def test_input_change_is_stale(seeded, tmp_repo):
    rec = recipe.load("P1")
    for style in paths.STYLES:
        _record(rec, style, _fake_preview(tmp_repo, style))
    recipe.save("P1", rec)
    (tmp_repo / "sidecars" / "P1_natural.pp3").write_text(
        "[Exposure]\nCompensation=0.3\n")        # moves style_hashes → inputs
    assert "natural" in provenance.stale_styles("P1", recipe.load("P1"))


def test_review_revision_moves_on_sidecar_and_preview_change(seeded, tmp_repo):
    rec = recipe.load("P1")
    r1 = provenance.review_revision("P1", rec)
    (tmp_repo / "sidecars" / "P1_bw.pp3").write_text("[Exposure]\nCompensation=0.2\n")
    r2 = provenance.review_revision("P1", recipe.load("P1"))
    assert r1 != r2
    _fake_preview(tmp_repo, "bw", b"new")
    r3 = provenance.review_revision("P1", recipe.load("P1"))
    assert r3 != r2
    assert r3.startswith("sha256:")
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_provenance.py -q` → FAIL.

- [ ] **Step 3: Implement `pipeline/provenance.py`**

```python
import hashlib
import json
from pathlib import Path

from . import labprofile, paths, recipe, render, toolchain

_LAB_PROFILE = "generic-v1"


def gather_material(stem):
    return {
        "style_hashes": render.style_hashes(stem),
        "seed_hash": render.seed_hash(),
        "lock": json.loads((paths.config_dir() / "toolchain.lock").read_text()),
        "lab": labprofile.load(_LAB_PROFILE),
        "preview_hashes": {style: content_hash(_preview_path(stem, style))
                           for style in paths.STYLES},
    }


def _canonical_sha(obj):
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def style_input_hash(stem, style, rec, material=None):
    material = material or gather_material(stem)
    return _canonical_sha({
        "raw": rec["raw_sha256"],
        "style": material["style_hashes"][style],
        "seed": material["seed_hash"],
        "render_tools": toolchain.entries_for(material["lock"],
                                              toolchain.RENDER_TOOLS),
        "overrides": rec["overrides"],
    })


def content_hash(path):
    # Deliberately uncached: a size+mtime cache would let a same-size,
    # restored-mtime swap return a stale hash (spec §4.2 forbids exactly that).
    path = Path(path)
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def _preview_path(stem, style):
    return paths.previews_dir() / f"{stem}_{style}_preview.jpg"


def record_preview(rec, stem, style, preview_path, inputs_hash):
    rec.setdefault("previews", {})[style] = {
        "inputs": inputs_hash,
        "content": content_hash(preview_path),
    }


def stale_styles(stem, rec, material=None):
    material = material or gather_material(stem)
    stored = rec.get("previews") or {}
    stale = []
    for style in paths.STYLES:
        entry = stored.get(style)
        if (entry is None
                or entry.get("inputs") != style_input_hash(stem, style, rec,
                                                           material)
                or entry.get("content") != material["preview_hashes"][style]):
            stale.append(style)
    return sorted(stale)


def review_revision(stem, rec, material=None):
    material = material or gather_material(stem)
    fp = recipe.fingerprint(stem, rec, material["style_hashes"],
                            material["seed_hash"], material["lock"],
                            material["lab"])
    return "sha256:" + _canonical_sha({"fp": fp,
                                       "previews": material["preview_hashes"]})
```

Note: `fingerprint` requires `rec["previews"]`-free material only — it reads named keys, so the new optional `previews`/`app_adjustments`/`delivery_id` keys never enter the fingerprint. Do not add them to `recipe.fingerprint`.

- [ ] **Step 4: Run to verify pass** — `.venv/bin/python -m pytest tests/test_provenance.py -q` → PASS.

- [ ] **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/provenance.py tests/test_provenance.py
git commit -m "feat(pipeline): preview provenance + review_revision"
```

---

