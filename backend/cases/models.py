"""A case = one hospital bill a law firm asked us to value.

Bills and EOBs are PHI. Their bytes are stored encrypted outside the repo
(see storage.py); PostgreSQL holds only name, size, hash and path. Every
view and download is written to AuditEntry.
"""
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from accounts.models import Firm

MONEY = dict(max_digits=14, decimal_places=2, null=True, blank=True)


class Case(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "uploaded"
        PROCESSING = "processing"
        NEEDS_REVIEW = "needs_review"
        RETURNED = "returned"
        NO_PRICE_FILE = "no_price_file"
        ERROR = "error"
        SENT = "sent"

    OPEN_STATUSES = ("uploaded", "processing", "needs_review", "returned", "no_price_file", "error")

    class ReportFor(models.TextChoices):
        PLAINTIFF = "plaintiff"
        DEFENSE = "defense"
        LIEN = "lien_resolution"

    class Setting(models.TextChoices):
        OUTPATIENT = "outpatient"
        INPATIENT = "inpatient"

    case_number = models.CharField(max_length=20, unique=True)
    firm = models.ForeignKey(Firm, on_delete=models.PROTECT, related_name="cases")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    matter_ref = models.CharField(max_length=100, blank=True)
    report_for = models.CharField(max_length=20, choices=ReportFor.choices)
    consent = models.BooleanField(default=False)
    consent_at = models.DateTimeField(null=True, blank=True)

    # Filled by processing (bill reading, hospital match, pricing)
    bill_type = models.CharField(max_length=20, blank=True)            # UB-04, CMS-1500, itemized
    visit_summary = models.CharField(max_length=200, blank=True)
    hospital_name = models.CharField(max_length=200, blank=True)
    ccn = models.CharField(max_length=6, blank=True, db_index=True)
    npi = models.CharField(max_length=10, blank=True)
    setting = models.CharField(max_length=10, choices=Setting.choices, default=Setting.OUTPATIENT)
    service_date_from = models.DateField(null=True, blank=True)
    service_date_to = models.DateField(null=True, blank=True)
    payer_name = models.CharField(max_length=200, blank=True)
    payer_group = models.CharField(max_length=100, blank=True)
    billed_total = models.DecimalField(**MONEY)
    price_file = models.JSONField(null=True, blank=True)   # file_name, period, last_updated_on, covers_service_date
    totals = models.JSONField(default=dict, blank=True)     # billed, payer_rate, median, cash, medicare, cost
    eob = models.JSONField(null=True, blank=True)           # what the EOB says (pipeline/lien/eob.py compare()); null = no EOB read

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UPLOADED, db_index=True)
    status_detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approval_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.case_number

    @staticmethod
    def next_number() -> str:
        """MK-<year>-<4 digits>, counted per year. Call inside a transaction."""
        year = timezone.now().year
        prefix = f"MK-{year}-"
        with transaction.atomic():
            last = (Case.objects.select_for_update().filter(case_number__startswith=prefix)
                    .order_by("-case_number").values_list("case_number", flat=True).first())
            n = int(last.rsplit("-", 1)[1]) + 1 if last else 1
        return f"{prefix}{n:04d}"

    def totals_payload(self) -> dict:
        t = {"billed": None, "payer_rate": None, "median": None, "cash": None, "medicare": None, "cost": None}
        t.update(self.totals or {})
        if t["billed"] is None and self.billed_total is not None:
            t["billed"] = float(self.billed_total)
        return t


class CaseFile(models.Model):
    class Kind(models.TextChoices):
        BILL = "bill"
        EOB = "eob"

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="files")
    kind = models.CharField(max_length=4, choices=Kind.choices)
    name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    stored_path = models.CharField(max_length=512, help_text="encrypted file, relative to MESHKOR_UPLOAD_DIR")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "uploaded_at"]


class CaseLine(models.Model):
    """One priced bill line (contract: GET /cases/{id}/lines/). Filled by pipeline.lien."""
    class Basis(models.TextChoices):
        SERVICE_DATE = "service_date"
        ESTIMATE = "estimate"

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="lines")
    basis = models.CharField(max_length=12, choices=Basis.choices, default=Basis.SERVICE_DATE)
    line_no = models.IntegerField()
    service_date = models.DateField(null=True, blank=True)
    revenue_code = models.CharField(max_length=4, blank=True)
    hcpcs = models.CharField(max_length=5, blank=True)
    modifiers = models.CharField(max_length=20, blank=True)
    units = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    description = models.CharField(max_length=300, blank=True)
    charge = models.DecimalField(**MONEY)
    confidence = models.FloatField(null=True, blank=True)
    payer_rate = models.DecimalField(**MONEY)
    payer_rate_is_estimate = models.BooleanField(default=False)
    median = models.DecimalField(**MONEY)
    p10 = models.DecimalField(**MONEY)
    p90 = models.DecimalField(**MONEY)
    cash = models.DecimalField(**MONEY)
    medicare = models.DecimalField(**MONEY)
    medicare_status = models.CharField(max_length=10, default="none")     # priced, packaged, none
    medicare_source = models.CharField(max_length=120, blank=True)
    cost = models.DecimalField(**MONEY)
    eob_allowed = models.DecimalField(**MONEY)      # from the insurer's EOB, when the line was matched to it
    eob_paid = models.DecimalField(**MONEY)
    eob_patient = models.DecimalField(**MONEY)      # deductible + copay + coinsurance
    status = models.CharField(max_length=30, default="unpriced_no_code")  # priced, packaged, unpriced_no_code, unpriced_no_hospital_row
    sources = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["basis", "line_no"]
        constraints = [models.UniqueConstraint(fields=["case", "basis", "line_no"], name="uniq_case_line")]


class Flag(models.Model):
    KINDS = ("low_confidence", "no_rate", "no_price_file", "estimate", "packaged", "no_eob", "eob", "drg_check", "other")

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="flags")
    kind = models.CharField(max_length=20)
    severity = models.CharField(max_length=5, default="check")   # check | info
    line_no = models.IntegerField(null=True, blank=True)
    title = models.CharField(max_length=200)
    detail = models.TextField(blank=True)
    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]


class Stay(models.Model):
    """Inpatient: the whole stay is priced as one MS-DRG."""
    case = models.OneToOneField(Case, on_delete=models.CASCADE, related_name="stay")
    ms_drg = models.CharField(max_length=3, blank=True)
    drg_title = models.CharField(max_length=200, blank=True)
    drg_source = models.CharField(max_length=10, default="bill")   # bill | grouper
    drg_confirmed = models.BooleanField(default=False)
    los_days = models.IntegerField(null=True, blank=True)
    diagnoses = models.JSONField(default=list, blank=True)   # [{code, description, level}]
    values = models.JSONField(default=dict, blank=True)      # billed, payer_rate, median, medicare, cost


class Feedback(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="feedback")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    outcome = models.CharField(max_length=10)        # reduced | partly | no_change
    price_per_report = models.DecimalField(**MONEY)
    pricing_model = models.CharField(max_length=15, blank=True)   # per_report | subscription
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AuditEntry(models.Model):
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actor = models.CharField(max_length=300, blank=True)   # "Jane Doe (Smith & Lee LLP)" at the time
    action = models.CharField(max_length=120)
    detail = models.TextField(blank=True)
    case = models.ForeignKey(Case, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit")

    class Meta:
        ordering = ["-at", "-id"]
        verbose_name_plural = "audit entries"
