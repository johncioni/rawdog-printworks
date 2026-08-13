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
            if not m:
                continue
            if start is not None:
                # The requested section ends where the next header begins.
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
