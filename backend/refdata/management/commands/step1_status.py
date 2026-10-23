from django.core.management.base import BaseCommand

from pipeline.runner import configured_tables
from refdata.models import LoadRun, VerifyRun


class Command(BaseCommand):
    help = "Show the latest load run per table and the latest verify result."

    def handle(self, *args, **opts):
        self.stdout.write(f"{'table':22s} {'status':8s} {'rows':>12s}  finished")
        for t in configured_tables():
            r = LoadRun.objects.filter(table=t).first()
            if not r:
                self.stdout.write(f"{t:22s} {'never':8s}")
                continue
            rows = f"{r.rows:,}" if r.rows is not None else "-"
            self.stdout.write(f"{t:22s} {r.status:8s} {rows:>12s}  {r.finished_at:%Y-%m-%d %H:%M}")
        v = VerifyRun.objects.first()
        if v:
            self.stdout.write(f"\nlast verify {v.created_at:%Y-%m-%d %H:%M}: {v.passed} pass, {v.failed} fail, {v.not_run} not run")
