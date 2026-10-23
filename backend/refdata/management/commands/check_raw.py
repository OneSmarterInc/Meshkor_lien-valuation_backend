from django.core.management.base import BaseCommand, CommandError

from pipeline.check_raw import BAD, check, render


class Command(BaseCommand):
    help = "Check that every download in config/sources.yaml is in data/raw and has the files the loaders need."

    def handle(self, *args, **opts):
        rows = check()
        self.stdout.write(render(rows))
        if any(r[2] == BAD for r in rows):
            raise CommandError("fix the PROBLEM lines first")
