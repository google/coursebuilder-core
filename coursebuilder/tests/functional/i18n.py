# -*- coding: utf-8 -*-
# Copyright 2014 Google Inc. All Rights Reserved.
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

"""Tests related to content translation to multiple languages."""

__author__ = 'Pavel Simakov (psimakov@google.com)'


import json
import os
import yaml
import appengine_config
from common import schema_fields
from common import xcontent
from models import courses
from modules.dashboard.question_editor import McQuestionRESTHandler
from modules.i18n_dashboard import i18n_dashboard
from tests.functional import actions


COURSE_NAME = 'i18n_tests'
NAMESPACE = 'ns_%s' % COURSE_NAME
COURSE_TITLE = 'I18N Tests'
ADMIN_EMAIL = 'admin@foo.com'
BASE_URL = '/' + COURSE_NAME
STUDENT_EMAIL = 'foo@foo.com'


def _filter(binding):
    """Filter out translatable strings."""
    return i18n_dashboard.TRANSLATABLE_FIELDS_FILTER.\
        filter_value_to_type_binding(binding)


class I18NCourseSettingsTests(actions.TestBase):
    """Tests for various course settings transformations I18N relies upon."""

    def _build_mapping(self, translations=None, errors=None):
        """Build mapping of course.yaml properties to their translations."""
        if translations is None:
            translations = {}
        binding = schema_fields.ValueToTypeBinding.bind_entity_to_schema(
            self.course_yaml, self.schema)
        desired = _filter(binding)
        mappings = xcontent.SourceToTargetDiffMapping.map_source_to_target(
            binding, existing_mappings=translations, allowed_names=desired,
            errors=errors)
        if errors:
            self.assertEqual(len(mappings) + len(errors), len(desired))
        else:
            self.assertEqual(len(mappings), len(desired))
        for mapping in mappings:
            self.assertTrue(mapping.name in desired)
        return binding, mappings

    def setUp(self):
        super(I18NCourseSettingsTests, self).setUp()
        context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, COURSE_TITLE)
        self.course = courses.Course(None, context)
        course_yaml = os.path.join(appengine_config.BUNDLE_ROOT, 'course.yaml')
        self.schema = courses.Course.create_settings_schema(self.course)
        self.schema.add_property(schema_fields.SchemaField(
            'test:i18n_test', 'Test Text', 'url', i18n=True))

        course_yaml_text = open(course_yaml).read()
        course_yaml_text = '%s\ntest:i18n_test:  \'Test!\'' % course_yaml_text
        self.course_yaml = yaml.safe_load(course_yaml_text)

    def tearDown(self):
        super(I18NCourseSettingsTests, self).tearDown()

    def test_course_yaml_schema_binding(self):
        binding = schema_fields.ValueToTypeBinding.bind_entity_to_schema(
            self.course_yaml, self.schema)

        expected_unmapped = set([
            'html_hooks:preview:after_main_content_ends',
            'html_hooks:preview:after_top_content_ends',
            'html_hooks:unit:after_content_begins',
            'html_hooks:unit:after_leftnav_begins',
            'html_hooks:unit:before_content_ends',
            'html_hooks:unit:before_leftnav_ends',
            'reg_form:whitelist',
          ])
        assert expected_unmapped.issubset(set(binding.unmapped_names))
        self.assertEqual(len(binding.name_to_field), len(binding.name_to_value))

        value = binding.find_value('test:i18n_test')
        self.assertTrue(value.field.i18n)
        self.assertEqual('url', value.field.type)
        self.assertEqual('Test!', value.value)
        self.assertEqual(binding.name_to_field['test:i18n_test'], value.field)

        value = binding.find_value('course:title')
        self.assertTrue(value.field.i18n is None)
        self.assertEqual('string', value.field.type)
        self.assertEqual('Power Searching with Google', value.value)
        self.assertEqual(binding.name_to_field['course:title'], value.field)

        forum_email_field = binding.find_field('course:forum_email')
        self.assertEquals('string', forum_email_field.type)
        blurb_field = binding.find_field('course:blurb')
        self.assertEquals('html', blurb_field.type)

    def test_extract_translatable_fields(self):
        binding = schema_fields.ValueToTypeBinding.bind_entity_to_schema(
            self.course_yaml, self.schema)
        value_names_to_translate = _filter(binding)
        self.assertTrue('course:locale' in binding.name_to_value)
        self.assertFalse('course:locale' in value_names_to_translate)
        self.assertTrue('course:title' in binding.name_to_value)
        self.assertTrue('course:title' in value_names_to_translate)

    def test_translate_never_before_translated(self):
        _, mappings = self._build_mapping()
        for mapping in mappings:
            self.assertEqual(
                mapping.verb, xcontent.SourceToTargetDiffMapping.VERB_NEW)
            self.assertEqual(mapping.target_value, None)

    def test_translations_must_have_same_type(self):
        translation = xcontent.SourceToTargetMapping(
            'course:title', 'Title', 'unknown_type',
            'Power Searching with Google', 'POWER SEARCHING WITH Google')
        errors = []
        binding, _ = self._build_mapping(
            translations=[translation], errors=errors)
        error_at_index = None
        for index, value_field in enumerate(binding.value_list):
            if 'course:title' == value_field.name:
                error_at_index = index
                break
        self.assertTrue(error_at_index is not None)
        self.assertEqual(error_at_index, errors[0].index)
        self.assertEqual(
            'Source and target types don\'t match: '
            'string, unknown_type.', errors[0].original_exception.message)

    def test_retranslate_already_translated_verb_same(self):
        translation = xcontent.SourceToTargetMapping(
            'course:title', 'Title', 'string',
            'Power Searching with Google', 'POWER SEARCHING WITH Google',)
        translations = [translation]

        _, mappings = self._build_mapping(translations)

        mapping = xcontent.SourceToTargetMapping.find_mapping(
            mappings, 'course:title')
        self.assertEqual(
            mapping.verb, xcontent.SourceToTargetDiffMapping.VERB_CURRENT)
        self.assertEqual('Power Searching with Google', mapping.source_value)
        self.assertEqual('POWER SEARCHING WITH Google', mapping.target_value)

        mapping = xcontent.SourceToTargetMapping.find_mapping(
            mappings, 'course:forum_email')
        self.assertEqual(
            mapping.verb, xcontent.SourceToTargetDiffMapping.VERB_NEW)
        self.assertEqual(None, mapping.target_value)

        mapping = xcontent.SourceToTargetMapping.find_mapping(
            mappings, 'course:locale')
        self.assertEqual(None, mapping)

    def test_retranslate_already_translated_verb_changed(self):
        translation = xcontent.SourceToTargetMapping(
            'course:title', 'Title', 'string',
            'Power Searching with Google (old)',
            'POWER SEARCHING WITH Google (old)')
        translations = [translation]

        _, mappings = self._build_mapping(translations)

        mapping = xcontent.SourceToTargetMapping.find_mapping(
            mappings, 'course:title')
        self.assertEqual(
            mapping.verb, xcontent.SourceToTargetDiffMapping.VERB_CHANGED)
        self.assertEqual('Power Searching with Google', mapping.source_value)
        self.assertEqual(
            'POWER SEARCHING WITH Google (old)', mapping.target_value)

    def test_schema_with_array_element_type(self):
        self.course_yaml['course']['extra_tabs'] = [
        {
            'label': 'FAQ',
            'position': 'left',
            'visibility': 'student',
            'url': '',
            'content': 'Frequently asked questions'},
        {
            'label': 'Resources',
            'position': 'right',
            'visibility': 'student',
            'url': '',
            'content': 'Links to resources'}]
        binding = schema_fields.ValueToTypeBinding.bind_entity_to_schema(
            self.course_yaml, self.schema)

        expected_names = [
            ('course:extra_tabs', None),
            ('course:extra_tabs:[0]:label', 'FAQ'),
            ('course:extra_tabs:[0]:position', 'left'),
            ('course:extra_tabs:[0]:visibility', 'student'),
            ('course:extra_tabs:[0]:url', ''),
            ('course:extra_tabs:[0]:content', 'Frequently asked questions'),
            ('course:extra_tabs:[1]:label', 'Resources'),
            ('course:extra_tabs:[1]:position', 'right'),
            ('course:extra_tabs:[1]:visibility', 'student'),
            ('course:extra_tabs:[1]:url', ''),
            ('course:extra_tabs:[1]:content', 'Links to resources')]
        for name, value in expected_names:
            self.assertIn(name, binding.name_to_field.keys())
            if value is not None:
                self.assertEquals(value, binding.name_to_value[name].value)


class I18NMultipleChoiceQuestionTests(actions.TestBase):
    """Tests for multiple choice object transformations I18N relies upon."""

    def setUp(self):
        super(I18NMultipleChoiceQuestionTests, self).setUp()
        self.schema = McQuestionRESTHandler.get_schema()
        self.question = json.loads("""{
            "description": "sky",
            "multiple_selections": false,
            "question": "What color is the sky?",
            "choices": [
                {"text": "red", "score": 0.0, "feedback": "Wrong!"},
                {"text": "blue", "score": 1.0, "feedback": "Correct!"},
                {"text": "green", "score": 0.0, "feedback": "Close..."}],
            "version": "1.5",
            "type": 0}
        """)

    def test_schema_with_array_element_type(self):
        binding = schema_fields.ValueToTypeBinding.bind_entity_to_schema(
            self.question, self.schema)

        expected_names = [
            'choices',
            'choices:[0]:feedback',
            'choices:[0]:score',
            'choices:[0]:text',
            'choices:[1]:feedback',
            'choices:[1]:score',
            'choices:[1]:text',
            'choices:[2]:feedback',
            'choices:[2]:score',
            'choices:[2]:text',
            'description',
            'multiple_selections',
            'question',
            'version']
        self.assertEquals(
            expected_names, sorted(binding.name_to_field.keys()))
        self.assertEquals(
            expected_names, sorted(binding.name_to_value.keys()))
        self.assertEquals(set(['type']), binding.unmapped_names)

        field = binding.find_field('choices')
        self.assertEqual('array', field.type)
        value = binding.find_value('choices')
        self.assertEqual(3, len(value.value))

        field = binding.find_field('choices:[0]:feedback')
        self.assertEqual('html', field.type)
        field = binding.find_field('choices:[0]:text')
        self.assertEqual('html', field.type)
        field = binding.find_field('choices:[0]:score')
        self.assertEqual('string', field.type)

        value = binding.find_value('choices:[1]:feedback')
        self.assertEqual('Correct!', value.value)
        value = binding.find_value('choices:[1]:text')
        self.assertEqual('blue', value.value)
        value = binding.find_value('choices:[1]:score')
        self.assertEqual(1.0, value.value)

    def test_translate_never_before_translated(self):
        binding = schema_fields.ValueToTypeBinding.bind_entity_to_schema(
            self.question, self.schema)
        desired = _filter(binding)
        expected_desired = [
            'choices:[0]:feedback',
            'choices:[0]:text',
            'choices:[1]:feedback',
            'choices:[1]:text',
            'choices:[2]:feedback',
            'choices:[2]:text',
            'description',
            'question']
        self.assertEqual(expected_desired, sorted(desired))

        mappings = xcontent.SourceToTargetDiffMapping.map_source_to_target(
            binding, allowed_names=desired)

        expected_source_values = [
            'sky',
            'What color is the sky?',
            'red',
            'Wrong!',
            'blue',
            'Correct!',
            'green',
            'Close...']
        self.assertEqual(
            expected_source_values,
            [mapping.source_value for mapping in mappings])

    def test_retranslate_already_translated_verb_same(self):
        binding = schema_fields.ValueToTypeBinding.bind_entity_to_schema(
            self.question, self.schema)
        desired = _filter(binding)
        translation = xcontent.SourceToTargetMapping(
            'choices:[1]:feedback', 'Feedback', 'html',
            'Correct!',
            'CORRECT!')
        mappings = xcontent.SourceToTargetDiffMapping.map_source_to_target(
            binding, existing_mappings=[translation], allowed_names=desired)

        expected_mappings = [
            (None, xcontent.SourceToTargetDiffMapping.VERB_NEW),
            (None, xcontent.SourceToTargetDiffMapping.VERB_NEW),
            (None, xcontent.SourceToTargetDiffMapping.VERB_NEW),
            (None, xcontent.SourceToTargetDiffMapping.VERB_NEW),
            (None, xcontent.SourceToTargetDiffMapping.VERB_NEW),
            ('CORRECT!', xcontent.SourceToTargetDiffMapping.VERB_CURRENT),
            (None, xcontent.SourceToTargetDiffMapping.VERB_NEW),
            (None, xcontent.SourceToTargetDiffMapping.VERB_NEW)]
        self.assertEqual(
            expected_mappings,
            [(mapping.target_value, mapping.verb) for mapping in mappings])

        mapping = xcontent.SourceToTargetMapping.find_mapping(
            mappings, 'choices:[1]:feedback')
        self.assertEqual(
            mapping.verb, xcontent.SourceToTargetDiffMapping.VERB_CURRENT)
        self.assertEqual('Correct!', mapping.source_value)
        self.assertEqual('CORRECT!', translation.target_value)

    def test_retranslate_already_translated_verb_changed(self):
        binding = schema_fields.ValueToTypeBinding.bind_entity_to_schema(
            self.question, self.schema)
        desired = _filter(binding)
        translation = xcontent.SourceToTargetMapping(
            'choices:[1]:feedback', 'Feedback', 'html',
            'Correct (old)!',
            'CORRECT (old)!')
        mappings = xcontent.SourceToTargetDiffMapping.map_source_to_target(
            binding, existing_mappings=[translation], allowed_names=desired)

        mapping = xcontent.SourceToTargetMapping.find_mapping(
            mappings, 'choices:[1]:feedback')
        self.assertEqual(
            mapping.verb, xcontent.SourceToTargetDiffMapping.VERB_CHANGED)
        self.assertEqual('Correct!', mapping.source_value)
        self.assertEqual('CORRECT (old)!', mapping.target_value)

    def test_retranslate_already_translated_with_list_reordered(self):
        binding = schema_fields.ValueToTypeBinding.bind_entity_to_schema(
            self.question, self.schema)
        desired = _filter(binding)
        translation = xcontent.SourceToTargetMapping(
            'choices:[0]:feedback', 'Feedback', 'html',
            'Correct (old)!',
            'CORRECT!')
        mappings = xcontent.SourceToTargetDiffMapping.map_source_to_target(
            binding, existing_mappings=[translation], allowed_names=desired)

        mapping = xcontent.SourceToTargetMapping.find_mapping(
            mappings, 'choices:[0]:feedback')
        self.assertEqual(
            mapping.verb, xcontent.SourceToTargetDiffMapping.VERB_CHANGED)
        self.assertEqual('Wrong!', mapping.source_value)
        self.assertEqual('CORRECT!', mapping.target_value)

    def test_retranslate_already_translated_with_list_reordered_matched(self):
        binding = schema_fields.ValueToTypeBinding.bind_entity_to_schema(
            self.question, self.schema)
        desired = _filter(binding)
        translation = xcontent.SourceToTargetMapping(
            'choices:[0]:feedback', 'Feedback', 'html',
            'Correct (old)!',
            'CORRECT!')
        try:
            mappings = xcontent.SourceToTargetDiffMapping.map_source_to_target(
                binding, existing_mappings=[translation], allowed_names=desired,
                allow_list_reorder=True)

            mapping = xcontent.SourceToTargetMapping.find_mapping(
                mappings, 'choices:[0]:feedback')
            self.assertEqual(
                mapping.verb, xcontent.SourceToTargetDiffMapping.VERB_CHANGED)
            self.assertEqual('Correct!', mapping.source_value)
            self.assertEqual('CORRECT!', mapping.target_value)

            raise Exception('Must have failed.')
            # TODO(psimakov): fix allow_list_reorder=True to stop this failure
        except NotImplementedError:
            pass
