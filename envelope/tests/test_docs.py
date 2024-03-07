import doctest
import os

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from envelope.testing import load_doctests
from envelope.testing import testing_channel_layers_setting

User = get_user_model()


class RunDocTests(TestCase):
    ROOT_RELATIVE = os.path.join("..", "..")
    FLAGS = (
        doctest.NORMALIZE_WHITESPACE
        | doctest.ELLIPSIS
        | doctest.FAIL_FAST
        | doctest.IGNORE_EXCEPTION_DETAIL
    )

    def setUp(self):
        self.user = User.objects.create(username="hello")
        self.client.force_login(self.user)

    def _doctest_file(self, fn):
        result = doctest.testfile(
            os.path.join(self.ROOT_RELATIVE, fn),
            optionflags=self.FLAGS,
            extraglobs={"test": self},
        )
        if result.failed:
            self.fail(f"DocTest {fn} has {result.failed} fails")

    @override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
    def test_narrative_readme(self):
        self._doctest_file("README.md")


def load_tests(loader, tests, pattern):
    import envelope

    load_doctests(tests, envelope)
    return tests
