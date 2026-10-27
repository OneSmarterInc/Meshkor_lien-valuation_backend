import os

from django.core.management.base import BaseCommand, CommandError

from pipeline.runner import configured_tables
from refdata.models import LoadRun
from refdata.services import load_table


class Command(BaseCommand):
    help = "Load Step 1 reference tables from data/raw into Parquet (one table, several, or 'all')."

    def add_arguments(self, parser):
        parser.add_argument("tables", nargs="+", help="e.g. ref_mpfs ref_asc, or 'all'")
        parser.add_argument("--period", action="append", help="only this period (repeatable)")
        parser.add_argument("--ccn", action="append",
                            help="only this hospital CCN (repeatable, or a comma list: --ccn 360016,360064). ref_hospital_mrf only.")

    def handle(self, *args, tables, period, **opts):
        if opts.get("ccn"):
            os.environ["MESHKOR_ONLY_CCN"] = ",".join(opts["ccn"])
        known = configured_tables()
        tables = known if tables == ["all"] else tables
        unknown = [t for t in tables if t not in known]
        if unknown:
            raise CommandError(f"unknown table(s) {unknown}. Configured: {known}")
        failed = 0
        for t in tables:
            run = load_table(t, period)
            style = {"success": self.style.SUCCESS, "skipped": self.style.WARNING}.get(run.status, self.style.ERROR)
            rows = f"{run.rows:,} rows" if run.rows is not None else ""
            self.stdout.write(style(f"{t:22s} {run.status:8s} {rows} {run.error.splitlines()[0] if run.error else ''}"))
            for w in run.warnings:
                self.stdout.write(f"    ! {w}")
            failed += run.status == LoadRun.Status.FAILED
        if failed:
            raise CommandError(f"{failed} table(s) failed; see LoadRun.error in the admin")
