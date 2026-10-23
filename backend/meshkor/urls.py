"""Step 1 has no web API (decision Oct 17, 2026). Only the admin site, to
browse load runs, source files and verify reports."""
from django.contrib import admin
from django.urls import path

admin.site.site_header = "MeshKor Step 1 — reference data"
urlpatterns = [path("admin/", admin.site.urls)]
