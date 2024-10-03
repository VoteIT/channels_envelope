from django.contrib import admin
from envelope.models import Connection


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    search_fields = ("user__first_name", "user__last_name")
    autocomplete_fields = ("user",)
    list_filter = [
        "online",
        "awol",
        "online_at",
        "offline_at",
        "last_action",
    ]
    list_display = [
        "user",
        "online",
        "awol",
        "online_at",
        "offline_at",
        "last_action",
    ]
