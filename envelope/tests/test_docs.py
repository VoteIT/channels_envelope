import doctest
import os
from pkgutil import walk_packages

from django.test import TestCase


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
        self._doctest_file("README.md")


def load_tests(loader, tests, pattern):
    import envelope

    load_doctests(tests, envelope)
    return tests


def load_doctests(tests, package) -> None:
    """
    Load doctests from a specific package/module. Must be called from a test_ file with the following function:

    def load_tests(loader, tests, pattern):
        load_doctests(tests, <module>)
        return tests

    Where module is envelope for instance.
    """
    opts = (
        doctest.NORMALIZE_WHITESPACE
        | doctest.ELLIPSIS
        | doctest.FAIL_FAST
        | doctest.IGNORE_EXCEPTION_DETAIL
    )
    for importer, name, ispkg in walk_packages(
        package.__path__, package.__name__ + "."
    ):
        tests.addTests(doctest.DocTestSuite(name, optionflags=opts))
