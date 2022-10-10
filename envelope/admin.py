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
        "online",
        "awol",
    )
    search_fields = (
        "user__first_name",
        "user__last_name",
        "user__username",
    )
