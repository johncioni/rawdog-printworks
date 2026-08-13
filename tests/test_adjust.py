import json

import pytest

from pipeline import adjust, jsonio, paths, pp3, recipe, toolchain


@pytest.fixture
def repo(tmp_repo, monkeypatch):
    from pipeline import driver
    for s in paths.STYLES:
        (tmp_repo / "config/styles" / f"{s}.pp3").write_text(f"# {s}\n")
    (tmp_repo / "config/toolchain.lock").write_text(json.dumps({}))
    import pathlib, shutil as _sh
    _REPO = pathlib.Path(__file__).resolve().parent.parent
    _sh.copy2(_REPO / "config/lab-profiles/generic-v1.yaml",
              tmp_repo / "config/lab-profiles/generic-v1.yaml")
    # labprofile.load validates the exact field set — always copy the real
    # profile; hand-written minimal YAML fails its schema check.
    monkeypatch.setattr(toolchain, "entries_for", lambda lock, names: {})
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))
    calls = []

    def fake_preview(stem, style):
        calls.append((stem, style))
        p = paths.previews_dir() / f"{stem}_{style}_preview.jpg"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(f"render-{len(calls)}".encode())
        return p
    monkeypatch.setattr(driver, "preview_photo", fake_preview)
    return calls


def test_adjust_writes_wb_bundle_and_ownership(repo):
    result = adjust.apply("P1", "natural", temperature=5600)
    side = pp3.Pp3.load(paths.sidecars_dir() / "P1_natural.pp3")
    assert side.get("White Balance", "Setting") == "Custom"
    assert side.get("White Balance", "Temperature") == "5600"
    assert side.get("White Balance", "Green") == "1.0"
    rec = recipe.load("P1")
    own = rec["app_adjustments"]["natural"]["wb"]
    assert own["previous"] == {"Setting": None, "Temperature": None,
                               "Green": None}
    assert own["last_written"] == {"Setting": "Custom", "Temperature": "5600",
                                   "Green": "1.0"}
    assert result["temperature"] == {"value": 5600, "source": "sidecar"}
    assert result["review_revision_before"] != result["review_revision_after"]


def test_adjust_preserves_hand_written_keys(repo):
    hand = paths.sidecars_dir() / "P1_bw.pp3"
    hand.write_text("# hand note\n[Exposure]\nCompensation=0.15\n"
                    "CurveMode=Standard\n")
    adjust.apply("P1", "bw", exposure=0.30)
    text = hand.read_text()
    assert "# hand note" in text and "CurveMode=Standard" in text
    assert "Compensation=0.3" in text
    own = recipe.load("P1")["app_adjustments"]["bw"]["exposure"]
    assert own["previous"] == {"Compensation": "0.15"}   # captured pre-app value


def test_reset_restores_previous_and_skips_diverged(repo):
    adjust.apply("P1", "natural", temperature=5600)
    adjust.apply("P1", "natural", reset=True)
    side = pp3.Pp3.load(paths.sidecars_dir() / "P1_natural.pp3")
    assert side.get("White Balance", "Temperature") is None   # restored to absent

    adjust.apply("P1", "vibrant", temperature=5600)
    # hand edit after app write → diverged
    p = paths.sidecars_dir() / "P1_vibrant.pp3"
    doc = pp3.Pp3.load(p); doc.set("White Balance", "Temperature", "4800")
    doc.write_atomic(p)
    adjust.apply("P1", "vibrant", reset=True)
    assert pp3.Pp3.load(p).get("White Balance", "Temperature") == "4800"
    # Ownership drop is PERSISTED even though the reset touched no sidecar
    assert "wb" not in recipe.load("P1")["app_adjustments"].get("vibrant", {})


def test_adjust_after_divergence_recaptures_previous(repo):
    # App writes, hand edits, app writes again: the new `previous` must be
    # the HAND-EDITED value, so a later reset restores the hand edit.
    adjust.apply("P1", "filmic", temperature=5600)
    p = paths.sidecars_dir() / "P1_filmic.pp3"
    doc = pp3.Pp3.load(p); doc.set("White Balance", "Temperature", "4800")
    doc.write_atomic(p)
    adjust.apply("P1", "filmic", temperature=5200)   # reconcile → re-own
    own = recipe.load("P1")["app_adjustments"]["filmic"]["wb"]
    assert own["previous"]["Temperature"] == "4800"
    adjust.apply("P1", "filmic", reset=True)
    assert pp3.Pp3.load(p).get("White Balance", "Temperature") == "4800"


def test_reset_keeps_comment_only_sidecar(repo):
    # Deleting a comment-only sidecar would change style_hashes (sidecar
    # existence feeds the fingerprint); only a truly empty file goes away.
    from pipeline import render
    side = render.ensure_sidecar("P1", "bw")
    adjust.apply("P1", "bw", temperature=5600)
    adjust.apply("P1", "bw", reset=True)
    assert side.exists()
    assert "# per-image override" in side.read_text()
    assert "[White Balance]" not in side.read_text()   # no stranded header


def test_adjust_validation(repo):
    with pytest.raises(jsonio.CommandError) as e:
        adjust.apply("P1", "natural", temperature=12000)
    assert e.value.code == "BAD_INPUT"
    with pytest.raises(jsonio.CommandError) as e:
        adjust.apply("NOPE", "natural", temperature=5000)
    assert e.value.code == "NOT_FOUND"


def test_adjust_render_failure_keeps_sidecar(repo, monkeypatch):
    from pipeline import driver, render

    def boom(stem, style):
        raise render.RenderError("rt failed")
    monkeypatch.setattr(driver, "preview_photo", boom)
    with pytest.raises(jsonio.CommandError) as e:
        adjust.apply("P1", "filmic", exposure=-0.2)
    assert e.value.code == "RENDER_FAILED"
    assert pp3.Pp3.load(paths.sidecars_dir() / "P1_filmic.pp3").get(
        "Exposure", "Compensation") == "-0.2"
