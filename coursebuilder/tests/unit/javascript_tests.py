"""Unit tests for the javascript code."""

__author__ = 'John Orr (jorr@google.com)'

import os

import unittest

import appengine_config
from scripts import run_all_tests


class AllJavaScriptTests(unittest.TestCase):

    def karma_test(self, test_folder):
        karma_conf = os.path.join(
            appengine_config.BUNDLE_ROOT, 'tests', 'unit',
            'javascript_tests', test_folder, 'karma.conf.js')
        result, out = run_all_tests.run([
            'karma', 'start', karma_conf], verbose=False)
        if result != 0:
            raise Exception('Test failed: %s', out)

    def test_activity_generic(self):
        self.karma_test('assets_lib_activity_generic')

    def test_assessment_tags(self):
        self.karma_test('modules_assessment_tags')

    def test_butterbar(self):
        self.karma_test('assets_lib_butterbar')

    def test_certificate(self):
        self.karma_test('modules_certificate')

    def test_core_tags(self):
        self.karma_test('modules_core_tags')

    def test_dashboard(self):
        self.karma_test('modules_dashboard')

    def test_oeditor(self):
        self.karma_test('modules_oeditor')

    def test_questionnaire(self):
        self.karma_test('modules_questionnaire')

    def test_skill_map(self):
        self.karma_test(os.path.join('modules_skill_map', 'lesson_editor'))
        self.karma_test(
            os.path.join('modules_skill_map', 'student_skill_widget'))
