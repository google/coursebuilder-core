# Copyright 2013 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Unit tests for the Workflow class in models.courses."""

__author__ = 'Sean Lip (sll@google.com)'

import unittest

import yaml

from models.courses import LEGACY_HUMAN_GRADER_WORKFLOW
from models.courses import Workflow

DATE_FORMAT_ERROR = (
    'dates should be formatted as YYYY-MM-DD hh:mm (e.g. 1997-07-16 19:20) and '
    'be specified in the UTC timezone.'
)

ERROR_HEADER = 'Error validating workflow specification: '

MISSING_KEYS_PREFIX = 'missing key(s) for a peer-reviewed assessment:'


class DateTimeConversionTests(unittest.TestCase):
    """Unit tests for datetime conversion."""

    def test_valid_datetime(self):
        """Valid datetimes should be converted without problems."""
        workflow = Workflow('')
        date_obj = workflow._convert_date_string_to_datetime('2012-03-21 12:30')
        self.assertEqual(date_obj.year, 2012)
        self.assertEqual(date_obj.month, 3)
        self.assertEqual(date_obj.day, 21)
        self.assertEqual(date_obj.hour, 12)
        self.assertEqual(date_obj.minute, 30)

    def test_invalid_datetime(self):
        """Valid datetimes should be converted without problems."""
        invalid_date_strs = [
            'abc', '2012-13-31 12:30', '2012-12-31T12:30',
            '2012-13-31 12:30+0100']

        workflow = Workflow('')
        for date_str in invalid_date_strs:
            with self.assertRaises(Exception):
                workflow._convert_date_string_to_datetime(date_str)

    def test_no_timezone_set(self):
        """Parsed date strings should contain no timezone information."""
        workflow = Workflow('')
        date_obj = workflow._convert_date_string_to_datetime('2012-03-21 12:30')
        self.assertIsNone(date_obj.tzinfo)


class WorkflowValidationTests(unittest.TestCase):
    """Unit tests for workflow object validation."""

    def setUp(self):
        self.errors = []
        self.valid_human_review_workflow_dict = yaml.safe_load(
            LEGACY_HUMAN_GRADER_WORKFLOW)

    def assert_matching_errors(self, expected, actual):
        """Prepend the error prefix to the error messages, then compare them."""
        formatted_errors = []
        for error in expected:
            formatted_errors.append('%s%s' % (ERROR_HEADER, error))
        self.assertEqual(formatted_errors, actual)

    def to_yaml(self, adict):
        """Convert a dict to YAML."""
        return yaml.safe_dump(adict)

    def test_empty_string(self):
        """Validation should fail on an empty string."""
        workflow = Workflow('')
        workflow.validate(self.errors)
        self.assert_matching_errors(['missing key: grader.'], self.errors)

    def test_invalid_string(self):
        """Validation should fail for invalid YAML strings."""
        workflow = Workflow('(')
        workflow.validate(self.errors)
        self.assertTrue(self.errors)

    def test_not_dict(self):
        """Validation should fail for non-dict YAML strings."""
        yaml_strs = ['- first\n- second', 'grader']

        for yaml_str in yaml_strs:
            self.errors = []
            workflow = Workflow(yaml_str)
            workflow.validate(self.errors)
            self.assert_matching_errors(
                ['expected the YAML representation of a dict'], self.errors)

    def test_missing_grader_key(self):
        """Validation should fail for missing grader key."""
        workflow = Workflow(self.to_yaml({'not_grader': 'human'}))
        workflow.validate(self.errors)
        self.assert_matching_errors(['missing key: grader.'], self.errors)

    def test_auto_grader(self):
        """Validation should pass for an auto-graded assessment."""
        workflow = Workflow(self.to_yaml({'grader': 'auto'}))
        workflow.validate(self.errors)
        self.assertFalse(self.errors)

    def test_empty_submission_date_in_grader(self):
        """Validation should pass for empty submission date."""
        workflow = Workflow(self.to_yaml(
            {'grader': 'auto', 'submission_due_date': ''}))
        workflow.validate(self.errors)
        self.assertFalse(self.errors)

    def test_invalid_human_grader(self):
        """Validation should fail for invalid human grading specifications."""
        workflow = Workflow(self.to_yaml({'grader': 'human'}))
        workflow.validate(self.errors)
        self.assert_matching_errors([
            '%s matcher, review_min_count, review_window_mins, '
            'submission_due_date, review_due_date.' %
            MISSING_KEYS_PREFIX], self.errors)

        self.errors = []
        workflow = Workflow(self.to_yaml(
            {'grader': 'human', 'matcher': 'peer'}
        ))
        workflow.validate(self.errors)
        self.assert_matching_errors([
            '%s review_min_count, review_window_mins, submission_due_date, '
            'review_due_date.' % MISSING_KEYS_PREFIX], self.errors)

    def test_invalid_review_min_count(self):
        """Validation should fail for bad review_min_count values."""
        workflow_dict = self.valid_human_review_workflow_dict
        workflow_dict['review_min_count'] = 'test_string'
        workflow = Workflow(self.to_yaml(workflow_dict))
        workflow.validate(self.errors)
        self.assert_matching_errors(
            ['review_min_count should be an integer.'], self.errors)

        self.errors = []
        workflow_dict['review_min_count'] = -1
        workflow = Workflow(self.to_yaml(workflow_dict))
        workflow.validate(self.errors)
        self.assert_matching_errors(
            ['review_min_count should be a non-negative integer.'], self.errors)

        self.errors = []
        workflow_dict['review_min_count'] = 0
        workflow = Workflow(self.to_yaml(workflow_dict))
        workflow.validate(self.errors)
        self.assertFalse(self.errors)

    def test_invalid_review_window_mins(self):
        """Validation should fail for bad review_window_mins values."""
        workflow_dict = self.valid_human_review_workflow_dict
        workflow_dict['review_window_mins'] = 'test_string'
        workflow = Workflow(self.to_yaml(workflow_dict))
        workflow.validate(self.errors)
        self.assert_matching_errors(
            ['review_window_mins should be an integer.'], self.errors)

        self.errors = []
        workflow_dict['review_window_mins'] = -1
        workflow = Workflow(self.to_yaml(workflow_dict))
        workflow.validate(self.errors)
        self.assert_matching_errors(
            ['review_window_mins should be a non-negative integer.'],
            self.errors)

        self.errors = []
        workflow_dict['review_window_mins'] = 0
        workflow = Workflow(self.to_yaml(workflow_dict))
        workflow.validate(self.errors)
        self.assertFalse(self.errors)

    def test_invalid_date(self):
        """Validation should fail for invalid dates."""
        workflow_dict = self.valid_human_review_workflow_dict
        workflow_dict['submission_due_date'] = 'test_string'
        workflow = Workflow(self.to_yaml(workflow_dict))
        workflow.validate(self.errors)
        self.assert_matching_errors([DATE_FORMAT_ERROR], self.errors)

        self.errors = []
        workflow_dict = self.valid_human_review_workflow_dict
        workflow_dict['review_due_date'] = 'test_string'
        workflow = Workflow(self.to_yaml(workflow_dict))
        workflow.validate(self.errors)
        self.assert_matching_errors([DATE_FORMAT_ERROR], self.errors)

    def test_submission_date_after_review_date_fails(self):
        """Validation should fail if review date precedes submission date."""
        workflow_dict = self.valid_human_review_workflow_dict
        workflow_dict['submission_due_date'] = '2013-03-14 12:00'
        workflow_dict['review_due_date'] = '2013-03-13 12:00'
        workflow = Workflow(self.to_yaml(workflow_dict))
        workflow.validate(self.errors)
        self.assert_matching_errors(
            ['submission due date should be earlier than review due date.'],
            self.errors)

    def test_multiple_errors(self):
        """Validation should fail with multiple errors when appropriate."""
        workflow_dict = self.valid_human_review_workflow_dict
        workflow_dict['submission_due_date'] = '2013-03-14 12:00'
        workflow_dict['review_due_date'] = '2013-03-13 12:00'
        workflow_dict['review_window_mins'] = 'hello'
        workflow = Workflow(self.to_yaml(workflow_dict))
        workflow.validate(self.errors)
        self.assert_matching_errors(
            ['review_window_mins should be an integer; submission due date '
             'should be earlier than review due date.'],
            self.errors)

    def test_valid_human_grader(self):
        """Validation should pass for valid human grading specifications."""
        workflow_dict = self.valid_human_review_workflow_dict
        workflow = Workflow(self.to_yaml(workflow_dict))
        workflow.validate(self.errors)
        self.assertFalse(self.errors)
