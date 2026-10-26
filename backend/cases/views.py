"""Contract §2–§6: cases, flags, DRG, report + downloads, approve / return / feedback, firms, audit.

Firm isolation: every case query starts from `visible_cases(user)`; another
firm's case is a 404, never a 403, so nothing leaks."""
from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Firm, firm_of, is_staff_role
from accounts.serializers import FirmSerializer
from . import processing, reports, storage
from .audit import log
from .models import AuditEntry, Case, Flag
from .permissions import IsStaffRole
from .serializers import (CaseCreateSerializer, CaseDetailSerializer, CaseSummarySerializer, DrgConfirmSerializer,
                          FeedbackSerializer, FlagSerializer, LineSerializer, NoteSerializer, ReturnSerializer,
                          StaySerializer)


class Page(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200


def visible_cases(user):
    qs = Case.objects.select_related("firm", "approved_by").prefetch_related("files", "flags")
    if is_staff_role(user):
        return qs
    firm = firm_of(user)
    return qs.filter(firm=firm) if firm else qs.none()


def get_case(request, pk) -> Case:
    return get_object_or_404(visible_cases(request.user), pk=pk)


class CaseList(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        qs = visible_cases(request.user)
        st = request.query_params.get("status")
        if st:
            qs = qs.filter(status__in=[s.strip() for s in st.split(",") if s.strip()])
        q = request.query_params.get("search")
        if q:
            qs = qs.filter(Q(case_number__icontains=q) | Q(matter_ref__icontains=q) | Q(hospital_name__icontains=q) | Q(payer_name__icontains=q))
        firm = request.query_params.get("firm")
        if firm and is_staff_role(request.user):
            if not firm.isdigit():
                return Response({"detail": "firm must be a number."}, status=400)
            qs = qs.filter(firm_id=int(firm))
        pg = Page()
        page = pg.paginate_queryset(qs.order_by("-created_at"), request, view=self)
        return pg.get_paginated_response(CaseSummarySerializer(page, many=True).data)

    def post(self, request):
        s = CaseCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if is_staff_role(request.user):
            if not d.get("firm_id"):
                return Response({"firm_id": ["Pick the firm this bill belongs to."]}, status=400)
            firm = get_object_or_404(Firm, pk=d["firm_id"])
        else:
            firm = firm_of(request.user)
            if firm is None:
                raise PermissionDenied("Your account is not linked to a firm.")
        with transaction.atomic():
            case = Case.objects.create(case_number=Case.next_number(), firm=firm, created_by=request.user,
                                       matter_ref=d.get("matter_ref", ""), report_for=d["report_for"],
                                       consent=True, consent_at=timezone.now())
            bill = storage.save(case, "bill", d["bill"])
            eob = storage.save(case, "eob", d["eob"]) if d.get("eob") else None
        log(request.user, "Bill uploaded", f"{bill.name} · consent recorded" + (f" · EOB {eob.name}" if eob else ""), case)
        processing.start(case, user=request.user)
        case.refresh_from_db()
        return Response(CaseSummarySerializer(case).data, status=status.HTTP_201_CREATED)


class CaseStats(APIView):
    permission_classes = [IsStaffRole]

    def get(self, request):
        now = timezone.now()
        month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        qs = Case.objects.all()
        return Response({
            "needs_review": qs.filter(status=Case.Status.NEEDS_REVIEW).count(),
            "processing": qs.filter(status__in=[Case.Status.UPLOADED, Case.Status.PROCESSING]).count(),
            "sent_this_month": qs.filter(status=Case.Status.SENT, sent_at__gte=month).count(),
            "billed_open_total": float(qs.filter(status__in=Case.OPEN_STATUSES).aggregate(t=Sum("billed_total"))["t"] or 0),
        })


def _released_or_staff(request, case):
    """Values, lines and the report are MeshKor's draft until the case is sent: firm users see them only then."""
    if is_staff_role(request.user) or case.status == Case.Status.SENT:
        return True
    raise PermissionDenied("The report is available once MeshKor has released it.")


class CaseDetail(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        case = get_case(request, pk)
        log(request.user, "Case viewed", "", case)
        data = CaseDetailSerializer(case).data
        if not is_staff_role(request.user) and case.status != Case.Status.SENT:
            # A firm user sees progress only: no draft totals, flags or internal notes before release.
            data["flags"], data["stay"] = [], None
            data["totals"] = {k: None for k in data["totals"]}
            if case.status in (Case.Status.ERROR, Case.Status.NO_PRICE_FILE):
                data["status_detail"] = "MeshKor is looking at this bill."
        return Response(data)


class CaseLines(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        case = get_case(request, pk)
        _released_or_staff(request, case)
        log(request.user, "Lines viewed", "", case)
        basis = request.query_params.get("basis", "service_date")
        if basis not in ("service_date", "estimate"):
            return Response({"detail": "basis must be service_date or estimate."}, status=400)
        return Response(LineSerializer(case.lines.filter(basis=basis), many=True).data)


class FlagResolve(APIView):
    permission_classes = [IsStaffRole]

    def post(self, request, pk, flag_id):
        case = get_case(request, pk)
        flag = get_object_or_404(Flag, pk=flag_id, case=case)
        s = NoteSerializer(data=request.data); s.is_valid(raise_exception=True)
        flag.resolved, flag.resolved_by, flag.resolved_at, flag.note = True, request.user, timezone.now(), s.validated_data["note"]
        flag.save()
        log(request.user, "Flag resolved", f"{flag.title}" + (f" · {flag.note}" if flag.note else ""), case)
        return Response(FlagSerializer(flag).data)


class DrgConfirm(APIView):
    permission_classes = [IsStaffRole]

    def post(self, request, pk):
        case = get_case(request, pk)
        stay = getattr(case, "stay", None)
        if stay is None:
            return Response({"detail": "This case has no inpatient stay."}, status=400)
        if case.status != Case.Status.NEEDS_REVIEW:
            return Response({"detail": f"The DRG can be confirmed only while the case is in review (now '{case.status}')."}, status=400)
        s = DrgConfirmSerializer(data=request.data); s.is_valid(raise_exception=True)
        drg = s.validated_data["ms_drg"]
        if drg != stay.ms_drg:
            old = stay.ms_drg
            processing.reprice(case, ms_drg=drg, user=request.user)   # values for the new DRG
            case.refresh_from_db()
            stay = getattr(case, "stay", None)
            if stay is None or case.status != Case.Status.NEEDS_REVIEW:
                return Response({"detail": case.status_detail or "Re-pricing failed."}, status=400)
            log(request.user, "DRG changed", f"MS-DRG {old or '—'} → {drg}", case)
            stay.ms_drg, stay.drg_source = drg, "reviewer"
        stay.drg_confirmed = True
        stay.save()
        now = timezone.now()
        case.flags.filter(kind="drg_check", resolved=False).update(resolved=True, resolved_by=request.user, resolved_at=now,
                                                                     note=f"MS-DRG {stay.ms_drg} confirmed")
        log(request.user, "DRG confirmed", f"MS-DRG {stay.ms_drg}", case)
        return Response(StaySerializer(stay).data)


class CaseReport(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        case = get_case(request, pk)
        _released_or_staff(request, case)
        log(request.user, "Report viewed", "", case)
        return Response(reports.build(case))


def _download_allowed(request, case):
    if is_staff_role(request.user):
        return True
    if case.status != Case.Status.SENT:
        raise PermissionDenied("The report is available once MeshKor has released it.")
    return True


class ReportPdf(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        case = get_case(request, pk)
        _download_allowed(request, case)
        data = reports.pdf_bytes(case, draft=case.status != Case.Status.SENT)
        name = f"{case.case_number}_valuation_report.pdf"
        log(request.user, "Report downloaded", name, case)
        resp = HttpResponse(data, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{name}"'
        return resp


class ReportCsv(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        case = get_case(request, pk)
        _download_allowed(request, case)
        name = f"{case.case_number}_data_appendix.csv"
        log(request.user, "Data appendix downloaded", name, case)
        resp = HttpResponse(reports.csv_bytes(case), content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="{name}"'
        return resp


class Approve(APIView):
    permission_classes = [IsStaffRole]

    def post(self, request, pk):
        case = get_case(request, pk)
        s = NoteSerializer(data=request.data); s.is_valid(raise_exception=True)
        if case.status == Case.Status.SENT:
            return Response({"detail": "This case was already sent."}, status=400)
        if case.status != Case.Status.NEEDS_REVIEW:
            return Response({"detail": f"A case in status '{case.status}' cannot be approved; it must be priced and reviewed first."}, status=400)
        open_flags = case.flags.filter(severity="check", resolved=False).count()
        if open_flags:
            return Response({"detail": f"{open_flags} flag(s) still need a decision."}, status=400)
        if getattr(settings, "MESHKOR_FOUR_EYES", False) and case.flags.filter(resolved_by=request.user).exists():
            return Response({"detail": "Another reviewer must approve a case whose flags you resolved."}, status=400)
        case.status, case.sent_at, case.approved_by, case.approval_note = Case.Status.SENT, timezone.now(), request.user, s.validated_data["note"]
        case.status_detail = ""
        case.save()
        log(request.user, "Report approved and sent", s.validated_data["note"], case)
        self._notify(case)
        return Response(CaseSummarySerializer(case).data)

    @staticmethod
    def _notify(case):
        to = [case.firm.contact_email] if case.firm.contact_email else []
        if case.created_by and case.created_by.email:
            to.append(case.created_by.email)
        if not to:
            return
        try:
            send_mail(f"MeshKor report ready: {case.case_number}",
                      f"The valuation report for matter {case.matter_ref or case.case_number} is ready.\n"
                      f"Sign in to the portal to download it: {getattr(settings, 'MESHKOR_PORTAL_URL', '')}",
                      None, sorted(set(to)), fail_silently=True)
        except Exception:  # noqa: BLE001
            pass


class Return(APIView):
    permission_classes = [IsStaffRole]

    def post(self, request, pk):
        case = get_case(request, pk)
        s = ReturnSerializer(data=request.data); s.is_valid(raise_exception=True)
        if case.status == Case.Status.SENT:
            return Response({"detail": "This case was already sent to the firm."}, status=400)
        case.status, case.status_detail = Case.Status.RETURNED, s.validated_data["note"]
        case.save()
        log(request.user, "Case returned", s.validated_data["note"], case)
        return Response(CaseSummarySerializer(case).data)


class FeedbackView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        case = get_case(request, pk)
        if case.status != Case.Status.SENT:
            return Response({"detail": "Feedback can be given once the report is sent."}, status=400)
        s = FeedbackSerializer(data=request.data); s.is_valid(raise_exception=True)
        s.save(case=case, user=request.user)
        log(request.user, "Feedback given", s.validated_data["outcome"], case)
        return Response(s.data, status=status.HTTP_201_CREATED)


class FirmList(APIView):
    permission_classes = [IsStaffRole]

    def get(self, request):
        return Response(FirmSerializer(Firm.objects.order_by("name"), many=True).data)


class AuditList(APIView):
    permission_classes = [IsStaffRole]

    def get(self, request):
        qs = AuditEntry.objects.select_related("case")
        c = request.query_params.get("case")
        if c:
            if not c.isdigit():
                return Response({"detail": "case must be a number."}, status=400)
            qs = qs.filter(case_id=int(c))
        pg = Page()
        page = pg.paginate_queryset(qs, request, view=self)
        return pg.get_paginated_response([{"at": e.at, "actor": e.actor, "action": e.action, "detail": e.detail,
                                           "case_number": e.case.case_number if e.case else None} for e in page])
