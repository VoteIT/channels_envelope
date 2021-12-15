from django.contrib import admin

from envelope.models import Connection


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "online",
        "awol",
        "online_at",
        "offline_at",
    )
    list_filter = (
        "user",
        "online",
        "awol",
    )
    search_fields = ("user",)
