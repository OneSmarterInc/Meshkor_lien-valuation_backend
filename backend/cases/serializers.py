from rest_framework import serializers

from accounts.serializers import FirmSerializer
from .models import Case, CaseFile, CaseLine, Feedback, Flag, Stay
from .storage import check_upload


class CaseSummarySerializer(serializers.ModelSerializer):
    firm = FirmSerializer(read_only=True)
    billed_total = serializers.FloatField(allow_null=True)
    visit_summary = serializers.SerializerMethodField()
    hospital_name = serializers.SerializerMethodField()
    ccn = serializers.SerializerMethodField()
    payer_name = serializers.SerializerMethodField()
    status_detail = serializers.SerializerMethodField()

    class Meta:
        model = Case
        fields = ("id", "case_number", "firm", "matter_ref", "visit_summary", "hospital_name", "ccn", "setting",
                  "service_date_from", "service_date_to", "payer_name", "billed_total", "status", "status_detail",
                  "created_at", "sent_at")

    @staticmethod
    def _null(v):
        return v or None

    def get_visit_summary(self, o): return self._null(o.visit_summary)
    def get_hospital_name(self, o): return self._null(o.hospital_name)
    def get_ccn(self, o): return self._null(o.ccn)
    def get_payer_name(self, o): return self._null(o.payer_name)
    def get_status_detail(self, o): return self._null(o.status_detail)


class CaseFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseFile
        fields = ("kind", "name", "size_bytes", "sha256", "uploaded_at")


class FlagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flag
        fields = ("id", "kind", "severity", "line_no", "title", "detail", "resolved")


class StaySerializer(serializers.ModelSerializer):
    ms_drg = serializers.SerializerMethodField()

    class Meta:
        model = Stay
        fields = ("ms_drg", "drg_title", "drg_source", "drg_confirmed", "los_days", "diagnoses", "values")

    def get_ms_drg(self, o): return o.ms_drg or None


class CaseDetailSerializer(CaseSummarySerializer):
    files = CaseFileSerializer(many=True, read_only=True)
    flags = FlagSerializer(many=True, read_only=True)
    hospital_match = serializers.SerializerMethodField()
    totals = serializers.SerializerMethodField()
    stay = serializers.SerializerMethodField()
    bill_type = serializers.SerializerMethodField()

    class Meta(CaseSummarySerializer.Meta):
        fields = CaseSummarySerializer.Meta.fields + ("report_for", "bill_type", "files", "hospital_match", "totals", "eob", "flags", "stay")

    def get_bill_type(self, o): return o.bill_type or None

    def get_hospital_match(self, o):
        if not o.ccn:
            return None
        return {"npi": o.npi or None, "ccn": o.ccn, "hospital_name": o.hospital_name or None, "price_file": o.price_file}

    def get_totals(self, o): return o.totals_payload()

    def get_stay(self, o):
        s = getattr(o, "stay", None)
        return StaySerializer(s).data if (o.setting == Case.Setting.INPATIENT and s) else None


class CaseCreateSerializer(serializers.Serializer):
    matter_ref = serializers.CharField(max_length=100, allow_blank=True, required=False, default="")
    report_for = serializers.ChoiceField(choices=Case.ReportFor.choices)
    consent = serializers.BooleanField()
    bill = serializers.FileField()
    eob = serializers.FileField(required=False, allow_null=True)
    firm_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_consent(self, v):
        if not v:
            raise serializers.ValidationError("You must confirm that the client consented.")
        return v

    def validate_bill(self, f):
        try:
            check_upload(f, "bill")
        except ValueError as e:
            raise serializers.ValidationError(str(e).split(": ", 1)[-1])
        return f

    def validate_eob(self, f):
        if f is None:
            return None
        try:
            check_upload(f, "eob")
        except ValueError as e:
            raise serializers.ValidationError(str(e).split(": ", 1)[-1])
        return f


class LineSerializer(serializers.ModelSerializer):
    units = serializers.FloatField()
    charge = serializers.FloatField(allow_null=True)
    payer_rate = serializers.FloatField(allow_null=True)
    median = serializers.FloatField(allow_null=True)
    p10 = serializers.FloatField(allow_null=True)
    p90 = serializers.FloatField(allow_null=True)
    cash = serializers.FloatField(allow_null=True)
    medicare = serializers.FloatField(allow_null=True)
    cost = serializers.FloatField(allow_null=True)
    eob_allowed = serializers.FloatField(allow_null=True)
    eob_paid = serializers.FloatField(allow_null=True)
    eob_patient = serializers.FloatField(allow_null=True)

    class Meta:
        model = CaseLine
        fields = ("line_no", "service_date", "revenue_code", "hcpcs", "modifiers", "units", "description", "charge",
                  "confidence", "payer_rate", "payer_rate_is_estimate", "median", "p10", "p90", "cash", "medicare",
                  "medicare_status", "medicare_source", "cost", "eob_allowed", "eob_paid", "eob_patient", "status", "sources")


class NoteSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")


class ReturnSerializer(serializers.Serializer):
    note = serializers.CharField(allow_blank=False, error_messages={"blank": "Say why the case goes back.", "required": "Say why the case goes back."})


class DrgConfirmSerializer(serializers.Serializer):
    ms_drg = serializers.RegexField(r"^\d{3}$", error_messages={"invalid": "An MS-DRG is 3 digits."})


class FeedbackSerializer(serializers.ModelSerializer):
    outcome = serializers.ChoiceField(choices=["reduced", "partly", "no_change"])
    pricing_model = serializers.ChoiceField(choices=["per_report", "subscription"], required=False, allow_null=True, allow_blank=True)
    price_per_report = serializers.FloatField(required=False, allow_null=True)
    comment = serializers.CharField(required=False, allow_blank=True, default="")

    class Meta:
        model = Feedback
        fields = ("outcome", "price_per_report", "pricing_model", "comment")

    def validate_pricing_model(self, v):
        return v or ""          # the field is not nullable; "not answered" is stored as empty
