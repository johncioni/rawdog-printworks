import hashlib
import json
import subprocess

import pytest

from pipeline import ingest


GOOD = {"Make": "Panasonic", "Model": "DC-GH7", "ImageWidth": 5776,
        "ImageHeight": 4336, "Orientation": "Horizontal (normal)",
        "LensModel": "X", "ISO": 200, "ExposureTime": "1/800"}


def test_preflight_clean(monkeypatch):
    monkeypatch.setattr(ingest, "exif_summary", lambda p: dict(GOOD))
    warnings, meta = ingest.preflight("Input/P9.rw2", set(), set())
    assert warnings == []
    assert meta == GOOD


def test_preflight_flags_high_iso(monkeypatch):
    monkeypatch.setattr(ingest, "exif_summary",
                        lambda p: dict(GOOD, ISO=3200))
    warnings, _ = ingest.preflight("Input/P9.rw2", set(), set())
    assert any("ISO" in warning for warning in warnings)


def test_preflight_flags_unexpected_body(monkeypatch):
    monkeypatch.setattr(ingest, "exif_summary",
                        lambda p: dict(GOOD, Model="DC-S5"))
    warnings, _ = ingest.preflight("Input/P9.rw2", set(), set())
    assert any("DC-S5" in warning for warning in warnings)


def test_preflight_rejects_duplicate_stem(monkeypatch):
    monkeypatch.setattr(ingest, "exif_summary", lambda p: dict(GOOD))
    with pytest.raises(ingest.IngestError):
        ingest.preflight("Input/P9.rw2", {"P9"}, set())


def test_archive_verifies_hash(tmp_repo):
    src = tmp_repo / "Input/P9.rw2"
    src.write_bytes(b"raw-bytes")
    sha = hashlib.sha256(b"raw-bytes").hexdigest()
    assert ingest.archive(src, sha) is None
    assert (tmp_repo / "archive/P9.rw2").read_bytes() == b"raw-bytes"
    assert (tmp_repo / "archive/SHA256SUMS").read_text() == (
        f"{sha}  P9.rw2\n")


def test_preflight_rejects_duplicate_content(monkeypatch):
    monkeypatch.setattr(ingest, "exif_summary", lambda p: dict(GOOD))
    sha = hashlib.sha256(b"same").hexdigest()
    with pytest.raises(ingest.IngestError):
        ingest.preflight_with_hash("Input/P9.rw2", set(), {sha}, sha)


def test_archive_never_overwrites(tmp_repo):
    src = tmp_repo / "Input/P9.rw2"
    src.write_bytes(b"new")
    destination = tmp_repo / "archive/P9.rw2"
    destination.write_bytes(b"old")
    with pytest.raises(ingest.IngestError):
        ingest.archive(src, "whatever")
    assert destination.read_bytes() == b"old"


def test_run_isolates_failures(tmp_repo, monkeypatch):
    (tmp_repo / "Input/BAD.rw2").write_bytes(b"a")
    (tmp_repo / "Input/GOOD.rw2").write_bytes(b"b")

    def summary(path):
        if "BAD" in str(path):
            raise ingest.IngestError("BAD: unreadable metadata")
        return dict(GOOD)

    monkeypatch.setattr(ingest, "exif_summary", summary)
    results = ingest.run()
    assert "failed" in results["BAD"]
    assert results["GOOD"] == "ok"
    saved = (tmp_repo / "recipes/GOOD.yaml").read_text()
    assert "width: 5776" in saved and "height: 4336" in saved


def test_run_isolates_oserrors(tmp_repo, monkeypatch):
    (tmp_repo / "Input/BAD.rw2").write_bytes(b"a")
    (tmp_repo / "Input/GOOD.rw2").write_bytes(b"b")
    monkeypatch.setattr(ingest, "exif_summary", lambda path: dict(GOOD))
    real_archive = ingest.archive

    def archive(path, sha):
        if path.stem == "BAD":
            raise OSError("disk unavailable")
        return real_archive(path, sha)

    monkeypatch.setattr(ingest, "archive", archive)
    results = ingest.run()
    assert results["BAD"] == "failed: disk unavailable"
    assert results["GOOD"] == "ok"


def test_run_rejects_duplicate_content_within_batch(tmp_repo, monkeypatch):
    (tmp_repo / "Input/A.rw2").write_bytes(b"same")
    (tmp_repo / "Input/B.rw2").write_bytes(b"same")
    monkeypatch.setattr(ingest, "exif_summary", lambda path: dict(GOOD))
    results = ingest.run()
    assert results["A"] == "ok"
    assert "failed" in results["B"] and "content" in results["B"]


def test_exif_summary_wraps_subprocess_failure(monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], stderr="bad raw")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(ingest.IngestError,
                       match=r"P9: unreadable metadata: .*bad raw"):
        ingest.exif_summary("Input/P9.rw2")


def test_exif_summary_wraps_json_failure(monkeypatch):
    completed = subprocess.CompletedProcess([], 0, stdout="not json", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed)
    with pytest.raises(ingest.IngestError,
                       match="P9: unreadable metadata"):
        ingest.exif_summary("Input/P9.rw2")


def test_exif_summary_records_aspect_ratio(monkeypatch):
    payload = dict(GOOD, AspectRatio="4:3", Ignored="value")
    completed = subprocess.CompletedProcess(
        [], 0, stdout=json.dumps([payload]), stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed)
    meta = ingest.exif_summary("Input/P9.rw2")
    assert meta["AspectRatio"] == "4:3"
    assert meta["Make"] == "Panasonic"


def test_preflight_rejects_missing_dimensions(monkeypatch):
    monkeypatch.setattr(ingest, "exif_summary",
                        lambda p: dict(GOOD, ImageWidth=0))
    with pytest.raises(ingest.IngestError, match="unreadable dimensions"):
        ingest.preflight("Input/P9.rw2", set(), set())


def test_preflight_flags_unrecognized_orientation(monkeypatch):
    monkeypatch.setattr(ingest, "exif_summary",
                        lambda p: dict(GOOD, Orientation="sideways"))
    warnings, _ = ingest.preflight("Input/P9.rw2", set(), set())
    assert any("Orientation" in warning for warning in warnings)
