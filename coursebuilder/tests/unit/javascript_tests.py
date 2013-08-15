"""Unit tests for the javascript code."""

__author__ = 'John Orr (jorr@google.com)'


import subprocess
import unittest


class AllJavaScriptTests(unittest.TestCase):

    def test_all(self):
        retcode = subprocess.call([
            'karma', 'start',
            'experimental/coursebuilder/tests/unit/karma.conf.js'])
        self.assertEqual(retcode, 0)
