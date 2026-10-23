from django.core.management.base import BaseCommand

from refdata.services import build_duckdb


class Command(BaseCommand):
    help = "Copy every ref_* Parquet into data/meshkor.duckdb and create the views in sql/views.sql."

    def handle(self, *args, **opts):
        b = build_duckdb()
        for t, n in b.tables.items():
            self.stdout.write(f"  {t:24s} {n:>12,} rows")
        for name in b.objects_created:
            self.stdout.write(self.style.SUCCESS(f"  created {name}"))
        for name, why in b.objects_skipped.items():
            self.stdout.write(self.style.WARNING(f"  skipped {name}: {why}"))
        self.stdout.write(f"{b.path} ({b.size_bytes / 1e6:,.1f} MB, {b.seconds}s)")
