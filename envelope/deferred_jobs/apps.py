from django.apps import AppConfig


class EvenlopeDeferredJobsConfig(AppConfig):
    name = "envelope.deferred_jobs"

    def ready(self):
        from . import async_signals
        from . import jobs
