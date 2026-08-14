"""Golden contract fixtures for the --json interface.

Each scenario drives `pipeline.__main__.main` in-process, captures the NDJSON
stream, normalizes the machine-specific parts away, and compares against a
committed fixture. The fixtures are the contract the SwiftUI app decodes, so
drift in any envelope shape fails here first.

Regenerate with:

    REGEN_CONTRACT_FIXTURES=1 .venv/bin/python -m pytest tests/test_json_contract.py
"""

import hashlib
import io
import json
import os
import re
import shutil
import sys
from pathlib import Path

import pytest

from pipeline import (driver, geometry, ingest as ingest_mod, jsonio, manifest,
                      paths, provenance, recipe, render, subject, toolchain)
from pipeline.__main__ import main

FIXTURES = Path(__file__).parent / "fixtures" / "json_contract"
REGEN = os.environ.get("REGEN_CONTRACT_FIXTURES") == "1"

_SOURCE_REPO = Path(__file__).resolve().parent.parent
RAW_SHA = hashlib.sha256(b"raw-bytes").hexdigest()
INGESTED_AT = "2026-08-12T00:00:00.000000Z"


@pytest.fixture(autouse=True)
def _json_mode_hygiene(monkeypatch):
    # jsonio keeps module state; in-process back-to-back main() calls bleed
    # without this. Restores sys.stdout and resets the saved NDJSON stream.
    saved = sys.stdout
    monkeypatch.setattr(jsonio, "_out", None)
    yield
    sys.stdout = saved


def normalize(text, repo):
    text = text.replace(str(repo), "<REPO>")
    text = re.sub(r"sha256:[0-9a-f]{64}", "<REVISION>", text)
    text = re.sub(r"\b[0-9a-f]{64}\b", "<SHA256>", text)
    text = re.sub(r"\d{4}-\d{2}-\d{2}T[0-9:.+\-]+Z?", "<TIMESTAMP>", text)
    return text


def _fixture(name, text):
    path = FIXTURES / name
    if REGEN:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    if not path.exists():
        raise AssertionError(
            f"missing contract fixture {path}; regenerate with "
            "REGEN_CONTRACT_FIXTURES=1")
    assert text == path.read_text()


def run_scenario(monkeypatch, repo, argv, fixture_name, stream_name=None):
    """Run one --json command and pin its output.

    `fixture_name` receives the final envelope ALONE (the contract is one JSON
    object per .json fixture); `stream_name`, when given, receives the whole
    normalized NDJSON line list — event lines plus the envelope.
    """
    buf = io.StringIO()
    monkeypatch.setattr(jsonio, "_real_stdout", lambda: buf)
    exit_code = main(argv)
    raw = buf.getvalue()
    lines = normalize(raw, repo).splitlines()
    _fixture(fixture_name, lines[-1] + "\n")
    if stream_name is not None:
        _fixture(stream_name, "".join(line + "\n" for line in lines))
    return exit_code, json.loads(lines[-1]), lines, raw


# --------------------------------------------------------------------------
# Seeding
# --------------------------------------------------------------------------

def _fake_preview_photo(stem, style):
    """driver.preview_photo minus RawTherapee.

    Writes deterministic bytes and performs the same provenance recording the
    real render does, so previews read as fresh rather than perpetually stale.
    """
    rec = recipe.load(stem)
    inputs_hash = provenance.style_input_hash(stem, style, rec)
    path = paths.previews_dir() / f"{stem}_{style}_preview.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"preview:{stem}:{style}".encode())
    rec.setdefault("render_width", rec["width"])
    rec.setdefault("render_height", rec["height"])
    provenance.record_preview(rec, stem, style, path, inputs_hash)
    recipe.save(stem, rec)
    return path


@pytest.fixture
def seeded_repo(tmp_repo, monkeypatch):
    """The styles/lock/lab-profile seeding pattern from tests/test_status.py."""
    for style in paths.STYLES:
        (tmp_repo / "config/styles" / f"{style}.pp3").write_text(f"# {style}\n")
    (tmp_repo / "config/styles/filmic.pp3").write_text(
        "[White Balance]\nSetting=Custom\nTemperature=5650\nGreen=1.0\n")
    (tmp_repo / "config/toolchain.lock").write_text(json.dumps({}))
    # labprofile.load validates the exact field set — always copy the real
    # profile; hand-written minimal YAML fails its schema check.
    shutil.copy2(_SOURCE_REPO / "config/lab-profiles/generic-v1.yaml",
                 tmp_repo / "config/lab-profiles/generic-v1.yaml")
    monkeypatch.setattr(toolchain, "verify", lambda path: [])
    monkeypatch.setattr(toolchain, "entries_for", lambda lock, names: {})
    monkeypatch.setattr(driver, "preview_photo", _fake_preview_photo)
    return tmp_repo


def _seed_photo(stem, *, delivery=True, bind_crops=False, audit=False):
    rec = recipe.new(
        stem, RAW_SHA, 5776, 4336,
        delivery_id=f"fixture-delivery-{stem}" if delivery else None,
        ingested_at=INGESTED_AT if delivery else None)
    if bind_crops:
        rec["crops"] = {"8x10": {"x": 0.03, "y": 0.0, "w": 0.94, "h": 1.0},
                        "5x7": {"x": 0.0, "y": 0.04, "w": 1.0, "h": 0.92}}
    if audit:
        rec["expression_audit"] = ["eyes open - all: pass"]
    recipe.save(stem, rec)
    for style in paths.STYLES:
        _fake_preview_photo(stem, style)


def _seed_manifest(states):
    manifest.save({"photos": {stem: {"state": state, "fingerprint": fingerprint}
                              for stem, (state, fingerprint) in states.items()}})


@pytest.fixture
def ingested_repo(seeded_repo):
    """One photo in `ingested` state with fresh previews for every style."""
    _seed_photo("P1")
    _seed_manifest({"P1": ("ingested", None)})
    return seeded_repo


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------

def test_status_empty(seeded_repo, monkeypatch):
    exit_code, envelope, _, _ = run_scenario(
        monkeypatch, seeded_repo, ["status", "--json"], "status_empty.json")
    assert exit_code == 0
    assert envelope["ok"] is True
    assert envelope["result"]["photos"] == []
    assert envelope["result"]["lock"] == {"held": False, "stale": False,
                                          "pid": None}


def test_status_ingested(ingested_repo, monkeypatch):
    # A second photo ingested WITHOUT --delivery-id pins the null branch of
    # delivery_id/ingested_at (spec §4.3) and the sorted order of `photos`.
    _seed_photo("P0", delivery=False)
    _seed_manifest({"P0": ("ingested", None), "P1": ("ingested", None)})
    exit_code, envelope, _, _ = run_scenario(
        monkeypatch, ingested_repo, ["status", "--json"],
        "status_ingested.json")
    assert exit_code == 0
    earlier, photo = envelope["result"]["photos"]
    assert [earlier["stem"], photo["stem"]] == ["P0", "P1"]
    assert earlier["delivery_id"] is None and earlier["ingested_at"] is None
    assert photo["state"] == "ingested"
    assert photo["delivery_id"] == "fixture-delivery-P1"
    assert photo["stale_previews"] == []          # the fake records provenance
    assert photo["adjustments"]["filmic"]["temperature"] == {
        "value": 5650, "source": "style"}
    assert photo["published"] == {"version": None, "path": None,
                                  "artifact_count": None}


def test_adjust_ok(ingested_repo, monkeypatch):
    exit_code, envelope, lines, raw = run_scenario(
        monkeypatch, ingested_repo,
        ["adjust", "--stem", "P1", "--style", "natural",
         "--temperature", "5600", "--json"],
        "adjust_ok.json", stream_name="adjust_stream.ndjson")
    assert exit_code == 0
    result = envelope["result"]
    assert result["preview"] == "previews/P1_natural_preview.jpg"
    assert result["temperature"] == {"value": 5600, "source": "sidecar"}
    assert result["exposure"] == {"value": None, "source": "camera"}
    # Both revisions normalize to <REVISION>; the raw stream is where the
    # "writing a sidecar moves the revision" claim is actually checkable.
    unnormalized = json.loads(raw.strip().splitlines()[-1])["result"]
    assert (unnormalized["review_revision_before"]
            != unnormalized["review_revision_after"])
    # adjust emits no progress events, so the stream is the envelope alone.
    assert len(lines) == 1


def test_crops_suggested(ingested_repo, monkeypatch):
    monkeypatch.setattr(
        subject, "group_bbox_detail",
        lambda image: ({"x": 0.30, "y": 0.20, "w": 0.40, "h": 0.35}, "faces"))
    exit_code, envelope, _, _ = run_scenario(
        monkeypatch, ingested_repo, ["crops", "--stem", "P1", "--json"],
        "crops_suggested.json")
    assert exit_code == 0
    result = envelope["result"]
    assert result["basis"] == "faces"
    assert sorted(result["windows"]) == ["5x7", "8x10"]
    assert all(window["source"] == "suggested"
               for window in result["windows"].values())


def test_approve_ok(ingested_repo, monkeypatch):
    # The success half of spec §4.2. `ingested_repo` seeds recorded render dims
    # and fresh previews, so submitting the CURRENT revision pins the happy
    # path of the staleness check that test_approve_stale_review only fails.
    rec = recipe.load("P1")
    width, height = rec["render_width"], rec["render_height"]
    review = ingested_repo / "review.json"
    review.write_text(json.dumps({
        "expected_review_revision": provenance.review_revision("P1", rec),
        "expression_audit": ["eyes open - all: pass"],
        # Derived from the seeded dims rather than hard-coded: hand-written
        # windows are validated against the render size, not the raw size.
        "crops": {crop: geometry.centered_crop_norm(width, height, crop,
                                                    width >= height)
                  for crop in paths.CROPS},
    }))
    exit_code, envelope, lines, _ = run_scenario(
        monkeypatch, ingested_repo,
        ["approve", "--stem", "P1", "--review-file", str(review), "--json"],
        "approve_ok.json")
    assert exit_code == 0
    assert envelope["ok"] is True
    assert envelope["result"] == {"stem": "P1", "state": "approved",
                                  "fingerprint": "<SHA256>"}
    assert len(lines) == 1                   # approve emits no progress events
    # The envelope's fingerprint is the one actually persisted, not a fresh
    # recompute — normalization would hide a mismatch between the two.
    assert (manifest.load_readonly()["photos"]["P1"]["fingerprint"]
            == recipe.load("P1")["approval"]["fingerprint"])


def test_approve_stale_review(ingested_repo, monkeypatch):
    review = ingested_repo / "review.json"
    review.write_text(json.dumps({
        "expected_review_revision": "sha256:wrong",
        "expression_audit": ["eyes open - all: pass"],
        "crops": {"8x10": {"x": 0.03, "y": 0.0, "w": 0.94, "h": 1.0},
                  "5x7": {"x": 0.0, "y": 0.04, "w": 1.0, "h": 0.92}},
    }))
    exit_code, envelope, _, _ = run_scenario(
        monkeypatch, ingested_repo,
        ["approve", "--stem", "P1", "--review-file", str(review), "--json"],
        "approve_stale_review.json")
    assert exit_code == 1
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "STALE_REVIEW"
    assert "result" not in envelope


def _fake_exif(path):
    return {"Make": "Panasonic", "Model": "DC-GH7", "ImageWidth": 5776,
            "ImageHeight": 4336, "Orientation": "Horizontal (normal)",
            "LensModel": "LEICA DG 12-60", "ISO": 400,
            "ExposureTime": "1/250", "AspectRatio": "4:3"}


def test_ingest_result(ingested_repo, monkeypatch):
    # exiftool would have to read a real RW2; the shape under test is the
    # ingest result body, not metadata extraction.
    monkeypatch.setattr(ingest_mod, "exif_summary", _fake_exif)
    sources = ingested_repo / "sources"
    sources.mkdir()
    placeable = sources / "S1.RW2"
    placeable.write_bytes(b"source-one")
    conflicting = sources / "P1.RW2"        # P1 already in the manifest
    conflicting.write_bytes(b"source-two")

    exit_code, envelope, _, _ = run_scenario(
        monkeypatch, ingested_repo,
        ["ingest", "--from", str(placeable), str(conflicting),
         "--delivery-id", "fixture-uuid", "--json"],
        "ingest_result.json")

    assert exit_code == 0
    assert envelope["result"] == {
        "ingested": ["S1"],
        "skipped": [],
        "conflicts": [{"file": "P1.RW2",
                       "reason": "stem exists with different content"}],
        "failed": []}


def _fake_publish_photo(stem):
    """publish without the real tree: a v001 the `current` symlink resolves."""
    photo = paths.output_dir() / "photos" / stem
    version = photo / "v001"
    version.mkdir(parents=True, exist_ok=True)
    current = photo / "current"
    if not current.is_symlink():
        os.symlink("v001", current)
    return {f"{stem}_natural.tif": {"raw": RAW_SHA},
            f"{stem}_natural.jpg": {"raw": RAW_SHA}}


def test_run_partial_failure(seeded_repo, monkeypatch):
    # P0 is `ingested`, so one run fills all three result buckets and emits
    # both event types; P1 publishes, P2 fails verification, P3 fails render
    # — two different failed[].code values, pinning that the field varies
    # (RAW-10) rather than always reading VERIFY_FAILED.
    _seed_photo("P0")
    for stem in ("P1", "P2", "P3"):
        _seed_photo(stem, bind_crops=True, audit=True)
    # The fingerprint has to be taken AFTER every seeding write: previews and
    # sidecars feed it, and a stale one downgrades the stem to review_required.
    states = {"P0": ("ingested", None)}
    states.update({stem: ("approved", driver._current_fingerprint(stem))
                   for stem in ("P1", "P2", "P3")})
    _seed_manifest(states)

    def _fake_render_photo(stem, only=None):
        if stem == "P3":
            raise render.RenderError("simulated render failure")

    monkeypatch.setattr(driver, "render_photo", _fake_render_photo)
    monkeypatch.setattr(
        driver, "verify_photo",
        lambda stem: [] if stem == "P1" else ["dpi 240 != 300"])
    monkeypatch.setattr(driver, "_publish_photo", _fake_publish_photo)

    exit_code, envelope, lines, _ = run_scenario(
        monkeypatch, seeded_repo, ["run", "--json"],
        "run_partial_failure.json", stream_name="run_stream.ndjson")

    assert exit_code == 1
    assert envelope["error"] == {"code": "PARTIAL_FAILURE",
                                 "message": "2 of 4 photos failed"}
    assert envelope["result"]["advanced"] == [
        {"stem": "P0", "state": "preview_ready"}]
    assert envelope["result"]["published"] == [
        {"stem": "P1", "version": "v001", "artifact_count": 2}]
    assert envelope["result"]["failed"] == [
        {"stem": "P2", "code": "VERIFY_FAILED", "message": "dpi 240 != 300"},
        {"stem": "P3", "code": "RENDER_FAILED",
         "message": "simulated render failure"}]
    # Events precede the envelope, per stem, and the envelope is always last.
    assert [(json.loads(line)["stem"], json.loads(line)["event"],
             json.loads(line)["stage"]) for line in lines[:-1]] == [
        ("P0", "stage", "preview"),
        *[("P0", "progress", "preview")] * 4,
        ("P1", "stage", "render"), ("P1", "stage", "verify"),
        ("P1", "stage", "publish"),
        ("P2", "stage", "render"), ("P2", "stage", "verify"),
        ("P3", "stage", "render")]
    assert "ok" not in json.loads(lines[0])          # events are not envelopes


def test_envelope_lock_held(seeded_repo, monkeypatch):
    lock = seeded_repo / "run/driver.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(os.getpid()))        # a LIVE pid — never stale
    exit_code, envelope, _, _ = run_scenario(
        monkeypatch, seeded_repo, ["ingest", "--json"],
        "envelope_lock_held.json")
    assert exit_code == 1
    assert envelope["error"]["code"] == "LOCK_HELD"
    assert "<REPO>/run/driver.lock" in envelope["error"]["message"]


# --------------------------------------------------------------------------
# Legacy (no --flag) output guards
# --------------------------------------------------------------------------

def test_legacy_status_output_is_byte_for_byte_unchanged(tmp_repo, capsys):
    assert main(["status"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "photos: none ingested\n"
    assert captured.err == ""


def test_legacy_ingest_on_empty_input_is_byte_for_byte_unchanged(
        tmp_repo, capsys):
    # Today's output for an empty Input/ is nothing at all, exit 0.
    assert main(["ingest"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
