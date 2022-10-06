from datetime import timedelta

from django.core.management import BaseCommand
from django.utils.timezone import now
from envelope.models import Connection


class Command(BaseCommand):

    help = "Mark connections with no action as awol"

    def handle(self, *args, **options):
        probably_awol_ts = now() - timedelta(minutes=20)
        qs = Connection.objects.filter(
            online=True,
            last_action__lt=probably_awol_ts,
        )
        if qs.exists():
            print(f"Found {qs.count()} connections to mark as AWOL")
            qs.update(online=False, awol=True)
        else:
            print(f"No AWOL found")
