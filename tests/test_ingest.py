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


@pytest.mark.parametrize("lens", [None, "", "   "])
def test_preflight_flags_missing_or_empty_lens_model(monkeypatch, lens):
    monkeypatch.setattr(ingest, "exif_summary",
                        lambda p: dict(GOOD, LensModel=lens))
    warnings, _ = ingest.preflight("Input/P9.rw2", set(), set())
    assert any("LensModel" in warning for warning in warnings)


def test_preflight_flags_non_native_aspect_ratio(monkeypatch):
    monkeypatch.setattr(ingest, "exif_summary",
                        lambda p: dict(GOOD, AspectRatio="16:9"))
    warnings, _ = ingest.preflight("Input/P9.rw2", set(), set())
    assert any("AspectRatio" in warning and "4:3" in warning
               for warning in warnings)


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


def test_run_ingests_uppercase_rw2_extension(tmp_repo, monkeypatch):
    (tmp_repo / "Input/UPPER.RW2").write_bytes(b"raw")
    monkeypatch.setattr(ingest, "exif_summary", lambda path: dict(GOOD))

    results = ingest.run()

    assert results["UPPER"] == "ok"


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
