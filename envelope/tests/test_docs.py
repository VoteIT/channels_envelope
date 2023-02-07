import doctest
import os

from django.test import TestCase

from envelope.tests.helpers import load_doctests


class RunDocTests(TestCase):

    ROOT_RELATIVE = os.path.join("..", "..")
    FLAGS = (
        doctest.NORMALIZE_WHITESPACE
        | doctest.ELLIPSIS
        | doctest.FAIL_FAST
        | doctest.IGNORE_EXCEPTION_DETAIL
    )

    # def _docfile(self, fn):
    #     return os.path.join(self.DOCS_RELATIVE, fn)

    def _doctest_file(self, fn):
        doctest.testfile(os.path.join(self.ROOT_RELATIVE, fn), optionflags=self.FLAGS)

    def test_narrative_readme(self):
        ...
        # FIXME:
        # self._doctest_file("README.md")


def load_tests(loader, tests, pattern):
    import envelope

    load_doctests(
        tests,
        envelope,
        #ignore_names={"app", "channels", "consumer", "deferred_jobs", "tests"},
    )
    return tests
