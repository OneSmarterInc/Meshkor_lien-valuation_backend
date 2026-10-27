"""Local OCR for scanned or photographed bills: RapidOCR (PP-OCR models on ONNX Runtime).

Free (Apache-2.0) and fully local: the image is read on this computer and is never sent anywhere.
On the very first use RapidOCR downloads its 3 model files (about 32 MB) into its package folder;
after that it needs no network. (On a server without internet, copy the folder
<site-packages>/rapidocr/models from a PC that has them.)

Tested on the 10 synthetic test bills as clean scans and as tilted, blurred phone photos:
143 of 146 lines and 80 of 80 header fields read exactly; the 3 misses were all flagged for checking.
(Tesseract, the other free engine, read 71 of 146 lines on the same images.)
"""
from __future__ import annotations

import io
import math
import statistics
from dataclasses import dataclass

_engine = None
MAX_SIDE = 3600          # larger images are scaled down (speed; no accuracy gain above ~300 dpi)
PDF_SCALE = 200 / 72     # render scanned PDF pages at 200 dpi


class OcrNotInstalled(ImportError):
    pass


@dataclass
class OcrLine:
    text: str
    score: float         # the lowest OCR certainty of the words on the line (0..1)


def _get_engine():
    global _engine
    if _engine is None:
        try:
            import logging
            from rapidocr import RapidOCR
            logging.getLogger("RapidOCR").setLevel(logging.WARNING)
        except ImportError as e:  # pragma: no cover
            raise OcrNotInstalled("OCR is not installed on this server: run  python -m pip install -r requirements.txt") from e
        _engine = RapidOCR()
        logging.getLogger("RapidOCR").setLevel(logging.WARNING)   # RapidOCR sets INFO again at start; its model paths are noise
    return _engine


def _group_lines(boxes: list[tuple[list, str, float]]) -> list[OcrLine]:
    """Turn word boxes into text lines: undo the page tilt, drop oversized text (watermarks, logos),
    then join the boxes of each line from left to right."""
    if not boxes:
        return []
    angles, heights = [], []
    for q, _t, _s in boxes:
        (x0, y0), (x1, y1) = q[0], q[1]
        if math.hypot(x1 - x0, y1 - y0) > 60:
            angles.append(math.atan2(y1 - y0, x1 - x0))
        heights.append(math.hypot(q[3][0] - q[0][0], q[3][1] - q[0][1]))
    tilt = statistics.median(angles) if angles else 0.0
    mh = statistics.median(heights)
    ca, sa = math.cos(-tilt), math.sin(-tilt)
    items = []
    for (q, text, score), h in zip(boxes, heights):
        if h > 2.6 * mh:
            continue
        x0 = min(p[0] for p in q)
        cy = sum(p[1] for p in q) / 4
        items.append((x0 * sa + cy * ca, x0 * ca - cy * sa, text, score))
    items.sort()
    rows, cur, row_y = [], [], None
    for it in items:
        if row_y is None or abs(it[0] - row_y) <= 0.55 * mh:
            cur.append(it)
            row_y = it[0] if row_y is None else (row_y * (len(cur) - 1) + it[0]) / len(cur)
        else:
            rows.append(cur)
            cur, row_y = [it], it[0]
    if cur:
        rows.append(cur)
    out = []
    for row in rows:
        row.sort(key=lambda z: z[1])
        out.append(OcrLine(" ".join(z[2] for z in row).strip(), min(z[3] for z in row)))
    return [ln for ln in out if ln.text]


def _numpy():
    try:
        import numpy as np
        return np
    except ImportError as e:
        raise OcrNotInstalled("OCR is not installed on this server: run  python -m pip install -r requirements.txt") from e


def image_lines(img) -> list[OcrLine]:
    """OCR one PIL image."""
    np = _numpy()
    img = img.convert("RGB")
    side = max(img.size)
    if side > MAX_SIDE:
        f = MAX_SIDE / side
        img = img.resize((int(img.width * f), int(img.height * f)))
    r = _get_engine()(np.asarray(img)[:, :, ::-1])      # RapidOCR wants BGR
    if r is None or r.boxes is None:
        return []
    return _group_lines([(b.tolist(), t, float(s)) for b, t, s in zip(r.boxes, r.txts, r.scores)])


def image_bytes_lines(data: bytes) -> list[OcrLine]:
    from PIL import Image, ImageOps
    img = Image.open(io.BytesIO(data))
    out = []
    for i in range(getattr(img, "n_frames", 1)):          # a multi-page TIFF has several frames
        img.seek(i)
        out += image_lines(ImageOps.exif_transpose(img))   # phone photos: apply the EXIF rotation
    return out


def pdf_lines(data: bytes, max_pages: int = 30) -> tuple[list[OcrLine], int]:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(data)
    out = []
    n = len(pdf)
    for i in range(min(n, max_pages)):
        out += image_lines(pdf[i].render(scale=PDF_SCALE).to_pil())
    return out, n
