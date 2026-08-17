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


def test_driver_and_provenance_resolve_one_active_profile(seeded, tmp_repo,
                                                          monkeypatch):
    # driver and provenance each used to hardcode their own profile name.
    # They feed different hashes — driver's goes into the approval
    # fingerprint, provenance's into artifact dependency hashes — so a
    # divergence would silently approve against one lab while invalidating
    # against another. There must be exactly one source.
    import yaml

    from pipeline import driver, labprofile
    profile = labprofile.load("generic-v1")
    profile["ppi"] = 360
    (tmp_repo / "config/lab-profiles/other-v1.yaml").write_text(
        yaml.safe_dump(profile))
    monkeypatch.setattr(labprofile, "active", lambda: "other-v1")

    assert driver._lab()["ppi"] == 360
    assert provenance.gather_material("P1")["lab"]["ppi"] == 360


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
