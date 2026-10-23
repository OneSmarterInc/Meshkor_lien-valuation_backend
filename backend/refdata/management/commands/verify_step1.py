from django.core.management.base import BaseCommand

from refdata.services import verify_step1


class Command(BaseCommand):
    help = "Run the Spec §8 checks and write data/reports/verify_latest.md (send that file for review)."

    def add_arguments(self, parser):
        parser.add_argument("--no-rehash", action="store_true", help="skip re-hashing raw files (faster)")
        parser.add_argument("--quiet", action="store_true", help="print only the summary line")

    def handle(self, *args, no_rehash, quiet, **opts):
        vr, path = verify_step1(rehash=not no_rehash)
        if not quiet:
            self.stdout.write(vr.report_markdown)
        style = self.style.ERROR if vr.failed else self.style.SUCCESS
        self.stdout.write(style(f"{vr.passed} pass, {vr.failed} fail, {vr.not_run} not run — report: {path}"))
