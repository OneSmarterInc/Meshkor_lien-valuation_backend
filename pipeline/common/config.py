"""Paths and config loading. No Django imports here: the pipeline must run
on its own (Steps 2–5 reuse it)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_env(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE). Real environment variables win. Same rule as
    backend/meshkor/settings.py, so `python -m pipeline.hpt.run` and manage.py see the
    same MESHKOR_RAW_DIR / MESHKOR_DATA_ROOT / MESHKOR_SOURCES (Oct 23, 2026)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env(PROJECT_ROOT / ".env")
OPEN_END = date(9999, 12, 31)


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def raw(self) -> Path:
        """Downloads folder. Default data/raw; set MESHKOR_RAW_DIR to use a
        folder you already have (e.g. D:/Datasetof CMS) without copying."""
        override = os.environ.get("MESHKOR_RAW_DIR")
        return Path(override) if override else self.root / "raw"

    @property
    def ref(self) -> Path:
        return self.root / "ref"

    @property
    def work(self) -> Path:
        return self.root / "work"

    @property
    def manifests(self) -> Path:
        return self.root / "ref" / "_manifest"

    @property
    def duckdb(self) -> Path:
        return self.root / "meshkor.duckdb"

    def ensure(self) -> "Paths":
        if not os.environ.get("MESHKOR_RAW_DIR"):
            self.raw.mkdir(parents=True, exist_ok=True)
        for p in (self.ref, self.work, self.manifests):
            p.mkdir(parents=True, exist_ok=True)
        return self


def data_paths(root: str | os.PathLike | None = None) -> Paths:
    root = root or os.environ.get("MESHKOR_DATA_ROOT") or PROJECT_ROOT / "data"
    return Paths(Path(root)).ensure()


def load_yaml(name: str, config_dir: Path | None = None) -> dict:
    config_dir = config_dir or Path(os.environ.get("MESHKOR_CONFIG_DIR", PROJECT_ROOT / "config"))
    with open(config_dir / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def sources(config_dir: Path | None = None) -> dict:
    """config/sources.yaml, or the file named in MESHKOR_SOURCES
    (e.g. sources_local.yaml for a folder of unzipped downloads)."""
    return load_yaml(os.environ.get("MESHKOR_SOURCES", "sources.yaml"), config_dir)


def geography(config_dir: Path | None = None) -> dict:
    return load_yaml("geography.yaml", config_dir)["first_market"]
