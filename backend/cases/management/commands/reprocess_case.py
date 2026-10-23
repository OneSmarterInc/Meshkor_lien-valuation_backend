r"""Price a case again, for example after a missing price file was loaded.

    python backend\manage.py reprocess_case MK-2026-0007
    python backend\manage.py reprocess_case --status no_price_file      (every case in that status)
"""
from django.core.management.base import BaseCommand, CommandError

from cases import processing
from cases.models import Case


class Command(BaseCommand):
    help = "Run the pricing step again for one case or every case in a status. Sent cases are never touched."

    def add_arguments(self, p):
        p.add_argument("case_number", nargs="?")
        p.add_argument("--status", help="e.g. no_price_file or error")

    def handle(self, case_number=None, status=None, **_):
        if not case_number and not status:
            raise CommandError("Give a case number or --status.")
        qs = Case.objects.exclude(status=Case.Status.SENT)
        qs = qs.filter(case_number=case_number) if case_number else qs.filter(status=status)
        if not qs.exists():
            raise CommandError("No matching case (sent cases are not reprocessed).")
        for case in qs:
            before = case.status
            processing.reprice(case)
            case.refresh_from_db()
            self.stdout.write(f"{case.case_number}: {before} -> {case.status}  {case.status_detail[:120]}")
