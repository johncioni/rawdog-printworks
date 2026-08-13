from pathlib import Path

from pipeline.pp3 import Pp3

REAL_SIDECAR = """# per-image override for P1036170 [vibrant] — layered over config/styles/vibrant.pp3
# Dusk frame: same warm-up as the natural sidecar so vibrance builds on
# honest skin tones instead of amplifying the cool cast.

[White Balance]
Setting=Custom
Temperature=5700
Green=1.0

[Exposure]
Compensation=0.12
CurveMode=Standard
Curve=1;0;0;0.25;0.22;0.75;0.78;1;1;
"""


def test_round_trip_preserves_bytes(tmp_path):
    p = tmp_path / "s.pp3"
    p.write_text(REAL_SIDECAR)
    doc = Pp3.load(p)
    assert doc.dump() == REAL_SIDECAR


def test_get_and_set_in_place(tmp_path):
    p = tmp_path / "s.pp3"
    p.write_text(REAL_SIDECAR)
    doc = Pp3.load(p)
    assert doc.get("White Balance", "Temperature") == "5700"
    doc.set("White Balance", "Temperature", "5450")
    out = doc.dump()
    assert "Temperature=5450" in out
    assert out.count("[White Balance]") == 1
    # Untouched keys and comments intact
    assert "Curve=1;0;0;0.25;0.22;0.75;0.78;1;1;" in out
    assert out.startswith("# per-image override")


def test_set_creates_missing_section_and_key(tmp_path):
    doc = Pp3.load(tmp_path / "missing.pp3")
    doc.set("White Balance", "Setting", "Custom")
    doc.set("White Balance", "Temperature", "5600")
    out = doc.dump()
    assert "[White Balance]\nSetting=Custom\nTemperature=5600" in out


def test_remove_and_section_keys(tmp_path):
    p = tmp_path / "s.pp3"
    p.write_text(REAL_SIDECAR)
    doc = Pp3.load(p)
    assert doc.remove("Exposure", "Compensation") is True
    assert doc.remove("Exposure", "Compensation") is False
    assert doc.get("Exposure", "Compensation") is None
    assert doc.section_keys("Exposure") == ["CurveMode", "Curve"]


def test_remove_section_if_empty(tmp_path):
    p = tmp_path / "s.pp3"
    p.write_text("[White Balance]\nTemperature=5600\n\n"
                 "[Exposure]\nCompensation=0.1\n")
    doc = Pp3.load(p)
    assert doc.remove_section_if_empty("White Balance") is False  # has a key
    doc.remove("White Balance", "Temperature")
    assert doc.remove_section_if_empty("White Balance") is True
    assert "[White Balance]" not in doc.dump()
    assert doc.get("Exposure", "Compensation") == "0.1"           # untouched


def test_remove_section_if_empty_preserves_comment_only_sections(tmp_path):
    p = tmp_path / "s.pp3"
    p.write_text("[White Balance]\n# hand note kept on purpose\n")
    doc = Pp3.load(p)
    assert doc.remove_section_if_empty("White Balance") is False
    assert "# hand note kept on purpose" in doc.dump()


def test_write_atomic(tmp_path):
    p = tmp_path / "s.pp3"
    doc = Pp3.load(p)
    doc.set("Exposure", "Compensation", "0.1")
    doc.write_atomic(p)
    assert p.read_text().rstrip().endswith("Compensation=0.1")
    assert [q.name for q in tmp_path.iterdir()] == ["s.pp3"]
