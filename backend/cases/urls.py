from django.urls import path

from . import views as v

urlpatterns = [
    path("cases/", v.CaseList.as_view()),
    path("cases/stats/", v.CaseStats.as_view()),
    path("cases/<int:pk>/", v.CaseDetail.as_view()),
    path("cases/<int:pk>/lines/", v.CaseLines.as_view()),
    path("cases/<int:pk>/flags/<int:flag_id>/resolve/", v.FlagResolve.as_view()),
    path("cases/<int:pk>/drg/confirm/", v.DrgConfirm.as_view()),
    path("cases/<int:pk>/report/", v.CaseReport.as_view()),
    path("cases/<int:pk>/report.pdf", v.ReportPdf.as_view()),
    path("cases/<int:pk>/report.csv", v.ReportCsv.as_view()),
    path("cases/<int:pk>/approve/", v.Approve.as_view()),
    path("cases/<int:pk>/return/", v.Return.as_view()),
    path("cases/<int:pk>/feedback/", v.FeedbackView.as_view()),
    path("firms/", v.FirmList.as_view()),
    path("audit/", v.AuditList.as_view()),
    path("admin/payer-names/", v.PayerNames.as_view()),
    path("admin/payer-names/<int:pk>/", v.PayerNameDelete.as_view()),
    path("admin/payer-names/reprice/", v.PayerNameReprice.as_view()),
]
