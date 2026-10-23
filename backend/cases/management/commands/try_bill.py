r"""Price one bill PDF from the command line. Writes nothing (no case, no upload).

    python backend\manage.py try_bill tests\fixtures\test_bills\B01_TEST_bill.pdf
    python backend\manage.py try_bill C:\secure\bill.pdf --payer "Medical Mutual"

Use it to check a new hospital's price file or a new bill layout before a real upload.
Do not point it at a real bill on a shared screen: it prints the bill lines.
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from pipeline.lien import db, match, price, reader


def m(v):
    return "—" if v is None else f"{float(v):,.2f}"


class Command(BaseCommand):
    help = "Read and price one bill PDF; print lines, totals and flags."

    def add_arguments(self, p):
        p.add_argument("pdf")
        p.add_argument("--payer", help="override the payer printed on the bill")
        p.add_argument("--ccn", help="override the hospital CCN")
        p.add_argument("--drg", help="override the MS-DRG (inpatient)")

    def handle(self, pdf, payer=None, ccn=None, drg=None, **_):
        path = Path(pdf)
        if not path.exists():
            raise CommandError(f"{path} not found")
        try:
            bill = reader.read(path.read_bytes(), path.name)
        except reader.BillNotReadable as e:
            raise CommandError(str(e))
        if drg:
            bill.ms_drg = drg
        con = db.connect()
        try:
            hosp = match.find(con, ccn=ccn or bill.ccn, npi=bill.npi, name=bill.facility_name)
            if hosp is None:
                raise CommandError(f"Hospital not found: name {bill.facility_name!r}, CCN {bill.ccn!r}, NPI {bill.npi!r}. Use --ccn.")
            r = price.price(con, bill, hosp.ccn, payer if payer is not None else bill.payer)
        finally:
            con.close()
        w = self.stdout.write
        pf = r.price_file
        w(f"Hospital   {hosp.name} (CCN {hosp.ccn}, matched by {hosp.method}{'' if hosp.certain else ', CHECK'})")
        w(f"Dates      {bill.date_from} to {bill.date_to}   {'inpatient' if bill.inpatient else 'outpatient'}   "
          f"payer {bill.payer or 'none'} -> group {r.payer_group}")
        w(f"Price file {pf.file_name + ' dated ' + str(pf.last_updated_on) + ('' if pf.covers_service_date else '  (does NOT cover the date: estimate)') if pf else 'none loaded'}")
        w(f"CCR        {r.ccr if r.ccr is not None else 'none'}")
        w("")
        w(f"{'#':>3} {'rev':4} {'code':5} {'units':>5} {'charge':>11} {'payer':>11} {'median':>11} {'cash':>9} {'medicare':>10} {'cost':>10}  medicare basis")
        for d in r.lines.get("service_date", []):
            w(f"{d['line_no']:>3} {d['revenue_code']:4} {d['hcpcs'] or '':5} {float(d['units']):>5g} {m(d['charge']):>11} "
              f"{m(d['payer_rate']) + ('*' if d['payer_rate_is_estimate'] else ''):>11} {m(d['median']):>11} {m(d['cash']):>9} "
              f"{m(d['medicare']):>10} {m(d['cost']):>10}  {d['medicare_source']}")
        if r.stay:
            v = r.stay["values"]
            w(f"\nStay: MS-DRG {r.stay['ms_drg']} {r.stay['drg_title']}, {r.stay['los_days']} days")
            w(f"  payer {m(v['payer_rate'])}  median {m(v['median'])} (p10 {m(v['p10'])}, p90 {m(v['p90'])})  "
              f"cash {m(v['cash'])}  medicare {m(v['medicare'])}  cost {m(v['cost'])}")
        t = r.totals
        w(f"\nTotals: billed {m(t['billed'])}  payer {m(t['payer_rate'])}  median {m(t['median'])}  cash {m(t['cash'])}  "
          f"medicare {m(t['medicare'])}  cost {m(t['cost'])}")
        if t.get("coverage"):
            w("Coverage (% of billed on lines with a value): " + ", ".join(f"{k} {v} %" for k, v in t["coverage"].items()))
        if bill.stated_total is not None:
            w(f"Bill says total {m(bill.stated_total)}; lines add up to {m(bill.lines_total)}")
        w("\nFlags:")
        for f in r.flags:
            w(f"  [{f['severity']}] {f['title']}. {f['detail']}")
        w("\n* = estimate (percentage contract or estimated amount)")
