"""Access to original downloads (Spec §3.2).

A raw file is the CMS download exactly as received. We hash it, never change
it, and read members straight out of the zip. A folder is also accepted
(for NPPES, where people often keep only the unzipped folder); then each
member file is hashed on its own.
"""
from __future__ import annotations

import fnmatch
import hashlib
import io
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

CHUNK = 8 * 1024 * 1024


def sha256_file(path: Path) -> str:
    sidecar = path.with_name(path.name + ".sha256")
    stat = path.stat()
    # Cache: "<hash>  <size>  <mtime_ns>" so re-runs do not re-hash 11 GB.
    if sidecar.exists():
        parts = sidecar.read_text(encoding="utf-8").split()
        if len(parts) >= 3 and parts[1] == str(stat.st_size) and parts[2] == str(stat.st_mtime_ns):
            return parts[0]
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(CHUNK):
            h.update(block)
    digest = h.hexdigest()
    try:
        sidecar.write_text(f"{digest}  {stat.st_size}  {stat.st_mtime_ns}\n", encoding="utf-8")
    except OSError:
        pass
    return digest


class RawFileMissing(FileNotFoundError):
    pass


@dataclass
class Member:
    """One file inside a raw download."""
    raw: "RawFile"
    name: str

    @property
    def lineage_name(self) -> str:
        return f"{self.raw.path.name}!{self.name}" if self.raw.is_zip else self.name

    @property
    def sha256(self) -> str:
        """Hash used in the lineage column: the zip's hash, or the member's
        own hash when the raw file is a folder."""
        return self.raw.sha256 if self.raw.is_zip else sha256_file(self.raw.path / self.name)

    def read_bytes(self) -> bytes:
        if self.raw.is_zip:
            with zipfile.ZipFile(self.raw.path) as zf:
                return zf.read(self.name)
        return (self.raw.path / self.name).read_bytes()

    def read_head(self, n: int) -> bytes:
        """First n bytes without reading the whole member."""
        if self.raw.is_zip:
            with zipfile.ZipFile(self.raw.path) as zf, zf.open(self.name) as fh:
                return fh.read(n)
        with open(self.raw.path / self.name, "rb") as fh:
            return fh.read(n)

    def open_text(self, encoding: str = "utf-8-sig") -> io.StringIO:
        return io.StringIO(self.read_bytes().decode(encoding, errors="replace"))

    def local_path(self, work_dir: Path) -> Path:
        """A real file path (for lazy scans). Zip members are extracted once
        into data/work/; the original zip is not touched."""
        if not self.raw.is_zip:
            return self.raw.path / self.name
        target = work_dir / self.raw.sha256[:16] / Path(self.name).name
        if target.exists():
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        with zipfile.ZipFile(self.raw.path) as zf, zf.open(self.name) as src, open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst, CHUNK)
        tmp.rename(target)
        return target


class RawFile:
    def __init__(self, raw_root: Path, rel_path: str):
        self.rel_path = rel_path
        self.path = raw_root / rel_path
        if not self.path.exists():
            raise RawFileMissing(f"raw file not found: {(raw_root / rel_path).as_posix()}")
        # .xlsx/.docx are zip containers too; treat them as single files.
        self.is_zip = (self.path.is_file() and self.path.suffix.lower() not in (".xlsx", ".xlsm", ".docx")
                       and zipfile.is_zipfile(self.path))
        self._sha: str | None = None

    @property
    def sha256(self) -> str:
        if self._sha is None:
            if self.path.is_dir():
                h = hashlib.sha256()
                for name in self.names():
                    h.update(f"{name}:{sha256_file(self.path / name)}\n".encode())
                self._sha = h.hexdigest()
            else:
                self._sha = sha256_file(self.path)
        return self._sha

    @property
    def size_bytes(self) -> int:
        if self.path.is_dir():
            return sum(p.stat().st_size for p in self.path.rglob("*") if p.is_file())
        return self.path.stat().st_size

    def names(self) -> list[str]:
        if self.is_zip:
            with zipfile.ZipFile(self.path) as zf:
                return [n for n in zf.namelist() if not n.endswith("/")]
        if self.path.is_dir():
            return sorted(str(p.relative_to(self.path)) for p in self.path.rglob("*")
                          if p.is_file() and not p.name.endswith(".sha256"))
        return [self.path.name]

    def member(self, pattern: str) -> Member:
        found = self.members(pattern)
        if len(found) != 1:
            raise ValueError(
                f"{self.path.name}: pattern {pattern!r} matched {len(found)} files "
                f"({found[:5]}); expected exactly 1")
        return found[0]

    def members(self, pattern: str) -> list[Member]:
        if not self.is_zip and self.path.is_file():
            return [Member(_SingleFile(self), self.path.name)] if _match(self.path.name, pattern) else []
        out = []
        for n in self.names():
            # Windows gives sub\\file.csv for files in a subfolder; match on the file name.
            base = n.replace("\\", "/").rsplit("/", 1)[-1]
            if _match(base, pattern) or _match(n, pattern):
                out.append(Member(self, n))
        return out


def _match(name: str, pattern: str) -> bool:
    """Case-insensitive on every OS (CMS uses HOSP10_2024_RPT.CSV and
    hosp10_2024_rpt.csv in different releases)."""
    return fnmatch.fnmatchcase(name.lower(), pattern.lower())


class _SingleFile(RawFile):
    """A raw download that is one plain file (not a zip)."""
    def __init__(self, parent: RawFile):  # noqa: D401
        self.rel_path = parent.rel_path
        self.path = parent.path.parent
        self.is_zip = False
        self._sha = parent.sha256
        self._file = parent.path

    @property
    def sha256(self) -> str:
        return self._sha
