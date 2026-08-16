### Task 3: `pipeline/pp3.py` — line-preserving pp3 editor

**Files:**
- Create: `pipeline/pp3.py`
- Test: `tests/test_pp3.py`

**Interfaces:**
- Produces:
  - `class Pp3` — `Pp3.load(path: Path) -> Pp3` (missing file → empty document), `get(section, key) -> str|None`, `set(section, key, value)` (creates section at end if absent; replaces the key's line in place if present; appends to section otherwise), `remove(section, key) -> bool`, `remove_section_if_empty(section) -> bool` (drops the header and its trailing blank line when the section has no key lines left — reset must not strand `[White Balance]` headers), `section_keys(section) -> list[str]`, `dump() -> str`, `write_atomic(path)` (temp + `os.replace`).
  - Comments (`# …`), blank lines, unknown sections/keys, and line order are preserved byte-for-byte for untouched content. **Do not use `configparser`** — it drops comments and reorders keys; the hand-written sidecars must survive round-trips intact.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pp3.py
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
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_pp3.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement `pipeline/pp3.py`**

```python
import os
import re
import tempfile
from pathlib import Path

_SECTION_RE = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")
_KEY_RE = re.compile(r"^(?P<key>[^=#;\s][^=]*)=(?P<value>.*)$")


class Pp3:
    """Line-preserving INI editor for RawTherapee .pp3 files.

    Untouched lines (comments, blanks, unknown keys) survive byte-for-byte;
    configparser would drop comments and reorder keys, destroying the
    hand-written sidecars adjust must preserve.
    """

    def __init__(self, lines):
        self._lines = lines

    @classmethod
    def load(cls, path):
        path = Path(path)
        if not path.exists():
            return cls([])
        return cls(path.read_text().splitlines(keepends=True))

    def _section_span(self, section):
        start = None
        for i, line in enumerate(self._lines):
            m = _SECTION_RE.match(line)
            if m:
                if start is not None:
                    return start, i
                if m.group("name") == section:
                    start = i
        return (start, len(self._lines)) if start is not None else None

    def _find_key(self, section, key):
        span = self._section_span(section)
        if span is None:
            return None
        for i in range(span[0] + 1, span[1]):
            m = _KEY_RE.match(self._lines[i])
            if m and m.group("key").strip() == key:
                return i
        return None

    def get(self, section, key):
        i = self._find_key(section, key)
        if i is None:
            return None
        return _KEY_RE.match(self._lines[i]).group("value").strip()

    def set(self, section, key, value):
        line = f"{key}={value}\n"
        i = self._find_key(section, key)
        if i is not None:
            self._lines[i] = line
            return
        span = self._section_span(section)
        if span is None:
            if self._lines and not self._lines[-1].endswith("\n"):
                self._lines[-1] += "\n"
            if self._lines and self._lines[-1].strip():
                self._lines.append("\n")
            self._lines += [f"[{section}]\n", line]
            return
        end = span[1]
        while end > span[0] + 1 and not self._lines[end - 1].strip():
            end -= 1
        self._lines.insert(end, line)

    def remove(self, section, key):
        i = self._find_key(section, key)
        if i is None:
            return False
        del self._lines[i]
        return True

    def section_keys(self, section):
        span = self._section_span(section)
        if span is None:
            return []
        keys = []
        for i in range(span[0] + 1, span[1]):
            m = _KEY_RE.match(self._lines[i])
            if m:
                keys.append(m.group("key").strip())
        return keys

    def remove_section_if_empty(self, section):
        # "Empty" means the section body is ONLY blank lines — a section
        # holding comments or unknown content is preserved (line-preservation
        # contract; reset restoration must never delete hand-written text).
        span = self._section_span(section)
        if span is None:
            return False
        body = self._lines[span[0] + 1:span[1]]
        if any(line.strip() for line in body):
            return False
        del self._lines[span[0]:span[1]]
        return True

    def dump(self):
        return "".join(self._lines)

    def write_atomic(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(self.dump())
            os.replace(tmp, path)
        except BaseException:
            os.unlink(tmp)
            raise
```

Note on `_section_span`: it must return the span of the *requested* section, not the first section. The loop above is subtly wrong for a section that is not first — fix during implementation so the tests pass (track `start` only after matching the requested name; end at the next section header). The tests in Step 1 catch this (`Exposure` lookups in a two-section file).

- [ ] **Step 4: Run to verify pass** — `.venv/bin/python -m pytest tests/test_pp3.py -q` → PASS.

- [ ] **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/pp3.py tests/test_pp3.py
git commit -m "feat(pipeline): line-preserving pp3 editor"
```

---

