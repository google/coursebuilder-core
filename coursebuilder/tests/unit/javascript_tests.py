"""Unit tests for the javascript code."""

__author__ = 'John Orr (jorr@google.com)'


import subprocess
import unittest


class AllJavaScriptTests(unittest.TestCase):

    def test_all(self):
        subprocess.call([
            'karma', 'start',
            'experimental/coursebuilder/tests/unit/karma.conf.js'])
