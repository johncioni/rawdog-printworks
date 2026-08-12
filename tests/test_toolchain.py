import json
import pathlib
import types

import pytest

from pipeline import toolchain

FAKE = {"rawtherapee": {"path": "/x", "version": "5.12", "sha256": "aa"},
        "magick": {"path": "/y", "version": "7.1", "sha256": "bb"}}


def _completed(stdout="RawTherapee 5.12\n", stderr="", returncode=0):
    def run(*a, **kw):
        return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
    return run


@pytest.fixture
def fake_tools(tmp_path, monkeypatch):
    """Each tool resolves to its own real file; no real tool is ever invoked.

    Per-tool files (not one shared binary) so a test can break exactly one
    probe and give each tool a distinct hash.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    binaries = {}
    for name in toolchain._VERSION_ARGS:
        f = bindir / name
        f.write_bytes(f"binary-{name}".encode())
        binaries[name] = f
    font = tmp_path / "Helvetica.ttc"
    font.write_bytes(b"font")
    icc = tmp_path / "RTv4_sRGB.icc"
    icc.write_bytes(b"icc")

    broken = {}

    def run(argv, *a, **kw):
        name = pathlib.Path(argv[0]).name
        if name in broken:
            return types.SimpleNamespace(returncode=broken[name][0],
                                         stdout=broken[name][1], stderr="")
        return types.SimpleNamespace(returncode=0, stdout="RawTherapee 5.12\n",
                                     stderr="")

    monkeypatch.setattr(toolchain, "_tool_path", lambda name: str(binaries[name]))
    monkeypatch.setattr(toolchain, "_FONT", str(font))
    monkeypatch.setattr(toolchain, "_rt_icc_path", lambda: icc)
    monkeypatch.setattr(toolchain.subprocess, "run", run)

    def break_tool(name, returncode=133, stdout=""):
        broken[name] = (returncode, stdout)

    return types.SimpleNamespace(binaries=binaries, font=font, icc=icc,
                                 break_tool=break_tool)


def test_write_and_verify_roundtrip(tmp_path):
    lock = tmp_path / "toolchain.lock"
    toolchain.write_lock(FAKE, lock)
    assert json.loads(lock.read_text()) == FAKE


def test_verify_structured_mismatch(tmp_path, monkeypatch):
    lock = tmp_path / "toolchain.lock"
    toolchain.write_lock(FAKE, lock)
    monkeypatch.setattr(toolchain, "discover", lambda: {**FAKE,
        "magick": {"path": "/y", "version": "7.2", "sha256": "cc"}})
    problems = toolchain.verify(lock)
    assert len(problems) == 1
    assert problems[0]["name"] == "magick"
    assert "7.1 -> 7.2" in problems[0]["problem"]


def test_verify_clean_when_unchanged(tmp_path, monkeypatch):
    lock = tmp_path / "toolchain.lock"
    toolchain.write_lock(FAKE, lock)
    monkeypatch.setattr(toolchain, "discover", lambda: dict(FAKE))
    assert toolchain.verify(lock) == []


def test_verify_reports_missing_tool(tmp_path, monkeypatch):
    lock = tmp_path / "toolchain.lock"
    toolchain.write_lock(FAKE, lock)
    monkeypatch.setattr(toolchain, "discover",
                        lambda: {"rawtherapee": FAKE["rawtherapee"]})
    assert toolchain.verify(lock) == [{"name": "magick", "problem": "missing"}]


def test_verify_reports_failed_probe_and_still_checks_other_tools(tmp_path, fake_tools):
    """A broken tool becomes a structured problem; the rest still verify.

    Drives the real discovery path (the fixture patches _tool_path and
    subprocess.run) rather than patching discover(), which would either hit
    real tools or skip the per-tool failure collection entirely.
    """
    lock = tmp_path / "toolchain.lock"
    toolchain.write_lock(toolchain.discover(), lock)

    fake_tools.break_tool("qpdf")
    fake_tools.binaries["magick"].write_bytes(b"upgraded magick")

    problems = toolchain.verify(lock)
    by_name = {p["name"]: p["problem"] for p in problems}
    assert set(by_name) == {"qpdf", "magick"}
    assert by_name["qpdf"].startswith("missing:")
    assert "qpdf" in by_name["qpdf"]
    assert by_name["magick"].startswith("hash mismatch")


def test_verify_reports_failed_probe_with_empty_output(tmp_path, fake_tools):
    lock = tmp_path / "toolchain.lock"
    toolchain.write_lock(toolchain.discover(), lock)
    fake_tools.break_tool("exiftool", returncode=0, stdout="   \n")
    problems = toolchain.verify(lock)
    assert [p["name"] for p in problems] == ["exiftool"]
    assert problems[0]["problem"].startswith("missing:")


def test_verify_flags_classified_entry_without_sha256(tmp_path, monkeypatch):
    """Deleting sha256 from a classified tool must not buy an exemption."""
    lock = tmp_path / "toolchain.lock"
    toolchain.write_lock({**FAKE, "magick": {"path": "/y", "version": "7.1"}}, lock)
    monkeypatch.setattr(toolchain, "discover", lambda: dict(FAKE))
    assert toolchain.verify(lock) == [
        {"name": "magick", "problem": "malformed lock entry"}]


def test_verify_flags_non_dict_classified_entry(tmp_path, monkeypatch):
    lock = tmp_path / "toolchain.lock"
    toolchain.write_lock({**FAKE, "magick": "7.1"}, lock)
    monkeypatch.setattr(toolchain, "discover", lambda: dict(FAKE))
    assert toolchain.verify(lock) == [
        {"name": "magick", "problem": "malformed lock entry"}]


def test_verify_ignores_comment_and_informational_entries(tmp_path, monkeypatch):
    """Entries with no sha256 (python/pytest/pyyaml) and _comment never invalidate."""
    locked = {**FAKE,
              "_comment": "pinned at 5.12",
              "python": {"path": "/venv/bin/python", "version": "3.13.0"},
              "pytest": {"version": "8.0.0"},
              "pyyaml": {"version": "6.0.1"}}
    lock = tmp_path / "toolchain.lock"
    toolchain.write_lock(locked, lock)
    monkeypatch.setattr(toolchain, "discover", lambda: {**FAKE,
        "_comment": "reworded entirely",
        "python": {"path": "/venv/bin/python", "version": "3.14.1"},
        "pytest": {"version": "9.9.9"},
        "pyyaml": {"version": "7.0.0"}})
    assert toolchain.verify(lock) == []


def test_class_sets_cover_all_locked_names():
    all_names = (toolchain.RENDER_TOOLS | toolchain.CROP_TOOLS |
                 toolchain.PDF_TOOLS | toolchain.VERIFY_TOOLS)
    assert {"rawtherapee", "magick", "img2pdf", "qpdf", "exiftool",
            "pdfimages", "pdfinfo", "font", "rt_icc"} == all_names


def test_class_sets_are_disjoint():
    classes = [toolchain.RENDER_TOOLS, toolchain.CROP_TOOLS,
               toolchain.PDF_TOOLS, toolchain.VERIFY_TOOLS]
    assert sum(len(c) for c in classes) == len(set().union(*classes))


def test_discovered_names_are_all_classified():
    """Adding a tool or asset without giving it a class must fail here."""
    all_names = (toolchain.RENDER_TOOLS | toolchain.CROP_TOOLS |
                 toolchain.PDF_TOOLS | toolchain.VERIFY_TOOLS)
    assert set(toolchain._VERSION_ARGS) | set(toolchain._ASSET_NAMES) == all_names


def test_rawtherapee_is_probed_by_bare_invocation():
    """5.12 exits 2 for --version and 255 for -v/-h; only bare invocation exits 0.

    A zero-exit probe is what separates the working CLI from the in-bundle
    binary, which is executable but SIGTRAPs with no output.
    """
    assert toolchain._VERSION_ARGS["rawtherapee"] == []


def test_entries_for_subsets():
    assert set(toolchain.entries_for(FAKE, {"magick"})) == {"magick"}


def test_entries_for_skips_names_absent_from_lock():
    assert set(toolchain.entries_for(FAKE, {"magick", "img2pdf"})) == {"magick"}


def test_discover_records_tools_assets_and_informational(fake_tools):
    entries = toolchain.discover()
    for name in ("rawtherapee", "magick", "img2pdf", "qpdf", "exiftool",
                 "pdfimages", "pdfinfo"):
        assert entries[name]["path"] == str(fake_tools.binaries[name])
        assert entries[name]["version"] == "RawTherapee 5.12"
        assert len(entries[name]["sha256"]) == 64
    assert entries["font"] == {"path": str(fake_tools.font), "version": "asset",
                              "sha256": toolchain._sha256(fake_tools.font)}
    assert entries["rt_icc"]["path"] == str(fake_tools.icc)
    assert entries["rt_icc"]["version"] == "asset"
    assert "sha256" not in entries["python"]
    assert "sha256" not in entries["pytest"]
    assert "sha256" not in entries["pyyaml"]
    assert "5.12" in entries["_comment"] and "code signature" in entries["_comment"]


def test_discover_rejects_tool_whose_version_call_fails(fake_tools, monkeypatch):
    """Executable but broken (the in-bundle CLI SIGTRAPs) counts as not found."""
    monkeypatch.setattr(toolchain.subprocess, "run",
                        _completed(stdout="", stderr="", returncode=133))
    with pytest.raises(RuntimeError, match="tool not found"):
        toolchain.discover()


def test_discover_rejects_tool_with_empty_version_output(fake_tools, monkeypatch):
    monkeypatch.setattr(toolchain.subprocess, "run", _completed(stdout="  \n"))
    with pytest.raises(RuntimeError, match="tool not found"):
        toolchain.discover()


def test_discover_rejects_unresolvable_tool(fake_tools, monkeypatch):
    monkeypatch.setattr(toolchain, "_tool_path", lambda name: None)
    with pytest.raises(RuntimeError, match="tool not found"):
        toolchain.discover()


def test_discover_rejects_wrong_rawtherapee_version(fake_tools, monkeypatch):
    monkeypatch.setattr(toolchain.subprocess, "run",
                        _completed(stdout="RawTherapee 5.13\n"))
    with pytest.raises(RuntimeError, match="5.12"):
        toolchain.discover()


def test_rt_icc_found_in_app_bundle(tmp_path, monkeypatch):
    resources = tmp_path / "Resources"
    (resources / "iccprofiles" / "output").mkdir(parents=True)
    icc = resources / "iccprofiles" / "output" / "RTv4_sRGB.icc"
    icc.write_bytes(b"icc")
    monkeypatch.setattr(toolchain, "_RT_RESOURCES", str(resources))
    assert toolchain._rt_icc_path() == icc


def test_rt_icc_falls_back_to_cli_parent_when_bundle_absent(tmp_path, monkeypatch):
    prefix = tmp_path / "usr" / "local"
    (prefix / "share").mkdir(parents=True)
    icc = prefix / "share" / "RTv4_sRGB.icc"
    icc.write_bytes(b"icc")
    monkeypatch.setattr(toolchain, "_RT_RESOURCES", str(tmp_path / "no-bundle"))
    monkeypatch.setattr(toolchain.paths, "rt_cli",
                        lambda: str(prefix / "bin" / "rawtherapee-cli"))
    assert toolchain._rt_icc_path() == icc


def test_rt_icc_raises_when_profile_missing(tmp_path, monkeypatch):
    resources = tmp_path / "Resources"
    resources.mkdir()
    monkeypatch.setattr(toolchain, "_RT_RESOURCES", str(resources))
    with pytest.raises(RuntimeError, match="RTv4_sRGB"):
        toolchain._rt_icc_path()


def test_write_lock_accepts_str_path(tmp_path):
    lock = tmp_path / "toolchain.lock"
    toolchain.write_lock(FAKE, str(lock))
    assert json.loads(lock.read_text()) == FAKE
