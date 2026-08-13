import json

import pytest

from pipeline import manifest, paths, recipe, status, toolchain


@pytest.fixture
def repo(tmp_repo, monkeypatch):
    for s in paths.STYLES:
        (tmp_repo / "config/styles" / f"{s}.pp3").write_text(f"# {s}\n")
    (tmp_repo / "config/styles/filmic.pp3").write_text(
        "[White Balance]\nSetting=Custom\nTemperature=5650\nGreen=1.0\n")
    (tmp_repo / "config/toolchain.lock").write_text(json.dumps({}))
    import pathlib, shutil as _sh
    _REPO = pathlib.Path(__file__).resolve().parent.parent
    _sh.copy2(_REPO / "config/lab-profiles/generic-v1.yaml",
              tmp_repo / "config/lab-profiles/generic-v1.yaml")
    # labprofile.load validates the exact field set — always copy the real
    # profile; hand-written minimal YAML fails its schema check.
    monkeypatch.setattr(toolchain, "verify", lambda p: [])
    monkeypatch.setattr(toolchain, "entries_for", lambda lock, names: {})
    return tmp_repo


def test_snapshot_empty_repo(repo):
    snap = status.snapshot()
    assert snap["photos"] == []
    assert snap["styles"] == list(paths.STYLES)
    assert snap["toolchain"] == {"ok": True, "failures": []}
    assert snap["lock"] == {"held": False, "stale": False, "pid": None}


def test_snapshot_photo_fields_and_no_writes(repo):
    rec = recipe.new("P1", "aa" * 32, 5776, 4336)
    rec["delivery_id"] = "uuid-1"
    rec["ingested_at"] = "2026-08-12T00:00:00.000000Z"
    recipe.save("P1", rec)
    m = {"photos": {"P1": {"state": "ingested", "fingerprint": None}}}
    manifest.save(m)
    before = {p: p.stat().st_mtime_ns for p in paths.root().rglob("*")
              if p.is_file()}

    snap = status.snapshot()

    after = {p: p.stat().st_mtime_ns for p in paths.root().rglob("*")
             if p.is_file()}
    assert before == after                       # side-effect-free
    (photo,) = snap["photos"]
    assert photo["stem"] == "P1"
    assert photo["state"] == "ingested"
    assert photo["delivery_id"] == "uuid-1"
    assert photo["review_revision"].startswith("sha256:")
    assert photo["stale_previews"] == sorted(paths.STYLES)
    assert photo["adjustments"]["filmic"]["temperature"] == {
        "value": 5650, "source": "style"}
    assert photo["adjustments"]["natural"]["temperature"] == {
        "value": None, "source": "camera"}
    assert photo["crops"] == {}
    assert photo["published"] == {"version": None, "path": None,
                                  "artifact_count": None}


def test_snapshot_reports_stale_lock(repo):
    lock = paths.run_dir() / "driver.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("999999")                    # dead PID
    snap = status.snapshot()
    assert snap["lock"] == {"held": False, "stale": True, "pid": 999999}
    assert lock.exists()                         # never deleted


def test_sidecar_exposure_only_reports_mixed_sources(repo):
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))
    manifest.save({"photos": {"P1": {"state": "ingested", "fingerprint": None}}})
    (paths.sidecars_dir() / "P1_bw.pp3").write_text(
        "[Exposure]\nCompensation=0.15\n")
    snap = status.snapshot()
    (photo,) = snap["photos"]
    assert photo["adjustments"]["bw"]["exposure"] == {
        "value": 0.15, "source": "sidecar"}
    assert photo["adjustments"]["bw"]["temperature"]["source"] == "camera"
