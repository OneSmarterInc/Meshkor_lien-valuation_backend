from django.contrib import admin

from .models import AuditEntry, Case, CaseFile, CaseLine, Feedback, Flag, Stay


class FileInline(admin.TabularInline):
    model = CaseFile
    extra = 0
    readonly_fields = ("kind", "name", "size_bytes", "sha256", "stored_path", "uploaded_at")
    can_delete = False


class FlagInline(admin.TabularInline):
    model = Flag
    extra = 0


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ("case_number", "firm", "status", "hospital_name", "ccn", "setting", "billed_total", "created_at", "sent_at")
    list_filter = ("status", "firm", "setting")
    search_fields = ("case_number", "matter_ref", "hospital_name", "payer_name")
    readonly_fields = ("case_number", "created_at", "updated_at", "consent_at")
    inlines = [FileInline, FlagInline]


@admin.register(CaseLine)
class CaseLineAdmin(admin.ModelAdmin):
    list_display = ("case", "basis", "line_no", "hcpcs", "revenue_code", "charge", "payer_rate", "medicare", "status")
    list_filter = ("basis", "status")


@admin.register(AuditEntry)
class AuditAdmin(admin.ModelAdmin):
    list_display = ("at", "actor", "action", "detail", "case")
    list_filter = ("action",)
    readonly_fields = ("at", "actor_user", "actor", "action", "detail", "case")

    def has_add_permission(self, r): return False
    def has_change_permission(self, r, obj=None): return False
    def has_delete_permission(self, r, obj=None): return False


admin.site.register(Stay)
admin.site.register(Feedback)
