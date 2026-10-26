"""Encrypted storage for bills and EOBs (PHI).

Files go under MESHKOR_UPLOAD_DIR (default <MESHKOR_DATA_ROOT>/uploads, which is
outside Git), encrypted with Fernet (AES-128-CBC + HMAC) using MESHKOR_FILE_KEY.
Make a key once:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
and put it in .env. Losing the key = losing every stored bill.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from cryptography.fernet import Fernet
from django.conf import settings

ALLOWED = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
           ".png": "image/png", ".tif": "image/tiff", ".tiff": "image/tiff",
           ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
# The first bytes must match the extension (a renamed .exe is refused); see pipeline/lien/reader.kind_of.
KIND_FOR_EXT = {".pdf": "pdf", ".jpg": "jpg", ".jpeg": "jpg", ".png": "png", ".tif": "tiff", ".tiff": "tiff", ".docx": "docx"}
MAX_BYTES = 50 * 1024 * 1024


def upload_dir() -> Path:
    d = Path(getattr(settings, "MESHKOR_UPLOAD_DIR"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fernet() -> Fernet:
    key = getattr(settings, "MESHKOR_FILE_KEY", "") or os.environ.get("MESHKOR_FILE_KEY", "")
    if not key:
        raise RuntimeError("MESHKOR_FILE_KEY is not set. See cases/storage.py for how to make one.")
    return Fernet(key.encode() if isinstance(key, str) else key)


def check_upload(f, field: str) -> str:
    """Return the content type, or raise ValueError with a message for the form."""
    ext = Path(f.name or "").suffix.lower()
    if ext not in ALLOWED:
        raise ValueError(f"{field}: only PDF, Word (.docx), JPG, PNG or TIFF files are accepted.")
    if f.size > MAX_BYTES:
        raise ValueError(f"{field}: the file is larger than 50 MB.")
    from pipeline.lien.reader import kind_of
    head = f.read(1 << 16) if ext != ".docx" else f.read()
    f.seek(0)
    if kind_of(head) != KIND_FOR_EXT[ext]:
        raise ValueError(f"{field}: the file is not a real {ext[1:].upper()} file (it may be damaged or renamed).")
    return ALLOWED[ext]


def save(case, kind: str, f):
    """Encrypt and store an uploaded file; return the CaseFile row (unsaved fields filled)."""
    from .models import CaseFile
    data = f.read()
    sha = hashlib.sha256(data).hexdigest()
    rel = Path(str(case.id)) / f"{kind}-{sha[:12]}.enc"
    out = upload_dir() / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(_fernet().encrypt(data))
    return CaseFile.objects.create(case=case, kind=kind, name=Path(f.name).name[:255],
                                   content_type=getattr(f, "content_type", "") or ALLOWED.get(Path(f.name).suffix.lower(), ""),
                                   size_bytes=len(data), sha256=sha, stored_path=rel.as_posix())


def read(cf) -> bytes:
    return _fernet().decrypt((upload_dir() / cf.stored_path).read_bytes())
