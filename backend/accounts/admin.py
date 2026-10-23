from django.contrib import admin

from .models import Firm, Profile


@admin.register(Firm)
class FirmAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_email", "created_at")
    search_fields = ("name",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "firm")
    list_filter = ("role", "firm")
    search_fields = ("user__email", "user__username")
