"""Hand a new case to the pricing pipeline.

Today: a placeholder that leaves the case in `uploaded` with a note. The next
patch plugs in pipeline.lien (bill reader -> hospital match -> price lines) and
moves the case to processing / needs_review / no_price_file / error.
Keep this the ONLY place the API touches the pipeline.
"""
import logging

log = logging.getLogger("meshkor.cases")


def start(case) -> None:
    try:
        from pipeline.lien import intake  # type: ignore  # arrives with the pricing patch
    except ImportError:
        log.info("case %s uploaded; pipeline.lien not installed yet, left as uploaded", case.case_number)
        return
    intake.process(case)
