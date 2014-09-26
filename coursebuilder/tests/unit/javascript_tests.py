"""Unit tests for the javascript code."""

__author__ = 'John Orr (jorr@google.com)'

import os

import subprocess
import unittest

import appengine_config


class AllJavaScriptTests(unittest.TestCase):

    def karma_test(self, test_folder):
        karma_conf = os.path.join(
            appengine_config.BUNDLE_ROOT, 'tests', 'unit',
            'javascript_tests', test_folder, 'karma.conf.js')
        self.assertEqual(0, subprocess.call(['karma', 'start', karma_conf]))

    def test_activity_generic(self):
        self.karma_test('assets_lib_activity_generic')

    def test_butterbar(self):
        self.karma_test('assets_lib_butterbar')

    def test_assessment_tags(self):
        self.karma_test('modules_assessment_tags')

    def test_certificate(self):
        self.karma_test('modules_certificate')

    def test_core_tags(self):
        self.karma_test('modules_core_tags')

    def test_dashboard(self):
        self.karma_test('modules_dashboard')

    def test_oeditor(self):
        self.karma_test('modules_oeditor')
