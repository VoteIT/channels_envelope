from async_signals import Signal
from django.apps import apps
from django.test import TestCase
from envelope.core.message import AsyncRunnable
from envelope.decorators import add_message
from envelope.tests.helpers import TESTING_NS

beep = Signal(debug=True)


@add_message(TESTING_NS)
class Subclassed(AsyncRunnable):
    ...


class ReceiverAllMessageSubclassesTests(TestCase):
    @property
    def _fut(self):
        from envelope.decorators import receiver_all_message_subclasses

        return receiver_all_message_subclasses

    async def test_message_signal(self):
        L = []

        @self._fut(beep, sender=AsyncRunnable)
        async def add_kwargs(signal, sender, **kwargs):
            L.append((signal, sender, kwargs))

        app_config = apps.get_app_config("envelope")
        app_config.register_deferred_signals()

        await beep.send(sender=Subclassed, bla=1)
        self.assertEqual(1, len(L))
        event = L[0]

        self.assertEqual(beep, event[0])
        self.assertEqual(Subclassed, event[1])
        self.assertEqual({"bla": 1}, event[2])
