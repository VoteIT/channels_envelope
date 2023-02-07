from envelope.tests.helpers import load_doctests


def load_tests(loader, tests, pattern):
    from envelope import channels

    load_doctests(tests, channels)
    return tests
