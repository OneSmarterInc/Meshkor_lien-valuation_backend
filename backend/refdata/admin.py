from django.contrib import admin

from .models import DuckDBBuild, LoadRun, SourceFile, VerifyRun


@admin.register(SourceFile)
class SourceFileAdmin(admin.ModelAdmin):
    list_display = ("table", "period", "path", "short_hash", "size_bytes", "last_loaded_at")
    list_filter = ("table",)
    search_fields = ("path", "sha256")

    @admin.display(description="sha256")
    def short_hash(self, obj):
        return obj.sha256[:16]


@admin.register(LoadRun)
class LoadRunAdmin(admin.ModelAdmin):
    list_display = ("table", "status", "rows", "seconds", "started_at")
    list_filter = ("status", "table")
    readonly_fields = [f.name for f in LoadRun._meta.fields] + ["sources"]


@admin.register(DuckDBBuild)
class DuckDBBuildAdmin(admin.ModelAdmin):
    list_display = ("created_at", "size_bytes", "seconds")


@admin.register(VerifyRun)
class VerifyRunAdmin(admin.ModelAdmin):
    list_display = ("created_at", "passed", "failed", "not_run")
    readonly_fields = [f.name for f in VerifyRun._meta.fields]
