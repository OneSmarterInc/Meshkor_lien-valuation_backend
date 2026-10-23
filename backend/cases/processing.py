"""Hand a case to the pricing pipeline (pipeline/lien).

Keep this the ONLY place the API touches the pipeline. The upload request waits
for pricing (a few seconds per bill). An unexpected failure never breaks the
upload: the case goes to `error` with the reason in status_detail.
"""
import logging

log = logging.getLogger("meshkor.cases")


def _run(case, **kw) -> None:
    try:
        from pipeline.lien import intake
        intake.process(case, **kw)
    except Exception as e:  # noqa: BLE001
        log.exception("processing failed for %s", case.case_number)
        case.status, case.status_detail = case.Status.ERROR, f"Processing failed: {type(e).__name__}: {e}"
        case.save(update_fields=["status", "status_detail", "updated_at"])


def start(case, user=None) -> None:
    """New upload: read, match, price."""
    _run(case, user=user)


def reprice(case, ms_drg: str | None = None, user=None) -> None:
    """Price again, e.g. after a reviewer changes the MS-DRG or a price file is loaded."""
    _run(case, drg_override=ms_drg, user=user)
