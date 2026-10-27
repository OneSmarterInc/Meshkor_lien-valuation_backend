r"""Price new uploads in the background (MESHKOR_PRICING=worker).

    python backend\manage.py pricing_worker           keeps running; Ctrl+C to stop
    python backend\manage.py pricing_worker --once    prices what is waiting now, then stops

Run it next to the web server. More than one worker is safe: each case is taken by one only.
"""
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections, connection

from cases import processing


class Command(BaseCommand):
    help = "Price the uploaded bills that are waiting. Safe to run more than one."

    def add_arguments(self, p):
        p.add_argument("--once", action="store_true", help="price what is waiting now, then stop")
        p.add_argument("--sleep", type=float, default=2.0, help="seconds between checks when nothing waits")

    def handle(self, once=False, sleep=2.0, **_):
        self.stdout.write("Pricing worker started." + ("" if once else " Ctrl+C to stop."))
        try:
            while True:
                if not connection.in_atomic_block:   # a live worker: drop a stale connection; inside a test, keep the test's
                    close_old_connections()
                done = 0
                for c in processing.waiting():
                    if processing.price_waiting_case(c.pk, c.created_by_id):
                        c.refresh_from_db()
                        self.stdout.write(f"{c.case_number}: {c.status}  {c.status_detail[:100]}")
                        done += 1
                if once:
                    self.stdout.write(f"Done: {done} case(s) priced.")
                    return
                if not done:
                    time.sleep(sleep)
        except KeyboardInterrupt:
            self.stdout.write("Pricing worker stopped.")
