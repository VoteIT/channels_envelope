from datetime import timedelta

from django.core.management import BaseCommand
from django.utils.timezone import now
from envelope.models import Connection


class Command(BaseCommand):

    help = "Sync organisations with consumer endpoint"

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        probably_awol_ts = now() - timedelta(minutes=10)
        qs = Connection.objects.filter(
            online=True,
            last_action__lt=probably_awol_ts,
        )
        if qs.exists():
            print(f"Found {qs.count()} connections to mark as AWOL")
            qs.update(online=False, awol=True)
        else:
            print(f"No AWOL found")
