"""Hand a case to the pricing pipeline (pipeline/lien).

Keep this the ONLY place the API touches the pipeline.

A new upload is priced in the background, so the upload answers at once (a scanned
bill read by OCR can take a minute). The case waits in `uploaded`, goes to
`processing`, then to `needs_review`, `no_price_file` or `error`.

MESHKOR_PRICING (in .env) picks who does the pricing:
  thread  (default) the web server prices the bill in a background thread. Nothing else to run.
  worker  the web server only queues the case; run  python backend\\manage.py pricing_worker
          next to the web server (use this on the live server with more than one web process).
  inline  the upload waits for the pricing (the tests use this).

A case is "claimed" with one UPDATE ... WHERE status='uploaded', so two threads or
workers never price the same case. A case left in `uploaded` or `processing` by a
server restart is picked up again (see waiting()).

An unexpected failure never breaks anything: the case goes to `error` with a short
reason; the traceback goes to the server log only.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.conf import settings
from django.db import close_old_connections, connections, transaction
from django.utils import timezone

log = logging.getLogger("meshkor.cases")

STUCK_UPLOADED = timedelta(minutes=2)      # queued, but no thread or worker took it
STUCK_PROCESSING = timedelta(minutes=30)   # started, but the server stopped before the end

_pool: ThreadPoolExecutor | None = None
_pool_lock = threading.Lock()
_mine: set[int] = set()                    # case ids this process has queued or is pricing now


def mode() -> str:
    m = (getattr(settings, "MESHKOR_PRICING", "thread") or "thread").strip().lower()
    return m if m in ("thread", "worker", "inline") else "thread"


def _run(case, **kw) -> None:
    try:
        from pipeline.lien import intake
        intake.process(case, **kw)
    except Exception as e:  # noqa: BLE001
        log.exception("processing failed for %s", case.case_number)
        case.status, case.status_detail = case.Status.ERROR, f"Processing failed: {type(e).__name__}: {e}"
        case.save(update_fields=["status", "status_detail", "updated_at"])


def claim(case_id: int) -> bool:
    """Take a waiting case. True for exactly one caller."""
    from .models import Case
    return Case.objects.filter(pk=case_id, status=Case.Status.UPLOADED).update(
        status=Case.Status.PROCESSING, status_detail="Reading and pricing the bill.", updated_at=timezone.now()) == 1


def price_waiting_case(case_id: int, user_id: int | None = None) -> bool:
    """Claim and price one case. Returns False when another thread or worker has it."""
    from django.contrib.auth import get_user_model
    from .models import Case
    if not claim(case_id):
        return False
    case = Case.objects.get(pk=case_id)
    user = get_user_model().objects.filter(pk=user_id).first() if user_id else None
    _run(case, user=user)
    return True


def _thread_job(case_id: int, user_id: int | None) -> None:
    close_old_connections()
    try:
        price_waiting_case(case_id, user_id)
    except Exception:  # noqa: BLE001
        log.exception("background pricing failed for case id %s", case_id)
    finally:
        _mine.discard(case_id)
        connections.close_all()            # a thread must not keep its own database connection open


def _submit(case_id: int, user_id: int | None) -> None:
    global _pool
    with _pool_lock:
        if case_id in _mine:
            return
        _mine.add(case_id)
        if _pool is None:
            n = max(1, int(getattr(settings, "MESHKOR_PRICING_THREADS", 2) or 2))
            _pool = ThreadPoolExecutor(max_workers=n, thread_name_prefix="pricing")
    _pool.submit(_thread_job, case_id, user_id)


def start(case, user=None) -> None:
    """New upload: read, match, price. The case must be in `uploaded`."""
    m = mode()
    if m == "inline":
        if claim(case.pk):
            case.refresh_from_db()
            _run(case, user=user)
        return
    if m == "thread":
        uid = getattr(user, "pk", None)
        transaction.on_commit(lambda: _submit(case.pk, uid))   # after the upload is saved
    # worker: the case waits in `uploaded`; pricing_worker takes it


def waiting(now=None):
    """Cases a thread or worker should take now: new uploads, and cases a stop left behind."""
    from .models import Case
    now = now or timezone.now()
    stuck = Case.objects.filter(status=Case.Status.PROCESSING, updated_at__lt=now - STUCK_PROCESSING).exclude(pk__in=list(_mine))
    for c in stuck:                         # back to the queue, once
        n = Case.objects.filter(pk=c.pk, status=Case.Status.PROCESSING, updated_at=c.updated_at).update(
            status=Case.Status.UPLOADED, status_detail="Pricing started again after a server stop.", updated_at=now)
        if n:
            log.warning("case %s was stuck in processing; queued again", c.case_number)
    return Case.objects.filter(status=Case.Status.UPLOADED).order_by("created_at")


def resume_stuck() -> int:
    """thread mode: queue again the cases a server restart left behind. Called from the staff case
    list, so nothing stays stuck after a restart. Returns how many were queued."""
    if mode() != "thread":
        return 0
    cutoff = timezone.now() - STUCK_UPLOADED
    n = 0
    for c in waiting().filter(updated_at__lt=cutoff).exclude(pk__in=list(_mine)):
        _submit(c.pk, None)
        n += 1
    return n


def reprice(case, ms_drg: str | None = None, user=None) -> None:
    """Price again now (the caller waits), e.g. after a reviewer changes the MS-DRG."""
    _run(case, drg_override=ms_drg, user=user)
