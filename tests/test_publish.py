import json
import os

import pytest

from pipeline import publish


def _stage(
    tmp_repo,
    stem="P1",
    files=("P1_natural.tif", "P1_natural.jpg"),
):
    directory = tmp_repo / "staging" / f"{stem}.tmp"
    directory.mkdir(parents=True, exist_ok=True)
    for name in files:
        (directory / name).write_bytes(b"data")
    return directory


def test_publish_creates_v001_and_current(tmp_repo):
    staging = _stage(tmp_repo)
    publish.publish(
        "P1",
        staging,
        {"tools": {}},
        {"P1_natural.tif", "P1_natural.jpg"},
    )
    photo = tmp_repo / "Output/photos/P1"
    assert (photo / "v001/P1_natural.tif").exists()
    assert (photo / "v001/provenance.json").exists()
    assert os.readlink(photo / "current") == "v001"
    assert not staging.exists()


def test_republish_swaps_and_prunes(tmp_repo):
    allowlist = {"P1_natural.tif", "P1_natural.jpg"}
    publish.publish("P1", _stage(tmp_repo), {}, allowlist)
    publish.publish("P1", _stage(tmp_repo), {}, allowlist)
    photo = tmp_repo / "Output/photos/P1"
    assert os.readlink(photo / "current") == "v002"
    assert not (photo / "v001").exists()


def test_lock_excludes_second_holder(tmp_repo):
    with publish.acquire_lock():
        with pytest.raises(publish.LockError):
            with publish.acquire_lock():
                pass


def test_rebuild_views(tmp_repo):
    publish.publish(
        "P1",
        _stage(tmp_repo),
        {},
        {"P1_natural.tif", "P1_natural.jpg"},
    )
    publish.rebuild_views()
    link = tmp_repo / "Output/JPG/P1_natural.jpg"
    expected = os.path.relpath(
        tmp_repo / "Output/photos/P1/current/P1_natural.jpg",
        link.parent,
    )
    assert link.is_symlink()
    assert os.readlink(link) == expected
    assert link.resolve().read_bytes() == b"data"


def test_recover_removes_orphan_staging(tmp_repo):
    staging = _stage(tmp_repo, "P9")
    actions = publish.recover()
    assert not staging.exists()
    assert any("P9" in action for action in actions)


def test_publish_excludes_non_allowlisted(tmp_repo):
    staging = _stage(
        tmp_repo,
        files=(
            "P1_natural.tif",
            "P1_comparison_src.jpg",
            "extract-000.jpg",
        ),
    )
    publish.publish("P1", staging, {}, {"P1_natural.tif"})
    version = tmp_repo / "Output/photos/P1/v001"
    assert (version / "P1_natural.tif").exists()
    assert (version / "provenance.json").exists()
    assert not (version / "P1_comparison_src.jpg").exists()
    assert not (version / "extract-000.jpg").exists()


def test_stale_lock_reclaimed(tmp_repo):
    lock = tmp_repo / "run/driver.lock"
    lock.write_text("999999")
    with publish.acquire_lock():
        pass


def test_recover_repoints_broken_current(tmp_repo):
    version = tmp_repo / "Output/photos/P1/v001"
    version.mkdir(parents=True)
    (version / "provenance.json").write_text(json.dumps({"fingerprint": "fp"}))
    actions = publish.recover()
    assert os.readlink(tmp_repo / "Output/photos/P1/current") == "v001"
    assert any("repointed" in action for action in actions)


def test_recover_removes_publish_orphans(tmp_repo):
    photo = tmp_repo / "Output/photos/P1"
    version = photo / "v001"
    version.mkdir(parents=True)
    (version / "provenance.json").write_text(json.dumps({}))
    os.symlink("v001", photo / "current")

    orphan_version = photo / "v002.tmp"
    orphan_version.mkdir()
    (orphan_version / "P1_natural.tif").write_bytes(b"data")
    orphan_current = photo / ".current.tmp-999"
    os.symlink("v002", orphan_current)

    actions = publish.recover()

    assert not orphan_version.exists()
    assert not orphan_current.is_symlink()
    assert version.exists()
    assert os.readlink(photo / "current") == "v001"
    assert "removed publish orphan P1/v002.tmp" in actions
    assert "removed publish orphan P1/.current.tmp-999" in actions


def test_recover_preserves_versions_when_current_broken(tmp_repo):
    photo = tmp_repo / "Output/photos/P1"
    for name in ("v001", "v002"):
        version = photo / name
        version.mkdir(parents=True)
        (version / "provenance.json").write_text(json.dumps({}))
    os.symlink("v999", photo / "current")

    actions = publish.recover()

    assert (photo / "v001").is_dir()
    assert (photo / "v002").is_dir()
    assert any("ambiguous" in action for action in actions)
