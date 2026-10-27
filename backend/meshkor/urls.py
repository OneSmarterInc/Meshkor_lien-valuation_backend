"""URL map. /admin/ for staff browsing; /api/ is the lien portal API the React
frontend calls (docs/API_CONTRACT.md). Added Oct 23, 2026."""
from django.contrib import admin
from django.http import JsonResponse
from accounts.urls import admin_urlpatterns
from django.urls import include, path

from refdata.api import DataSourcesView

admin.site.site_header = "MeshKor — lien valuation"


def health(_):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health),
    path("api/auth/", include("accounts.urls")),
    path("api/admin/", include((admin_urlpatterns, "admin_api"))),
    path("api/", include("cases.urls")),
    path("api/data-sources/", DataSourcesView.as_view()),
]
