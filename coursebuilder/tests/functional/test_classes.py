# coding: utf-8
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

"""Tests that walk through Course Builder pages."""

__author__ = 'Sean Lip'

import __builtin__
import copy
import cStringIO
import csv
import datetime
import logging
import os
import re
import shutil
import sys
import time
import types
import urllib
import zipfile

import actions
from actions import assert_contains
from actions import assert_contains_all_of
from actions import assert_does_not_contain
from actions import assert_equals
from controllers_review import PeerReviewControllerTest
from controllers_review import PeerReviewDashboardAdminTest
from review_stats import PeerReviewAnalyticsTest

import appengine_config
from common import crypto
from common.utils import Namespace
from controllers import lessons
from controllers import sites
from controllers import utils
from controllers.utils import XsrfTokenManager
from models import config
from models import courses
from models import entities
from models import jobs
from models import models
from models import student_work
from models import transforms
from models import vfs
from models.courses import Course
import modules.admin.admin
from modules.announcements.announcements import AnnouncementEntity
import modules.oeditor.oeditor
from tools import verify
from tools.etl import etl
from tools.etl import etl_lib
from tools.etl import examples
from tools.etl import remote
from tools.etl import testing

from google.appengine.api import memcache
from google.appengine.api import namespace_manager
from google.appengine.ext import db


# A number of data files in a test course.
COURSE_FILE_COUNT = 70

# There is an expectation in our tests of automatic import of data/*.csv files,
# which is achieved below by selecting an alternative factory method.
courses.Course.create_new_default_course = (
    courses.Course.custom_new_default_course_for_test)


def _add_data_entity(app_context, entity_type, data):
    """Insert new entity into a given namespace."""
    old_namespace = namespace_manager.get_namespace()
    try:
        namespace_manager.set_namespace(app_context.get_namespace_name())

        new_object = entity_type()
        new_object.data = data
        new_object.put()
        return new_object
    finally:
        namespace_manager.set_namespace(old_namespace)


def _assert_identical_data_entity_exists(app_context, test_object):
    """Checks a specific entity exists in a given namespace."""
    old_namespace = namespace_manager.get_namespace()
    try:
        namespace_manager.set_namespace(app_context.get_namespace_name())

        entity_class = test_object.__class__
        existing_object = entity_class().get(test_object.key())
        assert existing_object
        assert existing_object.data == test_object.data
        assert existing_object.key().id() == test_object.key().id()
    finally:
        namespace_manager.set_namespace(old_namespace)


class InfrastructureTest(actions.TestBase):
    """Test core infrastructure classes agnostic to specific user roles."""

    def test_fs_cleaned_up_when_memcache_begin_or_end_asserts(self):
        # pylint: disable-msg=protected-access
        config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name] = True
        try:
            for method in [
                models.MemcacheManager.begin_readonly,
                models.MemcacheManager.end_readonly]:
                models.MemcacheManager.begin_readonly()
                models.MemcacheManager.set('a', 'aaa')

                # force error state
                models.MemcacheManager._READONLY_REENTRY_COUNT = -1

                with self.assertRaises(AssertionError):
                    method()

                self.assertEquals(None, models.MemcacheManager._LOCAL_CACHE)
                self.assertEquals(False, models.MemcacheManager._IS_READONLY)
                self.assertEquals(
                    0, models.MemcacheManager._READONLY_REENTRY_COUNT)
                self.assertEquals(
                    None, models.MemcacheManager._READONLY_APP_CONTEXT)
        finally:
            del config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name]

    def test_memcache_begin_end_reentrancy(self):
        # pylint: disable-msg=protected-access
        config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name] = True
        try:
            self.assertEquals(None, models.MemcacheManager._LOCAL_CACHE)
            models.MemcacheManager.begin_readonly()
            models.MemcacheManager.set('a', 'aaa')
            models.MemcacheManager.begin_readonly()
            self.assertEquals(
                'aaa', models.MemcacheManager._LOCAL_CACHE['']['a'])
            models.MemcacheManager.begin_readonly()
            self.assertEquals(
                'aaa', models.MemcacheManager._LOCAL_CACHE['']['a'])
            models.MemcacheManager.end_readonly()
            self.assertEquals(
                'aaa', models.MemcacheManager._LOCAL_CACHE['']['a'])
            models.MemcacheManager.end_readonly()
            self.assertEquals(
                'aaa', models.MemcacheManager._LOCAL_CACHE['']['a'])
            models.MemcacheManager.end_readonly()
            self.assertEquals(None, models.MemcacheManager._LOCAL_CACHE)
        finally:
            del config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name]

    def test_memcache_fails_missmatched_begin_end(self):
        # pylint: disable-msg=protected-access
        config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name] = True
        models.MemcacheManager.begin_readonly()
        models.MemcacheManager.set('a', 'aaa')
        models.MemcacheManager.end_readonly()
        with self.assertRaises(AssertionError):
            models.MemcacheManager.end_readonly()
        self.assertEquals(None, models.MemcacheManager._LOCAL_CACHE)
        del config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name]

    def test_memcache_can_be_cleared_if_end_readonly_is_not_called(self):
        # pylint: disable-msg=protected-access
        config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name] = True
        models.MemcacheManager.begin_readonly()
        models.MemcacheManager.set('a', 'aaa')
        models.MemcacheManager.begin_readonly()
        models.MemcacheManager.begin_readonly()
        self.assertEquals('aaa', models.MemcacheManager._LOCAL_CACHE['']['a'])
        models.MemcacheManager.clear_readonly_cache()
        del config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name]

    def test_memcache_get_all_caching(self):
        config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name] = True
        with Namespace('ns_test'):
            for index in range(0, 100):
                models.QuestionDAO.create_question(
                    {'data': 'data-%s' % index},
                    models.QuestionDTO.MULTIPLE_CHOICE)

            questions_1 = models.QuestionDAO.get_all()
            old_all = models.QuestionDAO.ENTITY.all
            models.QuestionDAO.ENTITY.all = None
            questions_2 = models.QuestionDAO.get_all()
            models.QuestionDAO.ENTITY.all = old_all

            self.assertEquals(100, len(questions_1))
            self.assertEquals(100, len(questions_2))
            for index in range(0, 100):
                self.assertEquals(
                      questions_1[index].dict,
                      questions_2[index].dict)
                self.assertEquals(
                      questions_1[index].id,
                      questions_2[index].id)

    def test_value_cached_in_one_namespace_invisible_in_another(self):
        """Value cached in one namespace is not visible in another."""

        # set value and check it's visible in one namespace
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace('test_memcache_manager_a')
            models.MemcacheManager.set('foo', 'bar')
            assert 'bar' == models.MemcacheManager.get('foo')
        finally:
            namespace_manager.set_namespace(old_namespace)

        # check same value is not visible in another namespace
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace('test_memcache_manager_b')
            assert not models.MemcacheManager.get('foo')
        finally:
            namespace_manager.set_namespace(old_namespace)

        # check same value is not visible in default namespace
        assert not models.MemcacheManager.get('foo')

        # check same value is not visible in None namespace
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(None)
            assert not models.MemcacheManager.get('foo')
        finally:
            namespace_manager.set_namespace(old_namespace)

        # set value and check it's visible in default namespace
        models.MemcacheManager.set('foo', 'bar')
        assert 'bar' == models.MemcacheManager.get('foo')

        # check value is not visible in another namespace
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace('test_memcache_manager_c')
            assert not models.MemcacheManager.get('foo')
        finally:
            namespace_manager.set_namespace(old_namespace)

    def test_response_content_type_is_application_json_in_utf_8(self):
        response = self.testapp.get(
            '/rest/config/item?key=gcb_config_update_interval_sec')
        self.assertEqual(
            'application/javascript; charset=utf-8',
            response.headers['Content-Type'])

    def test_xsrf_token_manager(self):
        """Test XSRF token operations."""

        # os.environ['AUTH_DOMAIN'] = 'test_domain'
        # os.environ['APPLICATION_ID'] = 'test app'

        # Issues and verify anonymous user token.
        action = 'test-action'
        token = utils.XsrfTokenManager.create_xsrf_token(action)
        assert '/' in token
        assert utils.XsrfTokenManager.is_xsrf_token_valid(token, action)

        # Impersonate real user.
        os.environ['USER_EMAIL'] = 'test_email'
        os.environ['USER_ID'] = 'test_id'

        # Issues and verify real user token.
        action = 'test-action'
        token = utils.XsrfTokenManager.create_xsrf_token(action)
        assert '/' in token
        assert utils.XsrfTokenManager.is_xsrf_token_valid(token, action)

        # Check forged time stamp invalidates token.
        parts = token.split('/')
        assert len(parts) == 2
        forgery = '%s/%s' % (long(parts[0]) + 1000, parts[1])
        assert forgery != token
        assert not utils.XsrfTokenManager.is_xsrf_token_valid(forgery, action)

        # Check token properly expires.
        action = 'test-action'
        time_in_the_past = long(
            time.time() - utils.XsrfTokenManager.XSRF_TOKEN_AGE_SECS)
        # pylint: disable=protected-access
        old_token = utils.XsrfTokenManager._create_token(
            action, time_in_the_past)
        assert not utils.XsrfTokenManager.is_xsrf_token_valid(old_token, action)

        # Clean up.
        # del os.environ['APPLICATION_ID']
        # del os.environ['AUTH_DOMAIN']
        del os.environ['USER_EMAIL']
        del os.environ['USER_ID']

    def test_import_course(self):
        """Tests importing one course into another."""

        # Setup courses.
        sites.setup_courses(
            'course:/a::ns_a, course:/b::ns_b, course:/c::ns_c, course:/:/')

        # Validate the courses before import.
        all_courses = sites.get_all_courses()
        dst_app_context_a = all_courses[0]
        dst_app_context_b = all_courses[1]
        dst_app_context_c = all_courses[2]
        src_app_context = all_courses[3]

        dst_course_a = courses.Course(None, app_context=dst_app_context_a)
        dst_course_b = courses.Course(None, app_context=dst_app_context_b)
        dst_course_c = courses.Course(None, app_context=dst_app_context_c)
        src_course = courses.Course(None, app_context=src_app_context)

        new_course_keys = [
            'admin_user_emails', 'announcement_list_email',
            'announcement_list_url', 'blurb', 'forum_email',
            'forum_embed_url', 'forum_url',
            'google_analytics_id', 'google_tag_manager_id',
            'instructor_details', 'main_video', 'start_date']
        init_settings = dst_course_a.app_context.get_environ()
        assert 'assessment_confirmations' not in init_settings
        for key in new_course_keys:
            assert key not in init_settings['course']

        assert not dst_course_a.get_units()
        assert not dst_course_b.get_units()
        assert 12 == len(src_course.get_units())

        # Import 1.2 course into 1.3.
        errors = []
        src_course_out, dst_course_out_a = dst_course_a.import_from(
            src_app_context, errors)
        if errors:
            raise Exception(errors)
        assert len(
            src_course.get_units()) == len(src_course_out.get_units())
        assert len(
            src_course_out.get_units()) == len(dst_course_out_a.get_units())

        final_settings = dst_course_a.app_context.get_environ()
        assert 'assessment_confirmations' in final_settings
        final_course_settings = set(
            init_settings['course'].keys()).intersection(
            set(final_settings['course'].keys()))
        self.assertEqual(
            set(init_settings['course'].keys()), final_course_settings)
        for key in new_course_keys:
            assert key in final_settings['course']

        # add dependent entities so we can check they make it through the import
        dependents = []
        for dependent_entity_class in courses.COURSE_CONTENT_ENTITIES:
            dependents.append(_add_data_entity(
                dst_course_out_a.app_context,
                dependent_entity_class, 'Test "%s"' % str(
                    dependent_entity_class)))
        assert dependents

        # Import 1.3 course into 1.3.
        errors = []
        src_course_out_a, dst_course_out_b = dst_course_b.import_from(
            dst_app_context_a, errors)
        if errors:
            raise Exception(errors)
        assert src_course_out_a.get_units() == dst_course_out_b.get_units()
        for dependent in dependents:
            _assert_identical_data_entity_exists(
                dst_course_out_b.app_context, dependent)

        # Import imported 1.3 course into 1.3.
        errors = []
        _, dst_course_out_c = dst_course_c.import_from(
            dst_app_context_b, errors)
        if errors:
            raise Exception(errors)
        assert dst_course_out_c.get_units() == dst_course_out_b.get_units()
        for dependent in dependents:
            _assert_identical_data_entity_exists(
                dst_course_out_c.app_context, dependent)

        # Test delete.
        units_to_delete = dst_course_a.get_units()
        deleted_count = 0
        for unit in units_to_delete:
            assert dst_course_a.delete_unit(unit)
            deleted_count += 1
        dst_course_a.save()
        assert deleted_count == len(units_to_delete)
        assert not dst_course_a.get_units()
        assert not dst_course_a.app_context.fs.list(os.path.join(
            dst_course_a.app_context.get_home(), 'assets/js/'))

        # Clean up.
        sites.reset_courses()

    def test_import_13_assessment(self):

        # Setup courses.
        sites.setup_courses('course:/a::ns_a, course:/b::ns_b, course:/:/')

        all_courses = sites.get_all_courses()
        src_app_context = all_courses[0]
        dst_app_context = all_courses[1]

        src_course = courses.Course(None, app_context=src_app_context)
        dst_course = courses.Course(None, app_context=dst_app_context)

        # Add an assessment
        src_assessment = src_course.add_assessment()
        self.assertEqual('A', src_assessment.type)
        src_assessment.title = 'Test Assessment'
        src_assessment.release_date = '2015-01-01 12:15'
        src_assessment.now_available = True
        src_assessment.properties = {'key': 'value'}
        src_assessment.weight = 3.14
        src_assessment.html_content = 'content'
        src_assessment.html_check_answers = 'check'
        src_assessment.html_review_form = 'review'
        src_assessment.workflow_yaml = 'a: 3'
        src_course.save()

        errors = []
        dst_course.import_from(src_app_context, errors)
        self.assertEqual(0, len(errors))

        dst_assessment = dst_course.find_unit_by_id(src_assessment.unit_id)
        self.assertEqual(src_assessment.__dict__, dst_assessment.__dict__)

    def test_import_13_lesson(self):

        # Setup courses.
        sites.setup_courses('course:/a::ns_a, course:/b::ns_b, course:/:/')

        all_courses = sites.get_all_courses()
        src_app_context = all_courses[0]
        dst_app_context = all_courses[1]

        src_course = courses.Course(None, app_context=src_app_context)
        dst_course = courses.Course(None, app_context=dst_app_context)

        # Add a unit
        src_unit = src_course.add_unit()
        src_lesson = src_course.add_lesson(src_unit)
        src_lesson.title = 'Test Lesson'
        src_lesson.scored = True
        src_lesson.objectives = 'objectives'
        src_lesson.video = 'video'
        src_lesson.notes = 'notes'
        src_lesson.duration = 'duration'
        src_lesson.now_available = True
        src_lesson.has_activity = True
        src_lesson.activity_title = 'activity title'
        src_lesson.activity_listed = False
        src_lesson.properties = {'key': 'value'}
        src_course.save()

        errors = []
        dst_course.import_from(src_app_context, errors)
        self.assertEqual(0, len(errors))

        dst_unit = dst_course.find_unit_by_id(src_unit.unit_id)
        dst_lesson = dst_course.find_lesson_by_id(
            dst_unit, src_lesson.lesson_id)
        assert not dst_lesson.has_activity
        assert not dst_lesson.activity_title
        src_dict = copy.deepcopy(src_lesson.__dict__)
        dst_dict = copy.deepcopy(dst_lesson.__dict__)
        del src_dict['has_activity']
        del src_dict['activity_title']
        del dst_dict['has_activity']
        del dst_dict['activity_title']
        self.assertEqual(src_dict, dst_dict)

    def test_create_new_course(self):
        """Tests creating a new course."""

        # Setup courses.
        sites.setup_courses('course:/test::ns_test, course:/:/')

        # Add several units.
        course = courses.Course(None, app_context=sites.get_all_courses()[0])
        link = course.add_link()
        unit = course.add_unit()
        assessment = course.add_assessment()
        course.save()
        assert course.find_unit_by_id(link.unit_id)
        assert course.find_unit_by_id(unit.unit_id)
        assert course.find_unit_by_id(assessment.unit_id)
        assert 3 == len(course.get_units())
        assert assessment.unit_id == 3

        # Check unit can be found.
        assert unit == course.find_unit_by_id(unit.unit_id)
        assert not course.find_unit_by_id(999)

        # Update unit.
        unit.title = 'Unit Title'
        unit.labels = 'foo, bar'
        course.update_unit(unit)
        course.save()
        assert 'Unit Title' == course.find_unit_by_id(unit.unit_id).title
        assert 'foo, bar' == course.find_unit_by_id(unit.unit_id).labels

        # Update link.
        link.title = 'Link Title'
        link.href = 'http://google.com'
        link.labels = 'bar, baz'
        course.update_unit(link)
        course.save()
        assert 'Link Title' == course.find_unit_by_id(link.unit_id).title
        assert 'http://google.com' == course.find_unit_by_id(link.unit_id).href
        assert 'bar, baz' == course.find_unit_by_id(link.unit_id).labels

        # Update assessment.
        assessment.title = 'Asmt. Title'
        assessment.labels = 'a, b, c'
        course.update_unit(assessment)
        course.save()
        assert 'Asmt. Title' == course.find_unit_by_id(assessment.unit_id).title
        assert 'a, b, c' == course.find_unit_by_id(assessment.unit_id).labels

        # Update assessment from file.
        assessment_content = open(os.path.join(
            appengine_config.BUNDLE_ROOT,
            'assets/js/assessment-Pre.js'), 'rb').readlines()
        assessment_content = u''.join(assessment_content)
        errors = []
        course.set_assessment_content(assessment, assessment_content, errors)
        course.save()
        assert not errors
        assessment_content_stored = course.app_context.fs.get(os.path.join(
            course.app_context.get_home(),
            course.get_assessment_filename(assessment.unit_id)))
        assert assessment_content == assessment_content_stored

        # Test adding lessons.
        lesson_a = course.add_lesson(unit)
        lesson_b = course.add_lesson(unit)
        lesson_c = course.add_lesson(unit)
        course.save()
        assert [lesson_a, lesson_b, lesson_c] == course.get_lessons(
            unit.unit_id)
        assert lesson_c.lesson_id == 6

        # Reorder lessons.
        new_order = [
            {'id': link.unit_id},
            {
                'id': unit.unit_id,
                'lessons': [
                    {'id': lesson_b.lesson_id},
                    {'id': lesson_a.lesson_id},
                    {'id': lesson_c.lesson_id}]},
            {'id': assessment.unit_id}]
        course.reorder_units(new_order)
        course.save()
        assert [lesson_b, lesson_a, lesson_c] == course.get_lessons(
            unit.unit_id)

        # Move lesson to another unit.
        another_unit = course.add_unit()
        course.move_lesson_to(lesson_b, another_unit)
        course.save()
        assert [lesson_a, lesson_c] == course.get_lessons(unit.unit_id)
        assert [lesson_b] == course.get_lessons(another_unit.unit_id)
        course.delete_unit(another_unit)
        course.save()

        # Make the course available.
        with actions.OverriddenEnvironment({'course': {'now_available': True}}):
            # Test public/private assessment.
            assessment_url = (
                '/test/' + course.get_assessment_filename(assessment.unit_id))
            assert not assessment.now_available
            response = self.get(assessment_url, expect_errors=True)
            assert_equals(response.status_int, 403)
            assessment = course.find_unit_by_id(assessment.unit_id)
            assessment.now_available = True
            course.update_unit(assessment)
            course.save()
            response = self.get(assessment_url)
            assert_equals(response.status_int, 200)

            # Check delayed assessment deletion.
            course.delete_unit(assessment)
            response = self.get(assessment_url)  # note: file is still available
            assert_equals(response.status_int, 200)
            course.save()
            response = self.get(assessment_url, expect_errors=True)
            assert_equals(response.status_int, 404)

            # Test public/private activity.
            lesson_a = course.find_lesson_by_id(None, lesson_a.lesson_id)
            lesson_a.now_available = False
            lesson_a.has_activity = True
            course.update_lesson(lesson_a)
            errors = []
            course.set_activity_content(lesson_a, u'var activity = []', errors)
            assert not errors
            activity_url = (
                '/test/' + course.get_activity_filename(
                    None, lesson_a.lesson_id))
            response = self.get(activity_url, expect_errors=True)
            assert_equals(response.status_int, 403)
            lesson_a = course.find_lesson_by_id(None, lesson_a.lesson_id)
            lesson_a.now_available = True
            course.update_lesson(lesson_a)
            course.save()
            response = self.get(activity_url)
            assert_equals(response.status_int, 200)

            # Check delayed activity.
            course.delete_lesson(lesson_a)
            response = self.get(activity_url)  # note: file is still available
            assert_equals(response.status_int, 200)
            course.save()
            response = self.get(activity_url, expect_errors=True)
            assert_equals(response.status_int, 404)

            # Test deletes removes all child objects.
            course.delete_unit(link)
            course.delete_unit(unit)
            assert not course.delete_unit(assessment)
            course.save()
            assert not course.get_units()
            assert not course.app_context.fs.list(os.path.join(
                course.app_context.get_home(), 'assets/js/'))

        # Clean up.
        sites.reset_courses()

    # pylint: disable-msg=too-many-statements
    def test_unit_lesson_not_available(self):
        """Tests that unavailable units and lessons behave correctly."""

        # Setup a new course.
        sites.setup_courses('course:/test::ns_test, course:/:/')
        self.base = '/test'
        config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name] = True

        app_context = sites.get_all_courses()[0]
        course = courses.Course(None, app_context=app_context)

        # Add a unit that is not available.
        unit_1 = course.add_unit()
        unit_1.now_available = False
        lesson_1_1 = course.add_lesson(unit_1)
        lesson_1_1.title = 'Lesson 1.1'
        course.update_unit(unit_1)

        # Add a unit with some lessons available and some lessons not available.
        unit_2 = course.add_unit()
        unit_2.now_available = True
        lesson_2_1 = course.add_lesson(unit_2)
        lesson_2_1.title = 'Lesson 2.1'
        lesson_2_1.now_available = False
        lesson_2_2 = course.add_lesson(unit_2)
        lesson_2_2.title = 'Lesson 2.2'
        lesson_2_2.now_available = True
        course.update_unit(unit_2)

        # Add a unit with all lessons not available.
        unit_3 = course.add_unit()
        unit_3.now_available = True
        lesson_3_1 = course.add_lesson(unit_3)
        lesson_3_1.title = 'Lesson 3.1'
        lesson_3_1.now_available = False
        course.update_unit(unit_3)

        # Add a unit that is available.
        unit_4 = course.add_unit()
        unit_4.now_available = True
        lesson_4_1 = course.add_lesson(unit_4)
        lesson_4_1.title = 'Lesson 4.1'
        lesson_4_1.now_available = True
        course.update_unit(unit_4)

        # Add an available unit with no lessons.
        unit_5 = course.add_unit()
        unit_5.now_available = True
        course.update_unit(unit_5)

        course.save()

        assert [lesson_1_1] == course.get_lessons(unit_1.unit_id)
        assert [lesson_2_1, lesson_2_2] == course.get_lessons(unit_2.unit_id)
        assert [lesson_3_1] == course.get_lessons(unit_3.unit_id)

        # Make the course available.
        with actions.OverriddenEnvironment({
                'course': {
                    'now_available': True,
                    'browsable': False}}):
            private_tag = 'id="lesson-title-private"'

            # Confirm private units are suppressed for user out of session
            response = self.get('preview')
            assert_equals(response.status_int, 200)
            assert_does_not_contain('Unit 1 - New Unit', response.body)
            assert_contains('Unit 2 - New Unit', response.body)
            assert_contains('Unit 3 - New Unit', response.body)
            assert_contains('Unit 4 - New Unit', response.body)
            assert_contains('Unit 5 - New Unit', response.body)

            # Simulate a student traversing the course.
            email = 'test_unit_lesson_not_available@example.com'
            name = 'Test Unit Lesson Not Available'

            actions.login(email, is_admin=False)
            actions.register(self, name)

            # Accessing a unit that is not available redirects to the main page.
            response = self.get('unit?unit=%s' % unit_1.unit_id)
            assert_equals(response.status_int, 302)

            response = self.get('unit?unit=%s' % unit_2.unit_id)
            assert_equals(response.status_int, 200)
            assert_contains('Lesson 2.1', response.body)
            assert_contains('This lesson is not available.', response.body)
            assert_does_not_contain(private_tag, response.body)

            response = self.get('unit?unit=%s&lesson=%s' % (
                unit_2.unit_id, lesson_2_2.lesson_id))
            assert_equals(response.status_int, 200)
            assert_contains('Lesson 2.2', response.body)
            assert_does_not_contain(
                'This lesson is not available.', response.body)
            assert_does_not_contain(private_tag, response.body)

            response = self.get('unit?unit=%s' % unit_3.unit_id)
            assert_equals(response.status_int, 200)
            assert_contains('Lesson 3.1', response.body)
            assert_contains('This lesson is not available.', response.body)
            assert_does_not_contain(private_tag, response.body)

            response = self.get('unit?unit=%s' % unit_4.unit_id)
            assert_equals(response.status_int, 200)
            assert_contains('Lesson 4.1', response.body)
            assert_does_not_contain(
                'This lesson is not available.', response.body)
            assert_does_not_contain(private_tag, response.body)

            response = self.get('unit?unit=%s' % unit_5.unit_id)
            assert_equals(response.status_int, 200)
            assert_does_not_contain('Lesson', response.body)
            assert_contains('This unit has no content.', response.body)
            assert_does_not_contain(private_tag, response.body)

            actions.logout()

            # Simulate an admin traversing the course.
            email = 'test_unit_lesson_not_available@example.com_admin'
            name = 'Test Unit Lesson Not Available Admin'

            actions.login(email, is_admin=True)
            actions.register(self, name)

            # The course admin can access a unit that is not available.
            response = self.get('unit?unit=%s' % unit_1.unit_id)
            assert_equals(response.status_int, 200)
            assert_contains('Lesson 1.1', response.body)

            response = self.get('unit?unit=%s' % unit_2.unit_id)
            assert_equals(response.status_int, 200)
            assert_contains('Lesson 2.1', response.body)
            assert_does_not_contain(
                'This lesson is not available.', response.body)
            assert_contains(private_tag, response.body)

            response = self.get('unit?unit=%s&lesson=%s' % (
                unit_2.unit_id, lesson_2_2.lesson_id))
            assert_equals(response.status_int, 200)
            assert_contains('Lesson 2.2', response.body)
            assert_does_not_contain(
                'This lesson is not available.', response.body)
            assert_does_not_contain(private_tag, response.body)

            response = self.get('unit?unit=%s' % unit_3.unit_id)
            assert_equals(response.status_int, 200)
            assert_contains('Lesson 3.1', response.body)
            assert_does_not_contain(
                'This lesson is not available.', response.body)
            assert_contains(private_tag, response.body)

            response = self.get('unit?unit=%s' % unit_4.unit_id)
            assert_equals(response.status_int, 200)
            assert_contains('Lesson 4.1', response.body)
            assert_does_not_contain(
                'This lesson is not available.', response.body)
            assert_does_not_contain(private_tag, response.body)

            response = self.get('unit?unit=%s' % unit_5.unit_id)
            assert_equals(response.status_int, 200)
            assert_does_not_contain('Lesson', response.body)
            assert_contains('This unit has no content.', response.body)
            assert_does_not_contain(private_tag, response.body)

            actions.logout()

    # pylint: disable-msg=too-many-statements
    def test_custom_assessments(self):
        """Tests that custom assessments are evaluated correctly."""

        # Setup a new course.
        sites.setup_courses('course:/test::ns_test, course:/:/')
        self.base = '/test'
        self.namespace = 'ns_test'
        config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name] = True

        app_context = sites.get_all_courses()[0]
        course = courses.Course(None, app_context=app_context)

        email = 'test_assessments@google.com'
        name = 'Test Assessments'

        assessment_1 = course.add_assessment()
        assessment_1.title = 'first'
        assessment_1.now_available = True
        assessment_1.weight = 0
        assessment_2 = course.add_assessment()
        assessment_2.title = 'second'
        assessment_2.now_available = True
        assessment_2.weight = 0
        course.save()
        assert course.find_unit_by_id(assessment_1.unit_id)
        assert course.find_unit_by_id(assessment_2.unit_id)
        assert 2 == len(course.get_units())

        # Make the course available.
        with actions.OverriddenEnvironment({'course': {'now_available': True}}):
            first = {'score': '1.00', 'assessment_type': assessment_1.unit_id}
            second = {'score': '3.00', 'assessment_type': assessment_2.unit_id}

            # Update assessment 1.
            assessment_1_content = open(os.path.join(
                appengine_config.BUNDLE_ROOT,
                'assets/js/assessment-Pre.js'), 'rb').readlines()
            assessment_1_content = u''.join(assessment_1_content)
            errors = []
            course.set_assessment_content(
                assessment_1, assessment_1_content, errors)
            course.save()
            assert not errors

            # Update assessment 2.
            assessment_2_content = open(os.path.join(
                appengine_config.BUNDLE_ROOT,
                'assets/js/assessment-Mid.js'), 'rb').readlines()
            assessment_2_content = u''.join(assessment_2_content)
            errors = []
            course.set_assessment_content(
                assessment_2, assessment_2_content, errors)
            course.save()
            assert not errors

            # Register.
            actions.login(email)
            actions.register(self, name)

            # Submit assessment 1.
            actions.submit_assessment(self, assessment_1.unit_id, first)
            student = (
                models.StudentProfileDAO.get_enrolled_student_by_email_for(
                    email, app_context))
            student_scores = course.get_all_scores(student)

            assert len(student_scores) == 2

            assert student_scores[0]['id'] == str(assessment_1.unit_id)
            assert student_scores[0]['score'] == 1
            assert student_scores[0]['title'] == 'first'
            assert student_scores[0]['weight'] == 0

            assert student_scores[1]['id'] == str(assessment_2.unit_id)
            assert student_scores[1]['score'] == 0
            assert student_scores[1]['title'] == 'second'
            assert student_scores[1]['weight'] == 0

            # The overall score is None if there are no weights assigned to any
            # of the assessments.
            overall_score = course.get_overall_score(student)
            assert overall_score is None

            # View the student profile page.
            response = self.get('student/home')
            assert_does_not_contain('Overall course score', response.body)

            # Add a weight to the first assessment.
            assessment_1.weight = 10
            overall_score = course.get_overall_score(student)
            assert overall_score == 1

            # Submit assessment 2.
            actions.submit_assessment(self, assessment_2.unit_id, second)
            # We need to reload the student instance, because its properties
            # have changed.
            student = (
                models.StudentProfileDAO.get_enrolled_student_by_email_for(
                    email, app_context))
            student_scores = course.get_all_scores(student)

            assert len(student_scores) == 2
            assert student_scores[1]['score'] == 3
            overall_score = course.get_overall_score(student)
            assert overall_score == 1

            # Change the weight of assessment 2.
            assessment_2.weight = 30
            overall_score = course.get_overall_score(student)
            assert overall_score == int((1 * 10 + 3 * 30) / 40)

            # Save all changes.
            course.save()

            # View the student profile page.
            response = self.get('student/home')
            assert_contains('assessment-score-first">1</span>', response.body)
            assert_contains('assessment-score-second">3</span>', response.body)
            assert_contains('Overall course score', response.body)
            assert_contains('assessment-score-overall">2</span>', response.body)

            # Submitting a lower score for any assessment does not change any of
            # the scores, since the system records the maximum score that has
            # ever been achieved on any assessment.
            first_retry = {
                'score': '0', 'assessment_type': assessment_1.unit_id}
            actions.submit_assessment(self, assessment_1.unit_id, first_retry)
            student = (
                models.StudentProfileDAO.get_enrolled_student_by_email_for(
                    email, app_context))
            student_scores = course.get_all_scores(student)

            assert len(student_scores) == 2
            assert student_scores[0]['id'] == str(assessment_1.unit_id)
            assert student_scores[0]['score'] == 1

            overall_score = course.get_overall_score(student)
            assert overall_score == int((1 * 10 + 3 * 30) / 40)

            actions.logout()

    def test_datastore_backed_file_system(self):
        """Tests datastore-backed file system operations."""
        fs = vfs.AbstractFileSystem(vfs.DatastoreBackedFileSystem('', '/'))

        # Check binary file.
        src = os.path.join(appengine_config.BUNDLE_ROOT, 'course.yaml')
        dst = os.path.join('/', 'course.yaml')

        fs.put(dst, open(src, 'rb'))
        stored = fs.open(dst)
        assert stored.metadata.size == len(open(src, 'rb').read())
        assert not stored.metadata.is_draft
        assert stored.read() == open(src, 'rb').read()

        # Check draft.
        fs.put(dst, open(src, 'rb'), is_draft=True)
        stored = fs.open(dst)
        assert stored.metadata.is_draft

        # Check text files with non-ASCII characters and encoding.
        foo_js = os.path.join('/', 'assets/js/foo.js')
        foo_text = u'This is a test text (тест данные).'
        fs.put(foo_js, vfs.string_to_stream(foo_text))
        stored = fs.open(foo_js)
        assert vfs.stream_to_string(stored) == foo_text

        # Check delete.
        del_file = os.path.join('/', 'memcache.test')
        fs.put(del_file, vfs.string_to_stream(u'test'))
        assert fs.isfile(del_file)
        fs.delete(del_file)
        assert not fs.isfile(del_file)

        # Check open or delete of non-existent does not fail.
        assert not fs.open('/foo/bar/baz')
        assert not fs.delete('/foo/bar/baz')

        # Check new content fully overrides old (with and without memcache).
        test_file = os.path.join('/', 'memcache.test')
        fs.put(test_file, vfs.string_to_stream(u'test text'))
        stored = fs.open(test_file)
        assert u'test text' == vfs.stream_to_string(stored)
        fs.delete(test_file)

        # Check file existence.
        assert not fs.isfile('/foo/bar')
        assert fs.isfile('/course.yaml')
        assert fs.isfile('/assets/js/foo.js')

        # Check file listing.
        bar_js = os.path.join('/', 'assets/js/bar.js')
        fs.put(bar_js, vfs.string_to_stream(foo_text))
        baz_js = os.path.join('/', 'assets/js/baz.js')
        fs.put(baz_js, vfs.string_to_stream(foo_text))
        assert fs.list('/') == sorted([
            u'/course.yaml',
            u'/assets/js/foo.js', u'/assets/js/bar.js', u'/assets/js/baz.js'])
        assert fs.list('/assets') == sorted([
            u'/assets/js/foo.js', u'/assets/js/bar.js', u'/assets/js/baz.js'])
        assert not fs.list('/foo/bar')

    def test_utf8_datastore(self):
        """Test writing to and reading from datastore using UTF-8 content."""
        event = models.EventEntity()
        event.source = 'test-source'
        event.user_id = 'test-user-id'
        event.data = u'Test Data (тест данные)'
        event.put()

        stored_event = models.EventEntity().get_by_id([event.key().id()])
        assert 1 == len(stored_event)
        assert event.data == stored_event[0].data

    def assert_queriable(self, entity, name, date_type=datetime.datetime):
        """Create some entities and check that single-property queries work."""
        for i in range(1, 32):
            item = entity(
                key_name='%s_%s' % (date_type.__class__.__name__, i))
            setattr(item, name, date_type(2012, 1, i))
            item.put()

        # Descending order.
        items = entity.all().order('-%s' % name).fetch(1000)
        assert len(items) == 31
        assert getattr(items[0], name) == date_type(2012, 1, 31)

        # Ascending order.
        items = entity.all().order('%s' % name).fetch(1000)
        assert len(items) == 31
        assert getattr(items[0], name) == date_type(2012, 1, 1)

    def test_indexed_properties(self):
        """Test whether entities support specific query types."""

        # A 'DateProperty' or 'DateTimeProperty' of each persistent entity must
        # be indexed. This is true even if the application doesn't execute any
        # queries relying on the index. The index is still critically important
        # for managing data, for example, for bulk data download or for
        # incremental computations. Using index, the entire table can be
        # processed in daily, weekly, etc. chunks and it is easy to query for
        # new data. If we did not have an index, chunking would have to be done
        # by the primary index, where it is impossible to separate recently
        # added/modified rows from the rest of the data. Having this index adds
        # to the cost of datastore writes, but we believe it is important to
        # have it. Below we check that all persistent date/datetime properties
        # are indexed.

        self.assert_queriable(
            AnnouncementEntity, 'date', date_type=datetime.date)
        self.assert_queriable(models.EventEntity, 'recorded_on')
        self.assert_queriable(models.Student, 'enrolled_on')
        self.assert_queriable(models.StudentAnswersEntity, 'updated_on')
        self.assert_queriable(jobs.DurableJobEntity, 'updated_on')

    def test_config_visible_from_any_namespace(self):
        """Test that ConfigProperty is visible from any namespace."""

        assert (
            config.UPDATE_INTERVAL_SEC.value ==
            config.UPDATE_INTERVAL_SEC.default_value)
        new_value = config.UPDATE_INTERVAL_SEC.default_value + 5

        # Add datastore override for known property.
        prop = config.ConfigPropertyEntity(
            key_name=config.UPDATE_INTERVAL_SEC.name)
        prop.value = str(new_value)
        prop.is_draft = False
        prop.put()

        # Check visible from default namespace.
        config.Registry.last_update_time = 0
        assert config.UPDATE_INTERVAL_SEC.value == new_value

        # Check visible from another namespace.
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(
                'ns-test_config_visible_from_any_namespace')

            config.Registry.last_update_time = 0
            assert config.UPDATE_INTERVAL_SEC.value == new_value
        finally:
            namespace_manager.set_namespace(old_namespace)


class AdminAspectTest(actions.TestBase):
    """Test site from the Admin perspective."""

    def test_appstats(self):
        """Checks that appstats is available when enabled."""
        email = 'test_appstats@google.com'

        # check appstats is disabled by default
        actions.login(email, is_admin=True)
        response = self.testapp.get('/admin')
        assert_equals(response.status_int, 200)
        assert_does_not_contain('>Appstats</a>', response.body)
        assert_does_not_contain('/admin/stats/', response.body)

        # enable and check appstats is now enabled
        os.environ['GCB_APPSTATS_ENABLED'] = 'True'
        response = self.testapp.get('/admin')
        assert_equals(response.status_int, 200)
        assert_contains('>Appstats</a>', response.body)
        assert_contains('/admin/stats/', response.body)
        del os.environ['GCB_APPSTATS_ENABLED']

    def test_courses_page_for_multiple_courses(self):
        """Tests /admin page showing multiple courses."""
        # Setup courses.
        sites.setup_courses('course:/aaa::ns_a, course:/bbb::ns_b, course:/:/')
        config.Registry.test_overrides[
            models.CAN_USE_MEMCACHE.name] = True

        # Validate the courses before import.
        all_courses = sites.get_all_courses()
        dst_app_context_a = all_courses[0]
        dst_app_context_b = all_courses[1]
        src_app_context = all_courses[2]

        # This test requires a read-write file system. If test runs on read-
        # only one, we can't run this test :(
        if (not dst_app_context_a.fs.is_read_write() or
            not dst_app_context_a.fs.is_read_write()):
            return

        course_a = courses.Course(None, app_context=dst_app_context_a)
        course_b = courses.Course(None, app_context=dst_app_context_b)

        unused_course, course_a = course_a.import_from(src_app_context)
        unused_course, course_b = course_b.import_from(src_app_context)

        # Rename courses.
        with Namespace(dst_app_context_a.get_namespace_name()):
            course_a.save_settings({'course': {'title': 'Course AAA'}})
        with Namespace(dst_app_context_b.get_namespace_name()):
            course_b.save_settings({'course': {'title': 'Course BBB'}})

        # Login.
        email = 'test_courses_page_for_multiple_courses@google.com'
        actions.login(email, is_admin=True)

        # Check the course listing page.
        response = self.testapp.get('/admin')
        assert_contains_all_of([
            'Course AAA',
            '/aaa/dashboard',
            'Course BBB',
            '/bbb/dashboard'], response.body)

        # Clean up.
        sites.reset_courses()

    def test_python_console(self):
        """Test access rights to the Python console."""

        email = 'test_python_console@google.com'

        # The default is that the console should be turned off
        self.assertFalse(modules.admin.admin.DIRECT_CODE_EXECUTION_UI_ENABLED)

        # Test the console when it is enabled
        modules.admin.admin.DIRECT_CODE_EXECUTION_UI_ENABLED = True

        # Check normal user has no access.
        actions.login(email)
        response = self.testapp.get('/admin?action=console')
        assert_equals(response.status_int, 302)

        response = self.testapp.post('/admin?action=console')
        assert_equals(response.status_int, 302)

        # Check delegated admin has no access.
        os.environ['gcb_admin_user_emails'] = '[%s]' % email
        actions.login(email)
        response = self.testapp.get('/admin?action=console')
        assert_equals(response.status_int, 200)
        assert_contains(
            'You must be an actual admin user to continue.', response.body)

        response = self.testapp.get('/admin?action=console')
        assert_equals(response.status_int, 200)
        assert_contains(
            'You must be an actual admin user to continue.', response.body)

        del os.environ['gcb_admin_user_emails']

        # Check actual admin has access.
        actions.login(email, is_admin=True)
        response = self.testapp.get('/admin?action=console')
        assert_equals(response.status_int, 200)

        response.form.set('code', 'print "foo" + "bar"')
        response = self.submit(response.form, response)
        assert_contains('foobar', response.body)

        # Finally, test that the console is not found when it is disabled
        modules.admin.admin.DIRECT_CODE_EXECUTION_UI_ENABLED = False

        actions.login(email, is_admin=True)
        self.testapp.get('/admin?action=console', status=404)
        self.testapp.post('/admin?action=console_run', status=404)

    def test_non_admin_has_no_access(self):
        """Test non admin has no access to pages or REST endpoints."""

        email = 'test_non_admin_has_no_access@google.com'
        actions.login(email)

        # Add datastore override.
        prop = config.ConfigPropertyEntity(
            key_name='gcb_config_update_interval_sec')
        prop.value = '5'
        prop.is_draft = False
        prop.put()

        # Check user has no access to specific pages and actions.
        response = self.testapp.get('/admin?action=settings')
        assert_equals(response.status_int, 302)

        response = self.testapp.get(
            '/admin?action=config_edit&name=gcb_admin_user_emails')
        assert_equals(response.status_int, 302)

        response = self.testapp.post(
            '/admin?action=config_reset&name=gcb_admin_user_emails')
        assert_equals(response.status_int, 302)

        # Check user has no rights to GET verb.
        response = self.testapp.get(
            '/rest/config/item?key=gcb_config_update_interval_sec')
        assert_equals(response.status_int, 200)
        json_dict = transforms.loads(response.body)
        assert json_dict['status'] == 401
        assert json_dict['message'] == 'Access denied.'

        # Here are the endpoints we want to test: (uri, xsrf_action_name).
        endpoints = [
            ('/rest/config/item', 'config-property-put'),
            ('/rest/courses/item', 'add-course-put')]

        # Check user has no rights to PUT verb.
        payload_dict = {}
        payload_dict['value'] = '666'
        payload_dict['is_draft'] = False
        request = {}
        request['key'] = 'gcb_config_update_interval_sec'
        request['payload'] = transforms.dumps(payload_dict)

        for uri, unused_action in endpoints:
            response = self.testapp.put(uri + '?%s' % urllib.urlencode(
                {'request': transforms.dumps(request)}), {})
            assert_equals(response.status_int, 200)
            assert_contains('"status": 403', response.body)

        # Check user still has no rights to PUT verb even if he somehow
        # obtained a valid XSRF token.
        for uri, action in endpoints:
            request['xsrf_token'] = XsrfTokenManager.create_xsrf_token(action)
            response = self.testapp.put(uri + '?%s' % urllib.urlencode(
                {'request': transforms.dumps(request)}), {})
            assert_equals(response.status_int, 200)
            json_dict = transforms.loads(response.body)
            assert json_dict['status'] == 401
            assert json_dict['message'] == 'Access denied.'

    def test_admin_list(self):
        """Test delegation of admin access to another user."""

        email = 'test_admin_list@google.com'
        actions.login(email)

        # Add environment variable override.
        os.environ['gcb_admin_user_emails'] = '[%s]' % email

        # Add datastore override.
        prop = config.ConfigPropertyEntity(
            key_name='gcb_config_update_interval_sec')
        prop.value = '5'
        prop.is_draft = False
        prop.put()

        # Check user has access now.
        response = self.testapp.get('/admin?action=settings')
        assert_equals(response.status_int, 200)

        # Check overrides are active and have proper management actions.
        assert_contains('gcb_admin_user_emails', response.body)
        assert_contains('[test_admin_list@google.com]', response.body)
        assert_contains(
            '/admin?action=config_override&amp;name=gcb_admin_user_emails',
            response.body)
        assert_contains(
            '/admin?action=config_edit&amp;name=gcb_config_update_interval_sec',
            response.body)

        # Check editor page has proper actions.
        response = self.testapp.get(
            '/admin?action=config_edit&amp;name=gcb_config_update_interval_sec')
        assert_equals(response.status_int, 200)
        assert_contains('/admin?action=config_reset', response.body)
        assert_contains('name=gcb_config_update_interval_sec', response.body)

        # Remove override.
        del os.environ['gcb_admin_user_emails']

        # Check user has no access.
        response = self.testapp.get('/admin?action=settings')
        assert_equals(response.status_int, 302)

    def test_access_to_admin_pages(self):
        """Test access to admin pages."""

        # assert anonymous user has no access
        response = self.testapp.get('/admin?action=settings')
        assert_equals(response.status_int, 302)

        # assert admin user has access
        email = 'test_access_to_admin_pages@google.com'
        name = 'Test Access to Admin Pages'

        actions.login(email, is_admin=True)
        actions.register(self, name)

        response = self.testapp.get('/admin')
        assert_contains('Power Searching with Google', response.body)
        assert_contains('All Courses', response.body)

        response = self.testapp.get('/admin?action=settings')
        assert_contains('gcb_admin_user_emails', response.body)
        assert_contains('gcb_config_update_interval_sec', response.body)
        assert_contains('All Settings', response.body)

        response = self.testapp.get('/admin?action=perf')
        assert_contains('gcb-admin-uptime-sec:', response.body)
        assert_contains('In-process Performance Counters', response.body)

        response = self.testapp.get('/admin?action=deployment')
        assert_contains('application_id: testbed-test', response.body)
        assert_contains('About the Application', response.body)

        actions.unregister(self)
        actions.logout()

        # assert not-admin user has no access
        actions.login(email)
        actions.register(self, name)
        response = self.testapp.get('/admin?action=settings')
        assert_equals(response.status_int, 302)

    def test_multiple_courses(self):
        """Test courses admin page with two courses configured."""

        sites.setup_courses(
            'course:/foo:/foo-data, course:/bar:/bar-data:nsbar')

        email = 'test_multiple_courses@google.com'

        actions.login(email, is_admin=True)
        response = self.testapp.get('/admin')
        assert_contains('Course Builder &gt; Admin &gt; Courses', response.body)
        assert_contains('Total: 2 item(s)', response.body)

        # Check ocurse URL's.
        assert_contains('<a href="/foo/dashboard">', response.body)
        assert_contains('<a href="/bar/dashboard">', response.body)

        # Check content locations.
        assert_contains('/foo-data', response.body)
        assert_contains('/bar-data', response.body)

        # Check namespaces.
        assert_contains('gcb-course-foo-data', response.body)
        assert_contains('nsbar', response.body)

        # Clean up.
        sites.reset_courses()

    def test_add_course(self):
        """Tests adding a new course entry."""

        if not self.supports_editing:
            return

        email = 'test_add_course@google.com'
        actions.login(email, is_admin=True)

        # Prepare request data.
        payload_dict = {
            'name': 'add_new',
            'title': u'new course (тест данные)', 'admin_email': 'foo@bar.com'}
        request = {}
        request['payload'] = transforms.dumps(payload_dict)
        request['xsrf_token'] = XsrfTokenManager.create_xsrf_token(
            'add-course-put')

        # Execute action.
        response = self.testapp.put('/rest/courses/item?%s' % urllib.urlencode(
            {'request': transforms.dumps(request)}), {})
        assert_equals(response.status_int, 200)

        # Check response.
        json_dict = transforms.loads(transforms.loads(response.body)['payload'])
        assert 'course:/add_new::ns_add_new' == json_dict.get('entry')

        # Re-execute action; should fail as this would create a duplicate.
        response = self.testapp.put('/rest/courses/item?%s' % urllib.urlencode(
            {'request': transforms.dumps(request)}), {})
        assert_equals(response.status_int, 200)
        assert_equals(412, transforms.loads(response.body)['status'])

        # Load the course and check its title.
        new_app_context = sites.get_all_courses(
            'course:/add_new::ns_add_new')[0]
        assert_equals(u'new course (тест данные)', new_app_context.get_title())
        new_course = courses.Course(None, app_context=new_app_context)
        assert not new_course.get_units()


class CourseAuthorAspectTest(actions.TestBase):
    """Tests the site from the Course Author perspective."""

    # pylint: disable-msg=too-many-statements
    def test_dashboard(self):
        """Test course dashboard."""

        email = 'test_dashboard@google.com'
        name = 'Test Dashboard'

        # Non-admin does't have access.
        actions.login(email)
        response = self.get('dashboard')
        assert_equals(response.status_int, 302)

        actions.register(self, name)
        assert_equals(response.status_int, 302)
        actions.logout()

        # Admin has access.
        actions.login(email, is_admin=True)
        response = self.get('dashboard')
        # Verify title does not have link text
        assert_contains(
            '<title>Course Builder &gt; Power Searching with Google &gt; Dash',
            response.body)
        # Verify body has breadcrumb trail.
        assert_contains('Google &gt; Dashboard &gt; Outline', response.body)

        # Tests outline view.
        response = self.get('dashboard')
        assert_contains('Unit 3 - Advanced techniques', response.body)
        assert_contains('data/lesson.csv', response.body)

        # Check editability.
        if self.supports_editing:
            assert_contains('Add Assessment', response.body)
        else:
            assert_does_not_contain('Add Assessment', response.body)

        # Test assets view.
        response = self.get('dashboard?action=assets&tab=css')
        # Verify title does not have link text
        assert_contains(
            '<title>Course Builder &gt; Power Searching with Google &gt; Dash',
            response.body)
        # Verify body has breadcrumb trail.
        assert_contains(
            'Google &gt; Dashboard &gt; Assets &gt; CSS', response.body)
        assert_contains('assets/css/main.css', response.body)
        response = self.get('dashboard?action=assets&tab=images')
        assert_contains('assets/img/Image1.5.png', response.body)
        response = self.get('dashboard?action=assets&tab=js')
        assert_contains('assets/lib/activity-generic-1.3.js', response.body)

        # Test settings view.
        response = self.get('dashboard?action=settings&tab=advanced')
        # Verify title does not have link text
        assert_contains(
            '<title>Course Builder &gt; Power Searching with Google &gt; Dash',
            response.body)
        # Verify body has breadcrumb trail.
        assert_contains('Google &gt; Dashboard &gt; Settings', response.body)
        assert_contains('course.yaml', response.body)
        assert_contains(
            'title: &#39;Power Searching with Google&#39;', response.body)
        assert_contains('locale: &#39;en_US&#39;', response.body)

        # Check editability.
        if self.supports_editing:
            assert_contains('create_or_edit_settings', response.body)
        else:
            assert_does_not_contain('create_or_edit_settings', response.body)

        # Tests student statistics view.
        response = self.get('dashboard?action=analytics&tab=students')
        # Verify title does not have link text
        assert_contains(
            '<title>Course Builder &gt; Power Searching with Google &gt; Dash',
            response.body)
        # Verify body has breadcrumb trail.
        assert_contains(
            'Google &gt; Dashboard &gt; Analytics &gt; Students',
            response.body)
        assert_contains('have not been calculated yet', response.body)

        response = response.forms[
            'gcb-generate-analytics-data'].submit().follow()
        assert len(self.taskq.GetTasks('default')) == 3

        response = self.get(response.request.url)
        assert_contains('is running', response.body)

        self.execute_all_deferred_tasks()

        response = self.get(response.request.url)
        assert_contains('were last updated at', response.body)
        assert_contains('currently enrolled: 1', response.body)
        assert_contains('total: 1', response.body)

        # Tests assessment statistics.
        old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace(self.namespace)
        try:
            for i in range(5):
                student = models.Student(key_name='key-%s' % i)
                student.is_enrolled = True
                student.scores = transforms.dumps({'test-assessment': i})
                student.put()
        finally:
            namespace_manager.set_namespace(old_namespace)

        response = self.get(response.request.url)
        response = response.forms[
            'gcb-generate-analytics-data'].submit().follow()

        self.execute_all_deferred_tasks()

        response = self.get(response.request.url)
        assert_contains('currently enrolled: 6', response.body)
        assert_contains(
            'test-assessment: completed 5, average score 2.0', response.body)

    def test_trigger_sample_announcements(self):
        """Test course author can trigger adding sample announcements."""
        email = 'test_announcements@google.com'
        name = 'Test Announcements'

        actions.login(email, is_admin=True)
        actions.register(self, name)

        response = actions.view_announcements(self)
        assert_contains('Example Announcement', response.body)
        assert_contains('Welcome to the final class!', response.body)
        assert_does_not_contain('No announcements yet.', response.body)

    def test_manage_announcements(self):
        """Test course author can manage announcements."""
        email = 'test_announcements@google.com'
        name = 'Test Announcements'

        actions.login(email, is_admin=True)
        actions.register(self, name)

        # add new
        response = actions.view_announcements(self)
        add_form = response.forms['gcb-add-announcement']
        response = self.submit(add_form)
        assert_equals(response.status_int, 302)

        # check edit form rendering
        response = self.testapp.get(response.location)
        assert_equals(response.status_int, 200)
        assert_contains('/rest/announcements/item?key=', response.body)

        # check added
        response = actions.view_announcements(self)
        assert_contains('Sample Announcement (Draft)', response.body)

        # delete draft
        response = actions.view_announcements(self)
        delete_form = response.forms['gcb-delete-announcement-1']
        response = self.submit(delete_form)
        assert_equals(response.status_int, 302)

        # check deleted
        assert_does_not_contain('Welcome to the final class!', response.body)

    def test_announcements_rest(self):
        """Test REST access to announcements."""
        email = 'test_announcements_rest@google.com'
        name = 'Test Announcements Rest'

        actions.login(email, is_admin=True)
        actions.register(self, name)

        response = actions.view_announcements(self)
        assert_does_not_contain('My Test Title', response.body)

        # REST GET existing item
        items = AnnouncementEntity.all().fetch(1)
        for item in items:
            response = self.get('rest/announcements/item?key=%s' % item.key())
            json_dict = transforms.loads(response.body)
            assert json_dict['status'] == 200
            assert 'message' in json_dict
            assert 'payload' in json_dict

            payload_dict = transforms.loads(json_dict['payload'])
            assert 'title' in payload_dict
            assert 'date' in payload_dict

            # REST PUT item
            payload_dict['title'] = u'My Test Title Мой заголовок теста'
            payload_dict['date'] = '2012/12/31'
            payload_dict['is_draft'] = True
            payload_dict['send_email'] = False
            request = {}
            request['key'] = str(item.key())
            request['payload'] = transforms.dumps(payload_dict)

            # Check XSRF is required.
            response = self.put('rest/announcements/item?%s' % urllib.urlencode(
                {'request': transforms.dumps(request)}), {})
            assert_equals(response.status_int, 200)
            assert_contains('"status": 403', response.body)

            # Check PUT works.
            request['xsrf_token'] = json_dict['xsrf_token']
            response = self.put('rest/announcements/item?%s' % urllib.urlencode(
                {'request': transforms.dumps(request)}), {})
            assert_equals(response.status_int, 200)
            assert_contains('"status": 200', response.body)

            # Confirm change is visible on the page.
            response = self.get('announcements')
            assert_contains(
                u'My Test Title Мой заголовок теста (Draft)', response.body)

        # REST GET not-existing item
        response = self.get('rest/announcements/item?key=not_existent_key')
        json_dict = transforms.loads(response.body)
        assert json_dict['status'] == 404


class CourseAuthorCourseCreationTest(actions.TestBase):

    def test_course_admin_can_create_another_course(self):
        admin_email = 'admin@foo.com'
        author_email = 'author@foo.com'
        actions.login(admin_email, is_admin=True)
        actions.simple_add_course('course_one', admin_email, 'Course One')
        actions.update_course_config('course_one', {
            'course': {'admin_user_emails': author_email}})

        # Login without super-admin authority; visit dashboard of course we
        # may edit.
        actions.login(author_email)
        response = self.get('/course_one/dashboard')
        response = self.click(response, 'Add Course')

        # Ensure that clicking on add-course link does not result in a 302
        # to '/', which would happen if we did not have access.
        self.assertEquals(200, response.status_int)
        self.assertEquals('http://localhost/admin?action=add_course',
                          response.request.url)

    def test_course_admin_does_not_see_courses_he_does_not_administer(self):
        admin_email = 'admin@foo.com'
        author_email = 'author@foo.com'
        actions.login(admin_email, is_admin=True)

        actions.simple_add_course('course_one', admin_email, 'Course One')
        actions.simple_add_course('course_two', admin_email, 'Course Two')
        actions.simple_add_course('course_three', admin_email, 'Course Three')
        actions.update_course_config('course_one', {
            'course': {'admin_user_emails': author_email}})
        actions.update_course_config('course_two', {
            'course': {'admin_user_emails': author_email}})

        actions.login(author_email)

        # Visit course_one's dashboard
        response = self.get('/course_one/dashboard')

        # Expect to be able to see peer course for which author has admin rights
        self.assertIn('Course Two', response.body)
        self.assertIn('/course_two', response.body)

        # But not peer course for which he does not.
        self.assertNotIn('Course Three', response.body)
        self.assertNotIn('/course_three', response.body)


class StudentAspectTest(actions.TestBase):
    """Test the site from the Student perspective."""

    def test_view_announcements(self):
        """Test student aspect of announcements."""

        email = 'test_announcements@google.com'
        name = 'Test Announcements'

        actions.login(email)
        actions.register(self, name)

        # Check no announcements yet.
        response = actions.view_announcements(self)
        assert_does_not_contain('Example Announcement', response.body)
        assert_does_not_contain('Welcome to the final class!', response.body)
        assert_contains('No announcements yet.', response.body)
        actions.logout()

        # Login as admin and add announcements.
        actions.login('admin@sample.com', is_admin=True)
        actions.register(self, 'admin')
        response = actions.view_announcements(self)
        actions.logout()

        # Check we can see non-draft announcements.
        actions.login(email)
        response = actions.view_announcements(self)
        assert_contains('Example Announcement', response.body)
        assert_does_not_contain('Welcome to the final class!', response.body)
        assert_does_not_contain('No announcements yet.', response.body)

        # Check no access to access to draft announcements via REST handler.
        items = AnnouncementEntity.all().fetch(1000)
        for item in items:
            response = self.get('rest/announcements/item?key=%s' % item.key())
            if item.is_draft:
                json_dict = transforms.loads(response.body)
                assert json_dict['status'] == 401
            else:
                assert_equals(response.status_int, 200)

    def test_registration(self):
        """Test student registration."""
        email = 'test_registration@example.com'
        name1 = 'Test Student'
        name2 = 'John Smith'
        name3 = u'Pavel Simakov (тест данные)'

        actions.login(email)

        # Verify registration is present on /course to unregistered student.
        response = self.get('course')
        self.assertIn('<a href="register">Registration</a>', response.body)

        actions.register(self, name1)
        actions.check_profile(self, name1)

        # Verify registration link is gone once registered.
        response = self.get('course')
        self.assertNotIn('<a href="register">Registration</a>', response.body)

        actions.change_name(self, name2)
        actions.unregister(self)

        actions.register(self, name3)
        actions.check_profile(self, name3)

    def test_course_not_available(self):
        """Tests course is only accessible to author when incomplete."""

        email = 'test_course_not_available@example.com'
        name = 'Test Course Not Available'

        actions.login(email)
        actions.register(self, name)

        # Check preview and static resources are available.
        response = self.get('course')
        assert_equals(response.status_int, 200)
        response = self.get('assets/js/activity-1.3.js')
        assert_equals(response.status_int, 200)

        # Override course.yaml settings by patching app_context.
        with actions.OverriddenEnvironment(
                {'course': {'now_available': False}}):
            # Check preview and static resources are not available to Student.
            response = self.get('course', expect_errors=True)
            assert_equals(response.status_int, 404)
            response = self.get('assets/js/activity-1.3.js', expect_errors=True)
            assert_equals(response.status_int, 404)

            # Check preview and static resources are still available to author.
            actions.login(email, is_admin=True)
            response = self.get('course')
            assert_equals(response.status_int, 200)
            response = self.get('assets/js/activity-1.3.js')
            assert_equals(response.status_int, 200)

    def test_registration_closed(self):
        """Test student registration when course is full."""

        email = 'test_registration_closed@example.com'
        name = 'Test Registration Closed'

        with actions.OverriddenEnvironment(
                {'reg_form': {'can_register': False}}):

            # Try to login and register.
            actions.login(email)
            try:
                actions.register(self, name)
                raise actions.ShouldHaveFailedByNow(
                    'Expected to fail: new registrations should not be allowed '
                    'when registration is closed.')
            except actions.ShouldHaveFailedByNow as e:
                raise e
            except:
                pass

            # Verify registration link not present on /course
            response = self.get('course')
            self.assertNotIn(
                '<a href="register">Registration</a>', response.body)

    def test_registration_with_additional_fields(self):
        """Registers a new student with customized registration form."""

        email = 'test_registration_with_additional_fields@example.com'
        name = 'Test Registration with Additional Fields'
        zipcode = '94043'
        score = '99'

        environ = {
            'course': {'browsable': False},
            'reg_form': {
                'additional_registration_fields': (
                    '\'<!-- reg_form.additional_registration_fields -->'
                    '<li>'
                    '<label class="form-label" for="form02"> '
                    'What is your zipcode?'
                    '</label><input name="form02" type="text"></li>'
                    '<li>'
                    '<label class="form-label" for="form03"> '
                    'What is your score?'
                    '</label> <input name="form03" type="text"></li>\'')
            }
        }
        with actions.OverriddenEnvironment(environ):
            # Login and register.
            actions.login(email)
            actions.register_with_additional_fields(self, name, zipcode, score)

            # Verify that registration results in capturing additional
            # registration questions.
            old_namespace = namespace_manager.get_namespace()
            namespace_manager.set_namespace(self.namespace)
            student = models.Student.get_enrolled_student_by_email(email)

            # Check that two registration additional fields are populated
            # with correct values.
            if student.additional_fields:
                json_dict = transforms.loads(student.additional_fields)
                assert zipcode == json_dict[2][1]
                assert score == json_dict[3][1]

        # Clean up app_context.
        namespace_manager.set_namespace(old_namespace)

    def test_permissions(self):
        """Test student permissions, and which pages they can view."""
        email = 'test_permissions@example.com'
        name = 'Test Permissions'

        with actions.OverriddenEnvironment({'course': {'browsable': False}}):
            actions.login(email)

            actions.register(self, name)
            actions.Permissions.assert_enrolled(self)

            actions.unregister(self)
            actions.Permissions.assert_unenrolled(self)

            actions.register(self, name)
            actions.Permissions.assert_enrolled(self)

    def test_login_and_logout(self):
        """Test if login and logout behave as expected."""

        with actions.OverriddenEnvironment({'course': {'browsable': False}}):
            email = 'test_login_logout@example.com'

            actions.Permissions.assert_logged_out(self)
            actions.login(email)

            actions.Permissions.assert_unenrolled(self)

            actions.logout()
            actions.Permissions.assert_logged_out(self)

    def assert_locale_settings(self):
        # Locale picker shown. Chooser shows only available locales.
        course_page = self.parse_html_string(self.get('course').body)
        locale_options = course_page.findall(
            './/select[@id="locale-select"]/option')
        self.assertEqual(2, len(locale_options))
        self.assertEquals('en_US', locale_options[0].attrib['value'])
        self.assertEquals('el', locale_options[1].attrib['value'])

        # Set language prefs using the REST endoint

        # A bad XSRF token is rejected
        request = {'xsrf_token': '1234'}
        response = transforms.loads(self.post(
            'rest/locale', {'request': transforms.dumps(request)}).body)
        self.assertEquals(403, response['status'])
        self.assertIn('Bad XSRF token', response['message'])

        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token('locales')

        # An unavailable locale is rejected
        request = {'xsrf_token': xsrf_token, 'payload': {'selected': 'fr'}}
        response = transforms.loads(self.post(
            'rest/locale', {'request': transforms.dumps(request)}).body)
        self.assertEquals(401, response['status'])
        self.assertIn('Bad locale', response['message'])

        # An available locale is accepted
        request = {'xsrf_token': xsrf_token, 'payload': {'selected': 'el'}}
        response = transforms.loads(self.post(
            'rest/locale', {'request': transforms.dumps(request)}).body)
        self.assertEquals(200, response['status'])
        self.assertIn('OK', response['message'])

        # After setting locale, visit course homepage and see new locale
        course_page = self.parse_html_string(self.get('course').body)
        self.assertEquals(
            u'Εγγραφή', course_page.find('.//a[@href="register"]').text)

    def test_locale_settings(self):

        extra_environ = {
            'course': {'locale': 'en_US', 'can_student_change_locale': True},
            'extra_locales': [
                {'locale': 'el', 'availability': 'available'},
                {'locale': 'fr', 'availability': 'unavailable'}]}

        with actions.OverriddenEnvironment(extra_environ):

            # Visit course home page with no locale settings and see the default
            # locale
            course_page = self.parse_html_string(self.get('course').body)
            self.assertEquals(
                'Registration', course_page.find('.//a[@href="register"]').text)

            # Visit course home page with accept-language set to an available
            # locale
            course_page = self.parse_html_string(
                self.get('course', headers={'Accept-Language': 'el'}).body)
            self.assertEquals(
                u'Εγγραφή', course_page.find('.//a[@href="register"]').text)

            # Visit course home page with accept-language set to an unavailable
            # locale
            course_page = self.parse_html_string(
                self.get('course', headers={'Accept-Language': 'fr'}).body)
            self.assertEquals(
                u'Registration',
                course_page.find('.//a[@href="register"]').text)

            actions.login('user@place.com')
            self.assert_locale_settings()

            actions.logout()
            self.assert_locale_settings()
            self.assertEquals('el', self.testapp.cookies['cb-user-locale'])

    def test_lesson_activity_navigation(self):
        """Test navigation between lesson/activity pages."""

        email = 'test_lesson_activity_navigation@example.com'
        name = 'Test Lesson Activity Navigation'

        actions.login(email)
        actions.register(self, name)

        response = self.get('unit?unit=1&lesson=1')
        assert_does_not_contain('Previous Page', response.body)
        assert_contains('Next Page', response.body)

        response = self.get('unit?unit=2&lesson=3')
        assert_contains('Previous Page', response.body)
        assert_contains('Next Page', response.body)

        response = self.get('unit?unit=3&lesson=5')
        assert_contains('Previous Page', response.body)
        assert_does_not_contain('Next Page', response.body)
        assert_contains('End', response.body)

    def test_unit_title_without_index(self):
        """Tests display of unit/lesson titles when unit index is not shown."""
        email = 'test_unit_title_without_index@example.com'
        name = 'test_unit_title_without_index'

        actions.login(email)
        actions.register(self, name)

        response = self.get('unit?unit=2&lesson=2')
        assert_contains('Unit 2 - Interpreting results', response.body)

        with actions.OverriddenEnvironment(
                {'course': {'display_unit_title_without_index': True}}):
            response = self.get('unit?unit=2&lesson=2')
            assert_does_not_contain(
                'Unit 2 - Interpreting results', response.body)
            assert_contains('Interpreting results', response.body)

    def test_lesson_title_without_auto_index(self):
        """Tests display of lesson title when auto indexing is disabled."""
        email = 'test_lesson_title_without_auto_index@example.com'
        name = 'test_lesson_title_without_auto_index'

        actions.login(email)
        actions.register(self, name)

        response = self.get('unit?unit=2&lesson=2')
        assert_contains('2.1 When search results', response.body)
        assert_contains('2.2 Thinking more', response.body)
        assert_contains('2.3 Understand options', response.body)

        old_load = courses.CourseModel12.load

        def new_load(unused_cls, app_context):
            """Modify auto indexing setting for one lesson."""
            course = old_load(app_context)
            lesson = course.get_lessons(2)[1]
            lesson._auto_index = False  # pylint: disable=protected-access
            return course

        courses.CourseModel12.load = types.MethodType(
            new_load, courses.CourseModel12)

        response = self.get('unit?unit=2&lesson=2')
        assert_contains('2.1 When search results', response.body)
        assert_does_not_contain('2.2 Thinking more', response.body)
        assert_contains('Thinking more', response.body)
        assert_contains('2.3 Understand options', response.body)

        courses.CourseModel12.load = old_load

    def test_show_hide_unit_links_on_sidebar(self):
        """Test display of unit links in side bar."""
        email = 'test_show_hide_unit_links_on_sidebar@example.com'
        name = 'Test Show/Hide of Unit Links on Side Bar'

        actions.login(email)
        actions.register(self, name)

        text_to_check = [
            'unit?unit=1', 'Unit 1 - ',
            'unit?unit=3', 'Unit 3 - ',
            'assessment?name=Mid', 'Mid-course assessment',
            'unit?unit=1&lesson=5', 'Word order matters',
            'unit?unit=3&lesson=4', 'OR and quotes'
            ]

        # The default behavior is to show links to other units and lessons.
        response = self.get('unit?unit=2')
        for item in text_to_check:
            assert_contains(item, response.body)

        with actions.OverriddenEnvironment(
                {'unit': {'show_unit_links_in_leftnav': False}}):

            # Check that now we don't have links to other units and lessons.
            response = self.get('unit?unit=2')
            for item in text_to_check:
                assert_does_not_contain(item, response.body)

    def test_show_hide_lesson_navigation(self):
        """Test display of lesson navigation buttons."""
        email = 'test_show_hide_of_lesson_navigation@example.com'
        name = 'Test Show/Hide of Lesson Navigation'

        actions.login(email)
        actions.register(self, name)

        # The default behavior is to show the lesson navigation buttons.
        response = self.get('unit?unit=2&lesson=3')
        assert_contains('<div class="gcb-prev-button">', response.body)
        assert_contains('<div class="gcb-next-button">', response.body)

        with actions.OverriddenEnvironment(
                {'unit': {'hide_lesson_navigation_buttons': True}}):

            # The lesson navigation buttons should now be hidden.
            response = self.get('unit?unit=2&lesson=3')
            assert_does_not_contain(
                '<div class="gcb-prev-button">', response.body)
            assert_does_not_contain(
                '<div class="gcb-next-button">', response.body)

    def test_attempt_activity_event(self):
        """Test activity attempt generates event."""

        email = 'test_attempt_activity_event@example.com'
        name = 'Test Attempt Activity Event'

        actions.login(email)
        actions.register(self, name)

        # Enable event recording.
        config.Registry.test_overrides[
            lessons.CAN_PERSIST_ACTIVITY_EVENTS.name] = True

        # Prepare event.
        request = {}
        request['source'] = 'test-source'
        request['payload'] = transforms.dumps({'Alice': u'Bob (тест данные)'})

        # Check XSRF token is required.
        response = self.post('rest/events?%s' % urllib.urlencode(
            {'request': transforms.dumps(request)}), {})
        assert_equals(response.status_int, 200)
        assert_contains('"status": 403', response.body)

        # Check PUT works.
        request['xsrf_token'] = XsrfTokenManager.create_xsrf_token(
            'event-post')
        response = self.post('rest/events?%s' % urllib.urlencode(
            {'request': transforms.dumps(request)}), {})
        assert_equals(response.status_int, 200)
        assert not response.body

        # Check event is properly recorded.
        old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace(self.namespace)
        try:
            events = models.EventEntity.all().fetch(1000)
            assert 1 == len(events)
            assert_contains(
                u'Bob (тест данные)',
                transforms.loads(events[0].data)['Alice'])
        finally:
            namespace_manager.set_namespace(old_namespace)

        # Clean up.
        config.Registry.test_overrides = {}

    def test_two_students_dont_see_each_other_pages(self):
        """Test a user can't see another user pages."""
        email1 = 'user1@foo.com'
        name1 = 'User 1'
        email2 = 'user2@foo.com'
        name2 = 'User 2'

        # Login as one user and view 'unit' and other pages, which are not
        # cached.
        actions.login(email1)
        actions.register(self, name1)
        actions.Permissions.assert_enrolled(self)
        response = actions.view_unit(self)
        assert_contains(email1, response.body)
        actions.logout()

        # Login as another user and check that 'unit' and other pages show
        # the correct new email.
        actions.login(email2)
        actions.register(self, name2)
        actions.Permissions.assert_enrolled(self)
        response = actions.view_unit(self)
        assert_contains(email2, response.body)
        actions.logout()

    def test_xsrf_defence(self):
        """Test defense against XSRF attack."""

        email = 'test_xsrf_defence@example.com'
        name = 'Test Xsrf Defence'

        actions.login(email)
        actions.register(self, name)

        response = self.get('student/home')

        edit_form = actions.get_form_by_action(response, 'student/editstudent')
        edit_form.set('name', 'My New Name')
        edit_form.set('xsrf_token', 'bad token')

        response = edit_form.submit(expect_errors=True)
        assert_equals(response.status_int, 403)

    def test_autoescaping(self):
        """Test Jinja autoescaping."""
        email = 'test_autoescaping@example.com'
        name1 = '<script>alert(1);</script>'
        name2 = '<script>alert(2);</script>'

        actions.login(email)

        actions.register(self, name1)
        actions.check_profile(self, name1)

        actions.change_name(self, name2)
        actions.unregister(self)

    def test_response_headers(self):
        """Test dynamically-generated responses use proper headers."""

        email = 'test_response_headers@example.com'
        name = 'Test Response Headers'

        actions.login(email)
        actions.register(self, name)

        response = self.get('student/home')
        assert_equals(response.status_int, 200)
        assert_contains('must-revalidate', response.headers['Cache-Control'])
        assert_contains('no-cache', response.headers['Cache-Control'])
        assert_contains('no-cache', response.headers['Pragma'])
        assert_contains('Mon, 01 Jan 1990', response.headers['Expires'])

    def test_browsability_permissions(self):
        """Tests that the course browsability flag works correctly."""

        # By default, courses are browsable.
        response = self.get('course')
        assert_equals(response.status_int, 200)
        assert_contains('<a href="assessment?name=Pre"', response.body)
        assert_does_not_contain('progress-notstarted-Pre', response.body)

        actions.Permissions.assert_can_browse(self)

        with actions.OverriddenEnvironment({'course': {'browsable': False}}):
            actions.Permissions.assert_logged_out(self)

            # Check course page redirects.
            response = self.get('course', expect_errors=True)
            assert_equals(response.status_int, 302)


class StudentUnifiedProfileTest(StudentAspectTest):
    """Tests student actions having unified profile enabled."""

    def setUp(self):  # pylint: disable=g-bad-name
        super(StudentUnifiedProfileTest, self).setUp()
        config.Registry.test_overrides[
            models.CAN_SHARE_STUDENT_PROFILE] = True

    def tearDown(self):  # pylint: disable=g-bad-name
        config.Registry.test_overrides = {}
        super(StudentUnifiedProfileTest, self).tearDown()


class StaticHandlerTest(actions.TestBase):
    """Check serving of static resources."""

    def test_disabled_modules_has_no_routes(self):
        """Test that disabled modules has no routes."""
        assert modules.oeditor.oeditor.custom_module.enabled
        assert modules.oeditor.oeditor.custom_module.global_routes
        assert modules.oeditor.oeditor.custom_module.namespaced_routes

        modules.oeditor.oeditor.custom_module.disable()
        try:
            assert not modules.oeditor.oeditor.custom_module.enabled
            assert not modules.oeditor.oeditor.custom_module.global_routes
            assert not modules.oeditor.oeditor.custom_module.namespaced_routes
        finally:
            modules.oeditor.oeditor.custom_module.enable()

    def test_static_files_cache_control(self):
        """Test static/zip handlers use proper Cache-Control headers."""

        def assert_response(response):
            assert_equals(response.status_int, 200)
            assert_contains('max-age=600', response.headers['Cache-Control'])
            assert_contains('public', response.headers['Cache-Control'])
            assert_does_not_contain('no-cache', str(response.headers))
            assert_does_not_contain('must-revalidate', str(response.headers))

        # static resourse on a namespaced route
        assert_response(self.get('/assets/css/main.css'))

        # static resource from the file system on a global route
        assert_response(self.testapp.get(
            '/modules/oeditor/resources/butterbar.js'))

        # static resource from the zip file on a global route; it requires login
        assert_response(self.testapp.get(
            '/static/inputex-3.1.0/src/inputex/assets/skins/sam/inputex.css'))


class ActivityTest(actions.TestBase):
    """Test for activities."""

    def get_activity(self, unit_id, lesson_id, args):
        """Retrieve the activity page for a given unit and lesson id."""

        response = self.get('activity?unit=%s&lesson=%s' % (unit_id, lesson_id))
        assert_equals(response.status_int, 200)
        assert_contains(
            '<script src="assets/js/activity-%s.%s.js"></script>' %
            (unit_id, lesson_id), response.body)
        assert_contains('assets/lib/activity-generic-1.3.js', response.body)

        js_response = self.get('assets/lib/activity-generic-1.3.js')
        assert_equals(js_response.status_int, 200)

        # Extract XSRF token from the page.
        match = re.search(r'eventXsrfToken = [\']([^\']+)', response.body)
        assert match
        xsrf_token = match.group(1)
        args['xsrf_token'] = xsrf_token

        return response, args

    def test_activities(self):
        """Test that activity submissions are handled and recorded correctly."""

        email = 'test_activities@google.com'
        name = 'Test Activities'
        unit_id = 1
        lesson_id = 2
        activity_submissions = {
            '1.2': {
                'index': 3,
                'type': 'activity-choice',
                'value': 3,
                'correct': True,
            },
        }

        # Register.
        actions.login(email)
        actions.register(self, name)

        # Enable event recording.
        config.Registry.test_overrides[
            lessons.CAN_PERSIST_ACTIVITY_EVENTS.name] = True

        # Navigate to the course overview page, and check that the unit shows
        # no progress yet.
        response = self.get('course')
        assert_equals(response.status_int, 200)
        assert_contains(
            u'id="progress-notstarted-%s"' % unit_id, response.body)

        old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace(self.namespace)
        try:
            response, args = self.get_activity(unit_id, lesson_id, {})

            # Check that the current activity shows no progress yet.
            assert_contains(
                u'id="progress-notstarted-%s-activity"' %
                lesson_id, response.body)

            # Prepare activity submission event.
            args['source'] = 'attempt-activity'
            lesson_key = '%s.%s' % (unit_id, lesson_id)
            assert lesson_key in activity_submissions
            args['payload'] = activity_submissions[lesson_key]
            args['payload']['location'] = (
                'http://localhost:8080/activity?unit=%s&lesson=%s' %
                (unit_id, lesson_id))
            args['payload'] = transforms.dumps(args['payload'])

            # Submit the request to the backend.
            response = self.post('rest/events?%s' % urllib.urlencode(
                {'request': transforms.dumps(args)}), {})
            assert_equals(response.status_int, 200)
            assert not response.body

            # Check that the current activity shows partial progress.
            response, args = self.get_activity(unit_id, lesson_id, {})
            assert_contains(
                u'id="progress-inprogress-%s-activity"' %
                lesson_id, response.body)

            # Navigate to the course overview page and check that the unit shows
            # partial progress.
            response = self.get('course')
            assert_equals(response.status_int, 200)
            assert_contains(
                u'id="progress-inprogress-%s"' % unit_id, response.body)
        finally:
            namespace_manager.set_namespace(old_namespace)

    # pylint: disable-msg=too-many-statements
    def test_progress(self):
        """Test student activity progress in detail, using the sample course."""

        class FakeHandler(object):

            def __init__(self, app_context):
                self.app_context = app_context

        course = Course(FakeHandler(sites.get_all_courses()[0]))
        tracker = course.get_progress_tracker()
        student = models.Student(key_name='key-test-student')

        # Initially, all progress entries should be set to zero.
        unit_progress = tracker.get_unit_progress(student)
        for key in unit_progress:
            assert unit_progress[key] == 0
        lesson_progress = tracker.get_lesson_progress(student, 1)
        for key in lesson_progress:
            assert lesson_progress[key] == {
                'html': 0, 'activity': 0, 'has_activity': True
                }

        # The blocks in Lesson 1.2 with activities are blocks 3 and 6.
        # Submitting block 3 should trigger an in-progress update.
        tracker.put_block_completed(student, 1, 2, 3)
        assert tracker.get_unit_progress(student)['1'] == 1
        assert tracker.get_lesson_progress(student, 1)[2] == {
            'html': 0, 'activity': 1, 'has_activity': True
        }

        # Submitting block 6 should trigger a completion update for the
        # activity, but Lesson 1.2 is still incomplete.
        tracker.put_block_completed(student, 1, 2, 6)
        assert tracker.get_unit_progress(student)['1'] == 1
        assert tracker.get_lesson_progress(student, 1)[2] == {
            'html': 0, 'activity': 2, 'has_activity': True
        }

        # Visiting the HTML page for Lesson 1.2 completes the lesson.
        tracker.put_html_accessed(student, 1, 2)
        assert tracker.get_unit_progress(student)['1'] == 1
        assert tracker.get_lesson_progress(student, 1)[2] == {
            'html': 2, 'activity': 2, 'has_activity': True
        }

        # Test a lesson with no interactive blocks in its activity. It should
        # change its status to 'completed' once it is accessed.
        tracker.put_activity_accessed(student, 2, 1)
        assert tracker.get_unit_progress(student)['2'] == 1
        assert tracker.get_lesson_progress(student, 2)[1] == {
            'html': 0, 'activity': 2, 'has_activity': True
        }

        # Test that a lesson without activities (Lesson 1.1) doesn't count.
        # Complete lessons 1.3, 1.4, 1.5 and 1.6; unit 1 should then be marked
        # as 'completed' even though we have no events associated with
        # Lesson 1.1.
        tracker.put_html_accessed(student, 1, 1)
        tracker.put_html_accessed(student, 1, 3)
        tracker.put_html_accessed(student, 1, 4)
        tracker.put_html_accessed(student, 1, 5)
        tracker.put_html_accessed(student, 1, 6)
        tracker.put_activity_completed(student, 1, 3)
        tracker.put_activity_completed(student, 1, 4)
        tracker.put_activity_completed(student, 1, 5)
        assert tracker.get_unit_progress(student)['1'] == 1
        tracker.put_activity_completed(student, 1, 6)
        assert tracker.get_unit_progress(student)['1'] == 2

        # Test that a unit is not completed until all HTML and activity pages
        # have been, at least, visited. Unit 6 has 3 lessons; the last one has
        # no activity block.
        tracker.put_html_accessed(student, 6, 1)
        tracker.put_html_accessed(student, 6, 2)
        tracker.put_activity_completed(student, 6, 1)
        tracker.put_activity_completed(student, 6, 2)
        assert tracker.get_unit_progress(student)['6'] == 1
        tracker.put_activity_accessed(student, 6, 3)
        assert tracker.get_unit_progress(student)['6'] == 1
        tracker.put_html_accessed(student, 6, 3)
        assert tracker.get_unit_progress(student)['6'] == 2

        # Test assessment counters.
        pre_id = 'Pre'
        tracker.put_assessment_completed(student, pre_id)
        progress = tracker.get_or_create_progress(student)
        assert tracker.is_assessment_completed(progress, pre_id)
        assert tracker.get_assessment_status(progress, pre_id) == 1

        tracker.put_assessment_completed(student, pre_id)
        progress = tracker.get_or_create_progress(student)
        assert tracker.is_assessment_completed(progress, pre_id)
        assert tracker.get_assessment_status(progress, pre_id) == 2

        tracker.put_assessment_completed(student, pre_id)
        progress = tracker.get_or_create_progress(student)
        assert tracker.is_assessment_completed(progress, pre_id)
        assert tracker.get_assessment_status(progress, pre_id) == 3

        # Test that invalid keys do not lead to any updates.
        # Invalid assessment id.
        fake_id = 'asdf'
        tracker.put_assessment_completed(student, fake_id)
        progress = tracker.get_or_create_progress(student)
        assert not tracker.is_assessment_completed(progress, fake_id)
        assert tracker.get_assessment_status(progress, fake_id) is None
        # Invalid unit id.
        tracker.put_activity_completed(student, fake_id, 1)
        progress = tracker.get_or_create_progress(student)
        assert tracker.get_activity_status(progress, fake_id, 1) is None
        # Invalid lesson id.
        fake_numeric_id = 22
        tracker.put_activity_completed(student, 1, fake_numeric_id)
        progress = tracker.get_or_create_progress(student)
        assert tracker.get_activity_status(progress, 1, fake_numeric_id) is None
        # Invalid block id.
        tracker.put_block_completed(student, 5, 2, fake_numeric_id)
        progress = tracker.get_or_create_progress(student)
        assert not tracker.is_block_completed(
            progress, 5, 2, fake_numeric_id)


class AssessmentTest(actions.TestBase):
    """Test for assessments."""

    def test_course_pass(self):
        """Test student passing final exam."""
        email = 'test_pass@google.com'
        name = 'Test Pass'

        post = {'assessment_type': 'Fin', 'score': '100.00'}

        # Register.
        actions.login(email)
        actions.register(self, name)

        # Submit answer.
        response = actions.submit_assessment(self, 'Fin', post)
        assert_equals(response.status_int, 200)
        assert_contains('your overall course score of 70%', response.body)
        assert_contains('you have passed the course', response.body)

        # Check that the result shows up on the profile page.
        response = actions.check_profile(self, name)
        assert_contains('70', response.body)
        assert_contains('100', response.body)

    # pylint: disable-msg=too-many-statements
    def test_assessments(self):
        """Test assessment scores are properly submitted and summarized."""

        course = courses.Course(None, app_context=sites.get_all_courses()[0])

        email = 'test_assessments@google.com'
        name = 'Test Assessments'

        pre_answers = [{'foo': 'bar'}, {'Alice': u'Bob (тест данные)'}]
        pre = {
            'assessment_type': 'Pre', 'score': '1.00',
            'answers': transforms.dumps(pre_answers)}
        mid = {'assessment_type': 'Mid', 'score': '2.00'}
        fin = {'assessment_type': 'Fin', 'score': '3.00'}
        peer = {'assessment_type': 'ReviewAssessmentExample'}
        second_mid = {'assessment_type': 'Mid', 'score': '1.00'}
        second_fin = {'assessment_type': 'Fin', 'score': '100000'}

        # Register.
        actions.login(email)
        actions.register(self, name)

        # Navigate to the course overview page.
        response = self.get('course')
        assert_equals(response.status_int, 200)
        assert_does_not_contain(u'id="progress-completed-Mid', response.body)
        assert_contains(u'id="progress-notstarted-Mid', response.body)

        old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace(self.namespace)
        try:
            student = models.Student.get_enrolled_student_by_email(email)

            # Check that four score objects (corresponding to the four sample
            # assessments) exist right now, and that they all have zero
            # score.
            student_scores = course.get_all_scores(student)
            assert len(student_scores) == 4
            for assessment in student_scores:
                assert assessment['score'] == 0

            # Submit assessments and check that the score is updated.
            actions.submit_assessment(self, 'Pre', pre)
            student = models.Student.get_enrolled_student_by_email(email)
            student_scores = course.get_all_scores(student)
            assert len(student_scores) == 4
            for assessment in student_scores:
                if assessment['id'] == 'Pre':
                    assert assessment['score'] > 0
                else:
                    assert assessment['score'] == 0

            actions.submit_assessment(self, 'Mid', mid)
            student = models.Student.get_enrolled_student_by_email(email)

            # Navigate to the course overview page.
            response = self.get('course')
            assert_equals(response.status_int, 200)
            assert_contains(u'id="progress-completed-Pre', response.body)
            assert_contains(u'id="progress-completed-Mid', response.body)
            assert_contains(u'id="progress-notstarted-Fin', response.body)

            # Submit the final assessment.
            actions.submit_assessment(self, 'Fin', fin)
            student = models.Student.get_enrolled_student_by_email(email)

            # Submit the sample peer review assessment.
            actions.submit_assessment(self, 'ReviewAssessmentExample', peer)
            student_scores = course.get_all_scores(student)
            # This assessment is not considered to be completed until enough
            # peer reviews have been submitted.
            for assessment in student_scores:
                if assessment['id'] == 'ReviewAssessmentExample':
                    assert assessment['human_graded']
                    assert not assessment['completed']

            # Navigate to the course overview page.
            response = self.get('course')
            assert_equals(response.status_int, 200)
            assert_contains(u'id="progress-completed-Fin', response.body)

            # Check that the overall-score is non-zero.
            assert course.get_overall_score(student)

            # Check assessment answers.
            answers = transforms.loads(
                models.StudentAnswersEntity.get_by_key_name(
                    student.user_id).data)
            assert pre_answers == answers['Pre']

            # pylint: disable=g-explicit-bool-comparison
            assert [] == answers['Mid']
            assert [] == answers['Fin']
            # pylint: enable-msg=g-explicit-bool-comparison

            # Check that scores are recorded properly.
            student = models.Student.get_enrolled_student_by_email(email)
            assert int(course.get_score(student, 'Pre')) == 1
            assert int(course.get_score(student, 'Mid')) == 2
            assert int(course.get_score(student, 'Fin')) == 3
            assert (int(course.get_overall_score(student)) ==
                    int((0.30 * 2) + (0.70 * 3)))

            # Try posting a new midcourse exam with a lower score;
            # nothing should change.
            actions.submit_assessment(self, 'Mid', second_mid)
            student = models.Student.get_enrolled_student_by_email(email)
            assert int(course.get_score(student, 'Pre')) == 1
            assert int(course.get_score(student, 'Mid')) == 2
            assert int(course.get_score(student, 'Fin')) == 3
            assert (int(course.get_overall_score(student)) ==
                    int((0.30 * 2) + (0.70 * 3)))

            # Now try posting a postcourse exam with a higher score and note
            # the changes.
            actions.submit_assessment(self, 'Fin', second_fin)
            student = models.Student.get_enrolled_student_by_email(email)
            assert int(course.get_score(student, 'Pre')) == 1
            assert int(course.get_score(student, 'Mid')) == 2
            assert int(course.get_score(student, 'Fin')) == 100000
            assert (int(course.get_overall_score(student)) ==
                    int((0.30 * 2) + (0.70 * 100000)))
        finally:
            namespace_manager.set_namespace(old_namespace)


def remove_dir(dir_name):
    """Delete a directory."""

    logging.info('removing folder: %s', dir_name)
    if os.path.exists(dir_name):
        shutil.rmtree(dir_name)
        if os.path.exists(dir_name):
            raise Exception('Failed to delete directory: %s' % dir_name)


def clean_dir(dir_name):
    """Clean a directory."""

    remove_dir(dir_name)

    logging.info('creating folder: %s', dir_name)
    os.makedirs(dir_name)
    if not os.path.exists(dir_name):
        raise Exception('Failed to create directory: %s' % dir_name)


def clone_canonical_course_data(src, dst):
    """Makes a copy of canonical course content."""
    clean_dir(dst)

    def copytree(name):
        shutil.copytree(
            os.path.join(src, name),
            os.path.join(dst, name))

    copytree('assets')
    copytree('data')
    copytree('views')

    shutil.copy(
        os.path.join(src, 'course.yaml'),
        os.path.join(dst, 'course.yaml'))

    # Make all files writable.
    for root, unused_dirs, files in os.walk(dst):
        for afile in files:
            fname = os.path.join(root, afile)
            os.chmod(fname, 0o777)


class GeneratedCourse(object):
    """A helper class for a dynamically generated course content."""

    @classmethod
    def set_data_home(cls, test):
        """All data for this test will be placed here."""
        cls.data_home = test.test_tempdir

    def __init__(self, ns):
        self.path = ns

    @property
    def namespace(self):
        return 'ns%s' % self.path

    @property
    def title(self):
        return u'Power Searching with Google title-%s (тест данные)' % self.path

    @property
    def unit_title(self):
        return u'Interpreting results unit-title-%s (тест данные)' % self.path

    @property
    def lesson_title(self):
        return u'Word order matters lesson-title-%s (тест данные)' % self.path

    @property
    def head(self):
        return '<!-- head-%s -->' % self.path

    @property
    def css(self):
        return '<!-- css-%s -->' % self.path

    @property
    def home(self):
        return os.path.join(self.data_home, 'data-%s' % self.path)

    @property
    def email(self):
        return 'walk_the_course_named_%s@google.com' % self.path

    @property
    def name(self):
        return 'Walk The Course Named %s' % self.path


class MultipleCoursesTestBase(actions.TestBase):
    """Configures several courses for running concurrently."""

    def modify_file(self, filename, find, replace):
        """Read, modify and write back the file."""

        text = open(filename, 'r').read().decode('utf-8')

        # Make sure target text is not in the file.
        assert replace not in text
        text = text.replace(find, replace)
        assert replace in text

        open(filename, 'w').write(text.encode('utf-8'))

    def modify_canonical_course_data(self, course):
        """Modify canonical content by adding unique bits to it."""

        self.modify_file(
            os.path.join(course.home, 'course.yaml'),
            'title: \'Power Searching with Google\'',
            'title: \'%s\'' % course.title)

        self.modify_file(
            os.path.join(course.home, 'data/unit.csv'),
            ',Interpreting results,',
            ',%s,' % course.unit_title)

        self.modify_file(
            os.path.join(course.home, 'data/lesson.csv'),
            ',Word order matters,',
            ',%s,' % course.lesson_title)

        self.modify_file(
            os.path.join(course.home, 'data/lesson.csv'),
            ',Interpreting results,',
            ',%s,' % course.unit_title)

        self.modify_file(
            os.path.join(course.home, 'views/base.html'),
            '<head>',
            '<head>\n%s' % course.head)

        self.modify_file(
            os.path.join(course.home, 'assets/css/main.css'),
            'html {',
            '%s\nhtml {' % course.css)

    def prepare_course_data(self, course):
        """Create unique course content for a course."""

        clone_canonical_course_data(self.bundle_root, course.home)
        self.modify_canonical_course_data(course)

    def setUp(self):  # pylint: disable=g-bad-name
        """Configure the test."""

        super(MultipleCoursesTestBase, self).setUp()

        GeneratedCourse.set_data_home(self)

        self.course_a = GeneratedCourse('a')
        self.course_b = GeneratedCourse('b')
        self.course_ru = GeneratedCourse('ru')

        # Override BUNDLE_ROOT.
        self.bundle_root = appengine_config.BUNDLE_ROOT
        appengine_config.BUNDLE_ROOT = GeneratedCourse.data_home

        # Prepare course content.
        clean_dir(GeneratedCourse.data_home)
        self.prepare_course_data(self.course_a)
        self.prepare_course_data(self.course_b)
        self.prepare_course_data(self.course_ru)

        # Setup one course for I18N.
        self.modify_file(
            os.path.join(self.course_ru.home, 'course.yaml'),
            'locale: \'en_US\'',
            'locale: \'ru\'')

        # Configure courses.
        sites.setup_courses('%s, %s, %s' % (
            'course:/courses/a:/data-a:nsa',
            'course:/courses/b:/data-b:nsb',
            'course:/courses/ru:/data-ru:nsru'))

    def tearDown(self):  # pylint: disable=g-bad-name
        """Clean up."""
        sites.reset_courses()
        appengine_config.BUNDLE_ROOT = self.bundle_root
        super(MultipleCoursesTestBase, self).tearDown()

    def walk_the_course(
        self, course, first_time=True, is_admin=False, logout=True):
        """Visit a course as a Student would."""

        with actions.OverriddenEnvironment({'course': {'browsable': False}}):
            # Check normal user has no access.
            actions.login(course.email, is_admin=is_admin)

            # Test schedule.
            if first_time:
                response = self.testapp.get('/courses/%s/preview' % course.path)
            else:
                response = self.testapp.get('/courses/%s/course' % course.path)
            assert_contains(course.title, response.body)
            assert_contains(course.unit_title, response.body)
            assert_contains(course.head, response.body)

            # Tests static resource.
            response = self.testapp.get(
                '/courses/%s/assets/css/main.css' % course.path)
            assert_contains(course.css, response.body)

            if first_time:
                # Test registration.
                response = self.get('/courses/%s/register' % course.path)
                assert_contains(course.title, response.body)
                assert_contains(course.head, response.body)

                register_form = actions.get_form_by_action(response, 'register')
                register_form.set('form01', course.name)
                register_form.action = '/courses/%s/register' % course.path
                response = self.submit(register_form)

                assert_equals(response.status_int, 302)
                assert_contains(
                    'course#registration_confirmation', response.headers[
                        'location'])

            # Check lesson page.
            response = self.testapp.get(
                '/courses/%s/unit?unit=1&lesson=5' % course.path)
            assert_contains(course.title, response.body)
            assert_contains(course.lesson_title, response.body)
            assert_contains(course.head, response.body)

            # Check activity page.
            response = self.testapp.get(
                '/courses/%s/activity?unit=1&lesson=5' % course.path)
            assert_contains(course.title, response.body)
            assert_contains(course.lesson_title, response.body)
            assert_contains(course.head, response.body)

            if logout:
                actions.logout()


class MultipleCoursesTest(MultipleCoursesTestBase):
    """Test several courses running concurrently."""

    def test_courses_are_isolated(self):
        """Test each course serves its own assets, views and data."""

        # Pretend students visit courses.
        self.walk_the_course(self.course_a)
        self.walk_the_course(self.course_b)
        self.walk_the_course(self.course_a, first_time=False)
        self.walk_the_course(self.course_b, first_time=False)

        # Check course namespaced data.
        self.validate_course_data(self.course_a)
        self.validate_course_data(self.course_b)

        # Check default namespace.
        assert (
            namespace_manager.get_namespace() ==
            appengine_config.DEFAULT_NAMESPACE_NAME)

        assert not models.Student.all().fetch(1000)

    def validate_course_data(self, course):
        """Check course data is valid."""

        old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace(course.namespace)
        try:
            students = models.Student.all().fetch(1000)
            assert len(students) == 1
            for student in students:
                assert_equals(course.email, student.key().name())
                assert_equals(course.name, student.name)
        finally:
            namespace_manager.set_namespace(old_namespace)


class I18NTest(MultipleCoursesTestBase):
    """Test courses running in different locales and containing I18N content."""

    def test_csv_supports_utf8(self):
        """Test UTF-8 content in CSV file is handled correctly."""

        title_ru = u'Найди факты быстрее'

        csv_file = os.path.join(self.course_ru.home, 'data/unit.csv')
        self.modify_file(
            csv_file, ',Find facts faster,', ',%s,' % title_ru)
        self.modify_file(
            os.path.join(self.course_ru.home, 'data/lesson.csv'),
            ',Find facts faster,', ',%s,' % title_ru)

        rows = []
        for row in csv.reader(open(csv_file)):
            rows.append(row)
        assert title_ru == rows[6][3].decode('utf-8')

        response = self.get('/courses/%s/course' % self.course_ru.path)
        assert_contains(title_ru, response.body)

        # Tests student perspective.
        self.walk_the_course(self.course_ru, first_time=True)
        self.walk_the_course(self.course_ru, first_time=False)

        # Test course author dashboard.
        self.walk_the_course(
            self.course_ru, first_time=False, is_admin=True, logout=False)

        def assert_page_contains(page_name, text_array):
            dashboard_url = '/courses/%s/dashboard' % self.course_ru.path
            response = self.get('%s?action=%s' % (dashboard_url, page_name))
            for text in text_array:
                assert_contains(text, response.body)

        assert_page_contains('', [
            title_ru, self.course_ru.unit_title, self.course_ru.lesson_title])
        assert_page_contains(
            'assets', [self.course_ru.title])
        assert_page_contains(
            '', [
                self.course_ru.title,
                vfs.AbstractFileSystem.normpath(self.course_ru.home)])

        # Clean up.
        actions.logout()

    def test_i18n(self):
        """Test course is properly internationalized."""
        response = self.get('/courses/%s/course' % self.course_ru.path)
        assert_contains_all_of(
            [u'Войти', u'Расписание', u'Курс'], response.body)


class CourseUrlRewritingTestBase(actions.TestBase):
    """Prepare course for using rewrite rules and '/courses/pswg' base URL."""

    def setUp(self):  # pylint: disable=g-bad-name
        super(CourseUrlRewritingTestBase, self).setUp()

        self.base = '/courses/pswg'
        self.namespace = 'gcb-courses-pswg-tests-ns'
        sites.setup_courses('course:%s:/:%s' % (self.base, self.namespace))

    def tearDown(self):  # pylint: disable=g-bad-name
        sites.reset_courses()
        super(CourseUrlRewritingTestBase, self).tearDown()

    def canonicalize(self, href, response=None):
        """Canonicalize URL's using either <base> or self.base."""
        # Check if already canonicalized.
        if href.startswith(
                self.base) or utils.ApplicationHandler.is_absolute(href):
            pass
        else:
            # Look for <base> tag in the response to compute the canonical URL.
            if response:
                return super(CourseUrlRewritingTestBase, self).canonicalize(
                    href, response)

            # Prepend self.base to compute the canonical URL.
            if not href.startswith('/'):
                href = '/%s' % href
            href = '%s%s' % (self.base, href)

        self.audit_url(href)
        return href


class VirtualFileSystemTestBase(actions.TestBase):
    """Prepares a course running on a virtual local file system."""

    def setUp(self):  # pylint: disable=g-bad-name
        """Configure the test."""

        super(VirtualFileSystemTestBase, self).setUp()

        GeneratedCourse.set_data_home(self)

        # Override BUNDLE_ROOT.
        self.bundle_root = appengine_config.BUNDLE_ROOT
        appengine_config.BUNDLE_ROOT = GeneratedCourse.data_home

        # Prepare course content.
        home_folder = os.path.join(GeneratedCourse.data_home, 'data-v')
        clone_canonical_course_data(self.bundle_root, home_folder)

        # we also need resources in modules
        def ignore_pyc(unused_dir, filenames):
            return [
                filename for filename in filenames
                if filename.endswith('.pyc')]

        modules_home = 'modules'
        shutil.copytree(
            os.path.join(self.bundle_root, modules_home),
            os.path.join(GeneratedCourse.data_home, modules_home),
            ignore=ignore_pyc)

        # Configure course.
        self.namespace = 'nsv'
        sites.setup_courses('course:/:/data-vfs:%s' % self.namespace)

        # Modify app_context filesystem to map /data-v to /data-vfs.
        def after_create(unused_cls, instance):
            # pylint: disable=protected-access
            instance._fs = vfs.AbstractFileSystem(
                vfs.LocalReadOnlyFileSystem(
                    os.path.join(GeneratedCourse.data_home, 'data-vfs'),
                    home_folder))

        sites.ApplicationContext.after_create = after_create

    def tearDown(self):  # pylint: disable=g-bad-name
        """Clean up."""
        sites.reset_courses()
        appengine_config.BUNDLE_ROOT = self.bundle_root
        super(VirtualFileSystemTestBase, self).tearDown()


class DatastoreBackedCourseTest(actions.TestBase):
    """Prepares an empty course running on datastore-backed file system."""

    def setUp(self):  # pylint: disable=g-bad-name
        """Configure the test."""
        super(DatastoreBackedCourseTest, self).setUp()

        self.supports_editing = True
        self.namespace = 'dsbfs'
        sites.setup_courses('course:/::%s' % self.namespace)

        all_courses = sites.get_all_courses()
        assert len(all_courses) == 1
        self.app_context = all_courses[0]

    def tearDown(self):  # pylint: disable=g-bad-name
        """Clean up."""
        sites.reset_courses()
        super(DatastoreBackedCourseTest, self).tearDown()

    def upload_all_in_dir(self, dir_name, files_added):
        """Uploads all files in a folder to vfs."""
        root_dir = os.path.join(appengine_config.BUNDLE_ROOT, dir_name)
        for root, unused_dirs, files in os.walk(root_dir):
            for afile in files:
                filename = os.path.join(root, afile)
                self.app_context.fs.put(filename, open(filename, 'rb'))
                files_added.append(filename)

    def init_course_data(self, upload_files):
        """Uploads required course data files into vfs."""
        files_added = []
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(self.namespace)
            upload_files(files_added)

            # Normalize paths to be identical for Windows and Linux.
            files_added_normpath = []
            for file_added in files_added:
                files_added_normpath.append(
                    vfs.AbstractFileSystem.normpath(file_added))

            assert self.app_context.fs.list(
                appengine_config.BUNDLE_ROOT) == sorted(files_added_normpath)
        finally:
            namespace_manager.set_namespace(old_namespace)

    def upload_all_sample_course_files(self, files_added):
        """Uploads all sample course data files into vfs."""
        self.upload_all_in_dir('assets', files_added)
        self.upload_all_in_dir('views', files_added)
        self.upload_all_in_dir('data', files_added)

        course_yaml = os.path.join(
            appengine_config.BUNDLE_ROOT, 'course.yaml')
        self.app_context.fs.put(course_yaml, open(course_yaml, 'rb'))
        files_added.append(course_yaml)

    def calc_course_stats(self, course):
        assessment_count = len(course.get_assessment_list())
        units_count = len(course.get_units())
        activities_count = 0
        lessons_count = 0
        for uid in [x.unit_id for x in course.get_units()]:
            unit_lessons = course.get_lessons(uid)
            lessons_count += len(unit_lessons)
            activities_count += sum(x.activity for x in unit_lessons)
        return units_count, lessons_count, activities_count, assessment_count


class DatastoreBackedCustomCourseTest(DatastoreBackedCourseTest):
    """Prepares a sample course running on datastore-backed file system."""

    # pylint: disable-msg=too-many-statements
    def test_course_import(self):
        """Test importing of the course."""

        # Setup courses.
        sites.setup_courses('course:/test::ns_test, course:/:/')
        self.namespace = 'ns_test'
        self.base = '/test'
        config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name] = True

        # Format import payload and URL.
        payload_dict = {}
        payload_dict['course'] = 'course:/:/'
        request = {}
        request['payload'] = transforms.dumps(payload_dict)
        import_put_url = (
            'rest/course/import?%s' % urllib.urlencode(
                {'request': transforms.dumps(request)}))

        # Check non-logged user has no rights.
        response = self.put(import_put_url, {}, expect_errors=True)
        assert_equals(404, response.status_int)

        # Login as admin.
        email = 'test_course_import@google.com'
        name = 'Test Course Import'
        actions.login(email, is_admin=True)

        # Check course is empty.
        response = self.get('dashboard')
        assert_equals(200, response.status_int)
        assert_does_not_contain('Filter image results by color', response.body)

        # Import sample course.
        request[
            'xsrf_token'] = XsrfTokenManager.create_xsrf_token('import-course')
        import_put_url = (
            'rest/course/import?%s' % urllib.urlencode(
                {'request': transforms.dumps(request)}))
        response = self.put(import_put_url, {})
        assert_equals(200, response.status_int)
        assert_contains('Imported.', response.body)

        # Check course is not empty.
        response = self.get('dashboard')
        assert_contains('Filter image results by color', response.body)

        # Check assessment is copied.
        response = self.get('assessment?name=35')
        assert_equals(200, response.status_int)
        assert_contains('Humane Society website', response.body)

        # Check activity component is hidden
        response = self.get('dashboard?key=5&action=edit_lesson')
        assert_equals(200, response.status_int)
        assert 'excludedCustomTags\\\": [\\\"gcb-activity' in response.body

        # Check activity is copied.
        response = self.get('unit?unit=57&lesson=63')
        assert_equals(200, response.status_int)
        assert_contains(
        'explore ways to keep yourself updated', response.body)

        unit_2_title = 'Unit 2 - Interpreting results'
        lesson_2_1_title = 'When search results suggest something new'
        lesson_2_2_title = 'Thinking more deeply about your search'

        # Check units and lessons are indexed correctly.
        response = actions.register(self, name)
        assert (
            'http://localhost'
            '/test/course'
            '#registration_confirmation' == response.location)
        response = self.get('course')
        assert_contains(unit_2_title, response.body)

        # Unit page.
        response = self.get('unit?unit=14')
        # A unit title.
        assert_contains(
            unit_2_title, response.body)
        # First child lesson without link.
        assert_contains(
            lesson_2_1_title, response.body)
        # Second child lesson with link.
        assert_contains(
            lesson_2_2_title, response.body)
        # Breadcrumbs.
        assert_contains_all_of(
            ['Unit 2</a></li>', 'Lesson 1</li>'], response.body)

        # Unit page.
        response = self.get('unit?unit=14&lesson=16')
        # A unit title.
        assert_contains(
            unit_2_title, response.body)
        # An activity title.
        assert_contains(
            'Activity', response.body)
        # First child lesson without link.
        assert_contains(
            lesson_2_1_title, response.body)
        # Second child lesson with link.
        assert_contains(
            lesson_2_2_title, response.body)
        # Breadcrumbs.
        assert_contains_all_of(
            ['Unit 2</a></li>',
             '<a href="unit?unit=14&lesson=15">',
             '<a href="unit?unit=14&lesson=17">'], response.body)
        assert '<a href="unit?unit=14&lesson=16">' not in response.body

        # Clean up.
        sites.reset_courses()
        config.Registry.test_overrides = {}

    def test_get_put_file(self):
        """Test that one can put/get file via REST interface."""
        self.init_course_data(self.upload_all_sample_course_files)

        email = 'test_get_put_file@google.com'

        actions.login(email, is_admin=True)
        response = self.get('dashboard?action=settings&tab=advanced')

        # Check course.yaml edit form.
        compute_form = response.forms['edit_course_yaml']
        response = self.submit(compute_form)
        assert_equals(response.status_int, 302)
        assert_contains(
            'dashboard?action=edit_settings&tab_title=Advanced'
            '&tab=advanced&key=%2Fcourse.yaml',
            response.location)
        response = self.get(response.location)
        assert_contains('rest/files/item?key=%2Fcourse.yaml', response.body)

        # Get text file.
        response = self.get('rest/files/item?key=%2Fcourse.yaml')
        assert_equals(response.status_int, 200)
        json_dict = transforms.loads(
            transforms.loads(response.body)['payload'])
        assert '/course.yaml' == json_dict['key']
        assert 'text/utf-8' == json_dict['encoding']
        assert (open(os.path.join(
            appengine_config.BUNDLE_ROOT, 'course.yaml')).read(
                ) == json_dict['content'])

    def test_empty_course(self):
        """Test course with no assets and the simplest possible course.yaml."""

        email = 'test_empty_course@google.com'
        actions.login(email, is_admin=True)

        # Check minimal course page comes up.
        response = self.get('course')
        assert_contains('UNTITLED COURSE', response.body)
        assert_contains('Registration', response.body)

        # Check inheritable files are accessible.
        response = self.get('/assets/css/main.css')
        assert (open(os.path.join(
            appengine_config.BUNDLE_ROOT, 'assets/css/main.css')).read(
                ) == response.body)

        # Check non-inheritable files are not inherited.
        response = self.testapp.get(
            '/assets/js/activity-1.3.js', expect_errors=True)
        assert_equals(response.status_int, 404)

        # Login as admin.
        email = 'test_empty_course@google.com'
        actions.login(email, is_admin=True)
        response = self.get('dashboard')

        # Add unit.
        compute_form = response.forms['add_unit']
        response = self.submit(compute_form)
        response = self.get('/rest/course/unit?key=1')
        assert_equals(response.status_int, 200)

        # Add lessons.
        response = self.get('dashboard')
        compute_form = response.forms['add_lesson']
        response = self.submit(compute_form)
        response = self.get('/rest/course/lesson?key=2')
        assert_equals(response.status_int, 200)

        # Add assessment.
        response = self.get('dashboard')
        compute_form = response.forms['add_assessment']
        response = self.submit(compute_form)
        response = self.get('/rest/course/assessment?key=3')
        assert_equals(response.status_int, 200)

        # Add link.
        response = self.get('dashboard')
        compute_form = response.forms['add_link']
        response = self.submit(compute_form)
        response = self.get('/rest/course/link?key=4')
        assert_equals(response.status_int, 200)

    def import_sample_course(self):
        """Imports a sample course."""
        # setup courses
        sites.setup_courses('course:/test::ns_test, course:/:/')

        # check we have no questions or question gourps in neither source nor
        # destination course
        with Namespace(''):
            self.assertEqual(0, len(models.QuestionGroupDAO.get_all()))
            self.assertEqual(0, len(models.QuestionDAO.get_all()))
        with Namespace('ns_test'):
            self.assertEqual(0, len(models.QuestionGroupDAO.get_all()))
            self.assertEqual(0, len(models.QuestionDAO.get_all()))

        # import sample course
        dst_app_context = sites.get_all_courses()[0]
        dst_course = courses.Course(None, app_context=dst_app_context)
        src_app_context = sites.get_all_courses()[1]
        src_course = courses.Course(None, app_context=src_app_context)

        errors = []
        _, dst_course_out = dst_course.import_from(
            src_app_context, errors)
        if errors:
            raise Exception(errors)
        dst_course_out.save()

        u1, l1, ac1, as1 = self.calc_course_stats(src_course)
        u2, l2, _, as2 = self.calc_course_stats(dst_course)

        # the old and the new course have same number of units each
        self.assertEqual(12, u1)
        self.assertEqual(12, u2)

        # old course had lessons and activities
        self.assertEqual(29, l1)
        self.assertEqual(26, ac1)

        # new course has the same number of lessons as the old one, plus one
        # new lesson instead of each old activity
        self.assertEqual(55, l2)
        self.assertEqual(l1 + ac1, l2)

        # both the new & the old courses have 4 assessments
        self.assertEqual(4, as1)
        self.assertEqual(4, as2)

        # new course assessment weights are equal to 25.0
        for x in dst_course.get_assessment_list():
            self.assertEqual(25.0, x.weight)

        # old course does not have any questions or question groups
        with Namespace(''):
            self.assertEqual(0, len(models.QuestionGroupDAO.get_all()))
            self.assertEqual(0, len(models.QuestionDAO.get_all()))

        # new course has new questions and question groups that used to be old
        # style activities
        with Namespace('ns_test'):
            self.assertEqual(2, len(models.QuestionGroupDAO.get_all()))
            self.assertEqual(69, len(models.QuestionDAO.get_all()))

        # clean up
        sites.reset_courses()

    def test_imported_course_performance(self):
        """Tests various pages of the imported course."""
        self.import_sample_course()

        # Install a clone on the '/' so all the tests will treat it as normal
        # sample course.
        sites.setup_courses('course:/::ns_test')
        self.namespace = 'ns_test'

        # Enable memcache.
        config.Registry.test_overrides[
            models.CAN_USE_MEMCACHE.name] = True

        with actions.OverriddenEnvironment({
                'course': {
                    'now_available': True,
                    'browsable': False}}):

            def custom_inc(unused_increment=1, context=None):
                """A custom inc() function for cache miss counter."""
                self.keys.append(context)
                self.count += 1

            def assert_cached(url, assert_text, cache_miss_allowed=0):
                """Checks that specific URL supports caching."""
                memcache.flush_all()

                # Expect cache misses first time we load page.
                cache_miss_before = self.count
                response = self.get(url)
                assert_contains(assert_text, response.body)
                assert cache_miss_before != self.count

                # Expect no cache misses first time we load page.
                self.keys = []
                cache_miss_before = self.count
                response = self.get(url)
                assert_contains(assert_text, response.body)
                cache_miss_actual = self.count - cache_miss_before
                if cache_miss_actual != cache_miss_allowed:
                    raise Exception(
                        'Expected %s cache misses, got %s. Keys are:\n%s' % (
                            cache_miss_allowed, cache_miss_actual,
                            '\n'.join(self.keys)))

            self.keys = []
            self.count = 0

            old_inc = models.CACHE_MISS.inc
            models.CACHE_MISS.inc = custom_inc

            # Walk the site.
            email = 'test_units_lessons@google.com'
            name = 'Test Units Lessons'

            assert_cached('preview', 'Putting it all together')
            actions.login(email, is_admin=True)
            assert_cached('preview', 'Putting it all together')
            actions.register(self, name)
            assert_cached('course', 'Putting it all together')
            assert_cached(
                'unit?unit=14', 'When search results suggest something new')
            assert_cached(
                'unit?unit=14&lesson=19',
                'Understand options for different media')

        # Clean up.
        models.CACHE_MISS.inc = old_inc
        config.Registry.test_overrides = {}
        sites.reset_courses()

    def test_imported_course(self):
        """Tests various pages of the imported course."""
        # TODO(psimakov): Ideally, this test class should run all aspect tests
        # and they all should pass. However, the id's in the cloned course
        # do not match the id's of source sample course and we fetch pages
        # and assert page content using id's. For now, we will check the minimal
        # set of pages manually. Later, we have to make it run all known tests.

        self.import_sample_course()

        # Install a clone on the '/' so all the tests will treat it as normal
        # sample course.
        sites.setup_courses('course:/::ns_test')
        self.namespace = 'ns_test'

        email = 'test_units_lessons@google.com'
        name = 'Test Units Lessons'

        actions.login(email, is_admin=True)

        response = self.get('course')
        assert_contains('Putting it all together', response.body)

        actions.register(self, name)
        actions.check_profile(self, name)
        actions.view_announcements(self)

        # Check unit page without lesson specified.
        response = self.get('unit?unit=14')
        assert_contains('Interpreting results', response.body)
        assert_contains(
            'When search results suggest something new', response.body)

        # Check unit page with a lessons.
        response = self.get('unit?unit=14&lesson=19')
        assert_contains('Interpreting results', response.body)
        assert_contains(
            'Understand options for different media', response.body)

        # Check assesment page.
        response = self.get('assessment?name=35')
        self.assertEqual(5, response.body.count('<div class="qt-question">'))

        # Check activity page.
        response = self.get('unit?unit=14&lesson=16')
        assert_contains('Activity', response.body)

        # Clean up.
        sites.reset_courses()

    def test_readonly_caching(self):
        self.import_sample_course()

        sites.setup_courses('course:/::ns_test')
        self.namespace = 'ns_test'
        course = sites.get_all_courses()[0]
        fn = os.path.join(
            appengine_config.BUNDLE_ROOT, 'data/course.json')

        config.Registry.test_overrides[
            models.CAN_USE_MEMCACHE.name] = True

        # get the page and record hits and misses
        hit_local_before = models.CACHE_HIT_LOCAL.value
        hit_before = models.CACHE_HIT.value
        miss_local_before = models.CACHE_MISS_LOCAL.value
        miss_before = models.CACHE_MISS.value
        course.fs.impl.get(fn)
        hit_local_after = models.CACHE_HIT_LOCAL.value
        hit_after = models.CACHE_HIT.value
        miss_local_after = models.CACHE_MISS_LOCAL.value
        miss_after = models.CACHE_MISS.value
        self.assertEquals(hit_after, hit_before)
        self.assertEquals(miss_after, miss_before)
        self.assertEquals(hit_local_after, hit_local_before)
        self.assertEquals(miss_local_after, miss_local_before)

        # enable read_only caching and repeat
        models.MemcacheManager.begin_readonly()
        try:

          # first fetch chould miss local cache, but hit memcache
          hit_local_before = models.CACHE_HIT_LOCAL.value
          hit_before = models.CACHE_HIT.value
          miss_local_before = models.CACHE_MISS_LOCAL.value
          miss_before = models.CACHE_MISS.value
          course.fs.impl.get(fn)
          hit_local_after = models.CACHE_HIT_LOCAL.value
          hit_after = models.CACHE_HIT.value
          miss_local_after = models.CACHE_MISS_LOCAL.value
          miss_after = models.CACHE_MISS.value
          self.assertEquals(hit_after, hit_before)
          self.assertEquals(miss_after, miss_before)
          self.assertEquals(hit_local_after, hit_local_before)
          self.assertEquals(miss_local_after, miss_local_before)

          # second fetch must hit local cache, and not hit memcache
          hit_local_before = models.CACHE_HIT_LOCAL.value
          hit_before = models.CACHE_HIT.value
          miss_local_before = models.CACHE_MISS_LOCAL.value
          miss_before = models.CACHE_MISS.value
          course.fs.impl.get(fn)
          hit_local_after = models.CACHE_HIT_LOCAL.value
          hit_after = models.CACHE_HIT.value
          miss_local_after = models.CACHE_MISS_LOCAL.value
          miss_after = models.CACHE_MISS.value
          self.assertEquals(hit_after, hit_before)
          self.assertEquals(miss_after, miss_before)
          self.assertEquals(hit_local_after, hit_local_before)
          self.assertEquals(miss_local_after, miss_local_before)
        finally:
            models.MemcacheManager.end_readonly()


class DatastoreBackedSampleCourseTest(DatastoreBackedCourseTest):
    """Run all existing tests using datastore-backed file system."""

    def setUp(self):  # pylint: disable=g-bad-name
        super(DatastoreBackedSampleCourseTest, self).setUp()
        self.init_course_data(self.upload_all_sample_course_files)


class LessonComponentsTest(DatastoreBackedCourseTest):
    """Test operations that make use of components in a lesson body."""

    def setUp(self):
        """Set up the dummy course for each test case in this class."""
        super(LessonComponentsTest, self).setUp()
        self.course = courses.Course(None, app_context=self.app_context)
        self.unit = self.course.add_unit()
        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.objectives = """
            <question quid="123" weight="1" instanceid="QN"></question>
            random_text
            <gcb-youtube videoid="Kdg2drcUjYI" instanceid="VD"></gcb-youtube>
            more_random_text
            <question-group qgid="456" instanceid="QG"></question-group>
            yet_more_random_text
        """
        self.lesson.has_activity = False
        self.course.update_lesson(self.lesson)
        self.course.save()

        self.tracker = self.course.get_progress_tracker()

    def test_component_discovery(self):
        """Test extraction of components from a lesson body."""
        cpt_list = self.course.get_components(
            self.unit.unit_id, self.lesson.lesson_id)
        assert cpt_list == [
            {'instanceid': 'QN', 'quid': '123', 'weight': '1',
             'cpt_name': 'question'},
            {'instanceid': 'VD', 'cpt_name': 'gcb-youtube',
             'videoid': 'Kdg2drcUjYI'},
            {'instanceid': 'QG', 'qgid': '456', 'cpt_name': 'question-group'}
        ]

        valid_cpt_ids = self.tracker.get_valid_component_ids(
            self.unit.unit_id, self.lesson.lesson_id)
        self.assertEqual(set(['QN', 'QG']), set(valid_cpt_ids))

    def test_component_progress(self):
        """Test that progress tracking for components is done correctly."""
        unit_id = self.unit.unit_id
        lesson_id = self.lesson.lesson_id

        student = models.Student(key_name='lesson-body-test-student')

        assert self.tracker.get_unit_progress(student)[unit_id] == 0
        assert self.tracker.get_lesson_progress(
            student, unit_id)[lesson_id] == {
                'html': 0, 'activity': 0, 'has_activity': False}

        # Visiting the lesson page has no effect on progress, since it contains
        # trackable components.
        self.tracker.put_html_accessed(student, unit_id, lesson_id)
        assert self.tracker.get_unit_progress(student)[unit_id] == 0
        assert self.tracker.get_lesson_progress(
            student, unit_id)[lesson_id] == {
                'html': 0, 'activity': 0, 'has_activity': False}

        # Marking progress for a non-existent component id has no effect.
        self.tracker.put_component_completed(student, unit_id, lesson_id, 'a')
        assert self.tracker.get_unit_progress(student)[unit_id] == 0
        assert self.tracker.get_lesson_progress(
            student, unit_id)[lesson_id] == {
                'html': 0, 'activity': 0, 'has_activity': False}

        # Marking progress for a non-trackable component id has no effect.
        self.tracker.put_component_completed(student, unit_id, lesson_id, 'VD')
        assert self.tracker.get_unit_progress(student)[unit_id] == 0
        assert self.tracker.get_lesson_progress(
            student, unit_id)[lesson_id] == {
                'html': 0, 'activity': 0, 'has_activity': False}

        # Completing a trackable component marks the lesson as in-progress,
        self.tracker.put_component_completed(student, unit_id, lesson_id, 'QN')
        assert self.tracker.get_unit_progress(student)[unit_id] == 1
        assert self.tracker.get_lesson_progress(
            student, unit_id)[lesson_id] == {
                'html': 1, 'activity': 0, 'has_activity': False}

        # Completing the same component again has no further effect.
        self.tracker.put_component_completed(student, unit_id, lesson_id, 'QN')
        assert self.tracker.get_unit_progress(student)[unit_id] == 1
        assert self.tracker.get_lesson_progress(
            student, unit_id)[lesson_id] == {
                'html': 1, 'activity': 0, 'has_activity': False}

        # Completing the other trackable component marks the lesson (and unit)
        # as completed.
        self.tracker.put_component_completed(student, unit_id, lesson_id, 'QG')
        assert self.tracker.get_unit_progress(student)[unit_id] == 2
        assert self.tracker.get_lesson_progress(
            student, unit_id)[lesson_id] == {
                'html': 2, 'activity': 0, 'has_activity': False}


class EtlTestEntityPii(entities.BaseEntity):
    name = db.StringProperty(indexed=False)
    score = db.IntegerProperty(indexed=False)

    _PROPERTY_EXPORT_BLACKLIST = [name]

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        return db.Key.from_path(cls.kind(), transform_fn(db_key.id_or_name()))


class EtlTestEntityPiiReference(entities.BaseEntity):
    pii = db.ReferenceProperty(EtlTestEntityPii)


class EtlTestEntityIllegal(entities.BaseEntity):
    score = db.IntegerProperty(indexed=False)
    thingy = student_work.KeyProperty()


class EtlMainTestCase(testing.EtlTestBase, DatastoreBackedCourseTest):
    """Tests tools/etl/etl.py's main()."""

    # Allow access to protected members under test.
    # pylint: disable=protected-access
    def setUp(self):
        """Configures EtlMainTestCase."""
        super(EtlMainTestCase, self).setUp()
        self.archive_path = os.path.join(self.test_tempdir, 'archive.zip')
        self.new_course_title = 'New Course Title'
        self.common_args = [
            self.url_prefix, 'myapp', 'localhost:8080']
        self.common_command_args = self.common_args + [
            '--archive_path', self.archive_path]
        self.common_course_args = [etl._TYPE_COURSE] + self.common_command_args
        self.common_datastore_args = [
            etl._TYPE_DATASTORE] + self.common_command_args
        self.delete_datastore_args = etl.PARSER.parse_args(
            [etl._MODE_DELETE, etl._TYPE_DATASTORE] + self.common_args)
        self.download_course_args = etl.PARSER.parse_args(
            [etl._MODE_DOWNLOAD] + self.common_course_args)
        self.upload_course_args = etl.PARSER.parse_args(
            [etl._MODE_UPLOAD] + self.common_course_args)

        self.make_items_distinct_counter = 0

    def create_app_yaml(self, context, title=None):
        yaml = copy.deepcopy(courses.DEFAULT_COURSE_YAML_DICT)
        if title:
            yaml['course']['title'] = title
        context.fs.impl.put(
            os.path.join(
                appengine_config.BUNDLE_ROOT, etl._COURSE_YAML_PATH_SUFFIX),
            etl._ReadWrapper(str(yaml)), is_draft=False)

    def create_archive(self):
        self.upload_all_sample_course_files([])
        self.import_sample_course()
        args = etl.PARSER.parse_args(['download'] + self.common_course_args)
        etl.main(args, environment_class=testing.FakeEnvironment)
        sites.reset_courses()

    def create_archive_with_question(self, data):
        self.upload_all_sample_course_files([])
        self.import_sample_course()
        question = _add_data_entity(
            sites.get_all_courses()[1], models.QuestionEntity, data)
        args = etl.PARSER.parse_args(['download'] + self.common_course_args)
        etl.main(args, environment_class=testing.FakeEnvironment)
        sites.reset_courses()
        return question

    def create_empty_course(self, raw):
        sites.setup_courses(raw)
        context = etl_lib.get_context(self.url_prefix)
        course = etl_lib.get_course(etl_lib.get_context(self.url_prefix))
        course.delete_all()
        # delete all other entities from data store
        with Namespace(self.namespace):
            db.delete(db.Query(keys_only=True))
        self.create_app_yaml(context)

    def import_sample_course(self):
        """Imports a sample course."""

        # Import sample course.
        dst_app_context = sites.get_all_courses()[0]
        src_app_context = sites.get_all_courses()[1]

        # Patch in a course.yaml.
        self.create_app_yaml(dst_app_context, title=self.new_course_title)

        dst_course = courses.Course(None, app_context=dst_app_context)
        errors = []
        src_course_out, dst_course_out = dst_course.import_from(
            src_app_context, errors)
        if errors:
            raise Exception(errors)
        assert len(
            src_course_out.get_units()) == len(dst_course_out.get_units())
        dst_course_out.save()

    def test_archive_size_can_exceed_2_gb(self):
        # The maximum size for any file in the zipfile is 1 GB.
        byte = '.'
        gig = byte * (2 ** 30)
        archive = etl._Archive(self.archive_path)
        archive.open('w')
        archive.add(os.path.join(self.test_tempdir, 'first'), gig)
        archive.add(os.path.join(self.test_tempdir, 'second'), gig)
        archive.add(os.path.join(self.test_tempdir, 'overflow'), byte)
        archive.close()

    def test_delete_course_fails(self):
        args = etl.PARSER.parse_args(
            [etl._MODE_DELETE, etl._TYPE_COURSE] + self.common_args)
        self.assertRaises(
            NotImplementedError,
            etl.main, args, environment_class=testing.FakeEnvironment)

    def test_delete_datastore_fails_if_user_does_not_confirm(self):
        self.swap(
            etl, '_raw_input',
            lambda x: 'not' + etl._DELETE_DATASTORE_CONFIRMATION_INPUT)
        self.assertRaises(
            SystemExit, etl.main, self.delete_datastore_args,
            environment_class=testing.FakeEnvironment)

    def test_delete_datastore_succeeds(self):
        """Tests delete datastore success for populated and empty datastores."""
        self.import_sample_course()
        context = etl_lib.get_context(
            self.delete_datastore_args.course_url_prefix)
        self.swap(
            etl, '_raw_input',
            lambda x: etl._DELETE_DATASTORE_CONFIRMATION_INPUT)

        # Spot check that some kinds are populated.
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(context.get_namespace_name())
            self.assertTrue(vfs.FileDataEntity.all().get())
            self.assertTrue(vfs.FileMetadataEntity.all().get())
        finally:
            namespace_manager.set_namespace(old_namespace)

        # Delete against a datastore with contents runs successfully.
        etl.main(
            self.delete_datastore_args,
            environment_class=testing.FakeEnvironment)

        # Spot check that those kinds are now empty.
        try:
            namespace_manager.set_namespace(context.get_namespace_name())
            self.assertFalse(vfs.FileDataEntity.all().get())
            self.assertFalse(vfs.FileMetadataEntity.all().get())
        finally:
            namespace_manager.set_namespace(old_namespace)

        # Delete against a datastore without contents runs successfully.
        etl.main(
            self.delete_datastore_args,
            environment_class=testing.FakeEnvironment)

    def test_disable_remote_cannot_be_passed_for_mode_other_than_run(self):
        bad_args = etl.PARSER.parse_args(
            [etl._MODE_DOWNLOAD] + self.common_course_args +
            ['--disable_remote'])
        self.assertRaises(
            SystemExit, etl.main, bad_args,
            environment_class=testing.FakeEnvironment)

    def test_download_course_creates_valid_archive(self):
        """Tests download of course data and archive creation."""
        self.upload_all_sample_course_files([])
        self.import_sample_course()
        question = _add_data_entity(
            sites.get_all_courses()[0], models.QuestionEntity, 'test question')
        etl.main(
            self.download_course_args,
            environment_class=testing.FakeEnvironment)

        # Don't use Archive and Manifest here because we want to test the raw
        # structure of the emitted zipfile.
        zip_archive = zipfile.ZipFile(self.archive_path)

        # check manifest
        manifest = transforms.loads(
            zip_archive.open(etl._MANIFEST_FILENAME).read())
        self.assertGreaterEqual(
            courses.COURSE_MODEL_VERSION_1_3, manifest['version'])
        self.assertEqual(
            'course:%s::ns_test' % self.url_prefix, manifest['raw'])

        # check content
        for entity in manifest['entities']:
            self.assertTrue(entity.has_key('is_draft'))
            self.assertTrue(zip_archive.open(entity['path']))

        # check question
        question_json = transforms.loads(
            zip_archive.open('models/QuestionEntity.json').read())
        self.assertEqual(
            question.key().id(), question_json['rows'][-1]['key.id'])
        self.assertEqual(
            'test question', question_json['rows'][-1]['data'])
        # 69 from the import plus the one we created in the test
        self.assertEqual(70, len(question_json['rows']))

    def test_download_course_errors_if_archive_path_exists_on_disk(self):
        self.upload_all_sample_course_files([])
        self.import_sample_course()
        etl.main(
            self.download_course_args,
            environment_class=testing.FakeEnvironment)
        self.assertRaises(
            SystemExit, etl.main, self.download_course_args,
            environment_class=testing.FakeEnvironment)

    def test_download_errors_if_course_url_prefix_does_not_exist(self):
        sites.reset_courses()
        self.assertRaises(
            SystemExit, etl.main, self.download_course_args,
            environment_class=testing.FakeEnvironment)

    def test_download_course_errors_if_course_version_is_pre_1_3(self):
        args = etl.PARSER.parse_args(
            ['download', 'course', '/'] + self.common_course_args[2:])
        self.upload_all_sample_course_files([])
        self.import_sample_course()
        self.assertRaises(
            SystemExit, etl.main, args,
            environment_class=testing.FakeEnvironment)

    def test_download_datastore_fails_if_datastore_types_not_in_datastore(self):
        download_datastore_args = etl.PARSER.parse_args(
            [etl._MODE_DOWNLOAD] + self.common_datastore_args +
            ['--datastore_types', 'missing'])
        self.assertRaises(
            SystemExit, etl.main, download_datastore_args,
            environment_class=testing.FakeEnvironment)

    def test_download_datastore_succeeds(self):
        """Test download of datastore data and archive creation."""
        download_datastore_args = etl.PARSER.parse_args(
            [etl._MODE_DOWNLOAD] + self.common_datastore_args +
            ['--datastore_types', 'Student,StudentPropertyEntity'])
        context = etl_lib.get_context(download_datastore_args.course_url_prefix)

        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(context.get_namespace_name())
            first_student = models.Student(key_name='first_student')
            second_student = models.Student(key_name='second_student')
            first_entity = models.StudentPropertyEntity(
                key_name='first_student-property_entity')
            second_entity = models.StudentPropertyEntity(
                key_name='second_student-property_entity')
            db.put([first_student, second_student, first_entity, second_entity])
        finally:
            namespace_manager.set_namespace(old_namespace)

        etl.main(
            download_datastore_args, environment_class=testing.FakeEnvironment)
        archive = etl._Archive(self.archive_path)
        archive.open('r')
        self.assertEqual(
            ['Student.json', 'StudentPropertyEntity.json'],
            sorted(
                [os.path.basename(e.path) for e in archive.manifest.entities]))
        student_entity = [
            e for e in archive.manifest.entities
            if e.path.endswith('Student.json')][0]
        entity_entity = [
            e for e in archive.manifest.entities
            if e.path.endswith('StudentPropertyEntity.json')][0]
        # Ensure .json files are deserializable into Python objects.
        students = sorted(
            transforms.loads(archive.get(student_entity.path))['rows'],
            key=lambda d: d['key.name'])
        entitiez = sorted(
            transforms.loads(archive.get(entity_entity.path))['rows'],
            key=lambda d: d['key.name'])
        # Spot check their contents.
        self.assertEqual(
            [model.key().name() for model in [first_student, second_student]],
            [student['key.name'] for student in students])
        self.assertEqual(
            [model.key().name() for model in [first_entity, second_entity]],
            [entity['key.name'] for entity in entitiez])

    def test_download_datastore_with_privacy_maintains_references(self):
        """Test download of datastore data and archive creation."""
        unsafe_user_id = '1'
        download_datastore_args = etl.PARSER.parse_args(
            [etl._MODE_DOWNLOAD] + self.common_datastore_args +
            ['--datastore_types', 'EventEntity,Student', '--privacy',
             '--privacy_secret', 'super_seekrit'])
        context = etl_lib.get_context(download_datastore_args.course_url_prefix)

        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(context.get_namespace_name())
            event = models.EventEntity(user_id=unsafe_user_id)
            student = models.Student(
                key_name='first_student', user_id=unsafe_user_id)
            db.put([event, student])
        finally:
            namespace_manager.set_namespace(old_namespace)

        etl.main(
            download_datastore_args, environment_class=testing.FakeEnvironment)
        archive = etl._Archive(self.archive_path)
        archive.open('r')
        self.assertEqual(
            ['EventEntity.json', 'Student.json'],
            sorted(
                [os.path.basename(e.path) for e in archive.manifest.entities]))
        event_entity_entity = [
            e for e in archive.manifest.entities
            if e.path.endswith('EventEntity.json')][0]
        student_entity = [
            e for e in archive.manifest.entities
            if e.path.endswith('Student.json')][0]
        # Ensure .json files are deserializable into Python objects...
        event_entities = transforms.loads(
            archive.get(event_entity_entity.path))['rows']
        students = transforms.loads(archive.get(student_entity.path))['rows']
        # Reference maintained.
        self.assertEqual(event_entities[0]['user_id'], students[0]['user_id'])
        # But user_id transformed.
        self.assertNotEqual(unsafe_user_id, event_entities[0]['user_id'])
        self.assertNotEqual(unsafe_user_id, students[0]['user_id'])

    def test_privacy_fails_if_not_downloading_datastore(self):
        wrong_mode = etl.PARSER.parse_args(
            [etl._MODE_UPLOAD] + self.common_datastore_args + ['--privacy'])
        self.assertRaises(
            SystemExit, etl.main, wrong_mode,
            environment_class=testing.FakeEnvironment)
        wrong_type = etl.PARSER.parse_args(
            [etl._MODE_DOWNLOAD] + self.common_course_args + ['--privacy'])
        self.assertRaises(
            SystemExit, etl.main, wrong_type,
            environment_class=testing.FakeEnvironment)

    def test_privacy_secret_fails_if_not_download_datastore_with_privacy(self):
        """Tests invalid flag combinations related to --privacy."""
        missing_privacy = etl.PARSER.parse_args(
            [etl._MODE_DOWNLOAD] + self.common_datastore_args +
            ['--privacy_secret', 'foo'])
        self.assertRaises(
            SystemExit, etl.main, missing_privacy,
            environment_class=testing.FakeEnvironment)
        self.assertRaises(
            SystemExit, etl.main, missing_privacy,
            environment_class=testing.FakeEnvironment)
        wrong_mode = etl.PARSER.parse_args(
            [etl._MODE_UPLOAD] + self.common_datastore_args +
            ['--privacy_secret', 'foo', '--privacy'])
        self.assertRaises(
            SystemExit, etl.main, wrong_mode,
            environment_class=testing.FakeEnvironment)
        wrong_type = etl.PARSER.parse_args(
            [etl._MODE_DOWNLOAD] + self.common_course_args +
            ['--privacy_secret', 'foo', '--privacy'])
        self.assertRaises(
            SystemExit, etl.main, wrong_type,
            environment_class=testing.FakeEnvironment)

    def test_run_fails_when_delegated_argument_parsing_fails(self):
        bad_args = etl.PARSER.parse_args(
            ['run', 'tools.etl_lib.Job'] + self.common_args +
            ['--job_args', "'unexpected_argument'"])
        self.assertRaises(
            SystemExit, etl.main, bad_args,
            environment_class=testing.FakeEnvironment)

    def test_run_fails_when_if_requested_class_missing_or_invalid(self):
        bad_args = etl.PARSER.parse_args(
            ['run', 'a.missing.class.or.Module'] + self.common_args)
        self.assertRaises(
            SystemExit, etl.main, bad_args,
            environment_class=testing.FakeEnvironment)
        bad_args = etl.PARSER.parse_args(
            ['run', 'tools.etl.etl._Archive'] + self.common_args)
        self.assertRaises(
            SystemExit, etl.main, bad_args,
            environment_class=testing.FakeEnvironment)

    def test_run_print_memcache_stats_succeeds(self):
        """Tests examples.WriteStudentEmailsToFile prints stats to stdout."""
        args = etl.PARSER.parse_args(
            ['run', 'tools.etl.examples.PrintMemcacheStats'] + self.common_args)
        memcache.get('key')
        memcache.set('key', 1)
        memcache.get('key')

        old_stdout = sys.stdout
        stdout = cStringIO.StringIO()
        try:
            sys.stdout = stdout
            etl.main(args, environment_class=testing.FakeEnvironment)
        finally:
            sys.stdout = old_stdout

        expected0 = examples.PrintMemcacheStats._STATS_TEMPLATE % {
            'byte_hits': 1,
            'bytes': 1,
            'hits': 1,
            'items': 1,
            'misses': 1,
            'oldest_item_age': 0,
        }
        expected1 = examples.PrintMemcacheStats._STATS_TEMPLATE % {
            'byte_hits': 1,
            'bytes': 1,
            'hits': 1,
            'items': 1,
            'misses': 1,
            'oldest_item_age': 1,
        }
        actual = stdout.getvalue()
        self.assertTrue(expected0 in actual or expected1 in actual)

    def test_run_skips_remote_env_setup_when_disable_remote_passed(self):
        args = etl.PARSER.parse_args(
            ['run', 'tools.etl.etl_lib.Job'] + self.common_args +
            ['--disable_remote'])
        etl.main(args)

    def test_run_upload_file_to_course_succeeds(self):
        """Tests upload of a single local file to a course."""
        path = os.path.join(self.test_tempdir, 'file')
        target = 'assets/file'
        remote_path = os.path.join(appengine_config.BUNDLE_ROOT, target)
        contents = 'contents'

        with open(path, 'w') as f:
            f.write(contents)

        args = etl.PARSER.parse_args(
            ['run', 'tools.etl.examples.UploadFileToCourse'] +
            self.common_args + ['--job_args=%s %s' % (path, target)])
        sites.setup_courses(self.raw)
        context = etl_lib.get_context(args.course_url_prefix)

        self.assertFalse(context.fs.impl.get(remote_path))
        etl.main(args, environment_class=testing.FakeEnvironment)
        self.assertEqual(contents, context.fs.impl.get(remote_path).read())

    def test_run_write_student_emails_to_file_succeeds(self):
        """Tests args passed to and run of examples.WriteStudentEmailsToFile."""
        email1 = 'email1@example.com'
        email2 = 'email2@example.com'
        path = os.path.join(self.test_tempdir, 'emails')
        args = etl.PARSER.parse_args(
            ['run', 'tools.etl.examples.WriteStudentEmailsToFile'] +
            self.common_args + ['--job_args=%s --batch_size 1' % path])
        context = etl_lib.get_context(args.course_url_prefix)

        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(context.get_namespace_name())
            first_student = models.Student(key_name=email1)
            second_student = models.Student(key_name=email2)
            db.put([first_student, second_student])
        finally:
            namespace_manager.set_namespace(old_namespace)

        etl.main(args, environment_class=testing.FakeEnvironment)
        self.assertEqual('%s\n%s\n' % (email1, email2), open(path).read())

    def test_upload_course_fails_if_archive_cannot_be_opened(self):
        sites.setup_courses(self.raw)
        self.assertRaises(
            SystemExit, etl.main, self.upload_course_args,
            environment_class=testing.FakeEnvironment)

    def test_upload_course_fails_if_archive_course_json_malformed(self):
        self.create_archive()
        self.create_empty_course(self.raw)
        zip_archive = zipfile.ZipFile(self.archive_path, 'a')
        zip_archive.writestr(
            etl._Archive.get_internal_path(etl._COURSE_JSON_PATH_SUFFIX),
            'garbage')
        zip_archive.close()
        self.assertRaises(
            SystemExit, etl.main, self.upload_course_args,
            environment_class=testing.FakeEnvironment)

    def test_upload_course_fails_if_archive_course_yaml_malformed(self):
        self.create_archive()
        self.create_empty_course(self.raw)
        zip_archive = zipfile.ZipFile(self.archive_path, 'a')
        zip_archive.writestr(
            etl._Archive.get_internal_path(etl._COURSE_YAML_PATH_SUFFIX),
            '{')
        zip_archive.close()
        self.assertRaises(
            SystemExit, etl.main, self.upload_course_args,
            environment_class=testing.FakeEnvironment)

    def test_upload_course_fails_if_course_has_non_course_yaml_contents(self):
        self.upload_all_sample_course_files([])
        self.import_sample_course()
        self.assertRaises(
            SystemExit, etl.main, self.upload_course_args,
            environment_class=testing.FakeEnvironment)

    def test_upload_course_fails_if_force_overwrite_passed_with_bad_args(self):
        self.create_archive()
        bad_args = etl.PARSER.parse_args(
            [etl._MODE_UPLOAD] + self.common_datastore_args + [
                '--force_overwrite'])
        self.assertRaises(
            SystemExit, etl.main, bad_args,
            environment_class=testing.FakeEnvironment)

    def test_upload_course_fails_if_no_course_with_url_prefix_found(self):
        self.create_archive()
        self.assertRaises(
            SystemExit, etl.main, self.upload_course_args,
            environment_class=testing.FakeEnvironment)

    def _get_all_entity_files(self):
        files = []
        all_entities = list(courses.COURSE_CONTENT_ENTITIES) + list(
            courses.ADDITIONAL_ENTITIES_FOR_COURSE_IMPORT)
        for entity in all_entities:
            files.append('%s.json' % entity.__name__)
        return files

    def test_upload_course_succeeds(self):
        """Tests upload of archive contents."""
        question = self.create_archive_with_question('test question')
        self.create_empty_course(self.raw)
        context = etl_lib.get_context(self.upload_course_args.course_url_prefix)
        self.assertNotEqual(self.new_course_title, context.get_title())

        all_files_before_upload = set(
            etl._filter_filesystem_files(etl._list_all(
                context, include_inherited=True)))
        etl.main(
            self.upload_course_args, environment_class=testing.FakeEnvironment)

        # check archive content
        archive = etl._Archive(self.archive_path)
        archive.open('r')
        context = etl_lib.get_context(self.upload_course_args.course_url_prefix)

        vfs_files_after_upload = set(context.fs.impl.list(
            appengine_config.BUNDLE_ROOT))

        self.assertEqual(
            len(archive.manifest.entities)
            - len(all_files_before_upload)  # less already-present files
            - len(self._get_all_entity_files()),  # less entity files
            len(vfs_files_after_upload - all_files_before_upload))

        # check course structure
        self.assertEqual(self.new_course_title, context.get_title())
        units = etl_lib.get_course(context).get_units()
        spot_check_single_unit = [u for u in units if u.unit_id == 14][0]
        self.assertEqual('Interpreting results', spot_check_single_unit.title)
        for unit in units:
            self.assertTrue(unit.title)

        # check entities
        for entity in archive.manifest.entities:
            _, tail = os.path.split(entity.path)
            if tail in self._get_all_entity_files():
                continue
            full_path = os.path.join(
                appengine_config.BUNDLE_ROOT,
                etl._Archive.get_external_path(entity.path))
            stream = context.fs.impl.get(full_path)
            self.assertEqual(entity.is_draft, context.fs.is_draft(stream))

        # check uploaded question matches original
        _assert_identical_data_entity_exists(
            sites.get_all_courses()[0], question)

    def test_upload_course_with_force_overwrite_succeeds(self):
        """Tests upload into non-empty course with --force_overwrite."""

        self.upload_all_sample_course_files([])
        self.import_sample_course()
        etl.main(
            self.download_course_args,
            environment_class=testing.FakeEnvironment)
        force_overwrite_args = etl.PARSER.parse_args(
            [etl._MODE_UPLOAD] + self.common_course_args + [
                '--force_overwrite'])
        etl.main(
            force_overwrite_args,
            environment_class=testing.FakeEnvironment)
        archive = etl._Archive(self.archive_path)
        archive.open('r')
        context = etl_lib.get_context(self.upload_course_args.course_url_prefix)
        filesystem_contents = context.fs.impl.list(appengine_config.BUNDLE_ROOT)
        self.assertEqual(
            len(archive.manifest.entities),
            len(filesystem_contents) + len(self._get_all_entity_files()))
        self.assertEqual(self.new_course_title, context.get_title())
        units = etl_lib.get_course(context).get_units()
        spot_check_single_unit = [u for u in units if u.unit_id == 14][0]
        self.assertEqual('Interpreting results', spot_check_single_unit.title)
        for unit in units:
            self.assertTrue(unit.title)
        for entity in archive.manifest.entities:
            _, tail = os.path.split(entity.path)
            if tail in self._get_all_entity_files():
                continue
            full_path = os.path.join(
                appengine_config.BUNDLE_ROOT,
                etl._Archive.get_external_path(entity.path))
            stream = context.fs.impl.get(full_path)
            self.assertEqual(entity.is_draft, stream.metadata.is_draft)

    def test_upload_valid_encoded_string_reference(self):
        with Namespace(self.namespace):
            string_key = db.Key.from_path('EtlTestEntityPii', '334-44-1234')
        self._test_upload_valid_reference(
            string_key, ['--privacy', '--privacy_secret', 'super_seekrit'])

    def test_upload_valid_encoded_numeric_reference(self):
        with Namespace(self.namespace):
            numeric_key = db.Key.from_path('EtlTestEntityPii', 334441234)
        self._test_upload_valid_reference(
            numeric_key, ['--privacy', '--privacy_secret', 'super_seekrit'])

    def test_upload_valid_plaintext_string_reference(self):
        with Namespace(self.namespace):
            string_key = db.Key.from_path('EtlTestEntityPii', '334-44-1234')
        self._test_upload_valid_reference(string_key, [])

    def test_upload_valid_plaintext_numeric_reference(self):
        with Namespace(self.namespace):
            numeric_key = db.Key.from_path('EtlTestEntityPii', 334441234)
        self._test_upload_valid_reference(numeric_key, [])

    def _download_archive(self, extra_args=None):
        extra_args = extra_args or []
        etl.main(etl.PARSER.parse_args([etl._MODE_DOWNLOAD] +
                                       self.common_datastore_args +
                                       extra_args),
                 environment_class=testing.FakeEnvironment)

    def _clear_datastore(self):
        self.swap(
            etl, '_raw_input',
            lambda x: etl._DELETE_DATASTORE_CONFIRMATION_INPUT)
        etl.main(etl.PARSER.parse_args([etl._MODE_DELETE] +
                                       self.common_datastore_args),
                 environment_class=testing.FakeEnvironment)

    def _upload_archive(self, extra_args=None):
        extra_args = extra_args or []
        etl.main(etl.PARSER.parse_args([etl._MODE_UPLOAD] +
                                       self.common_datastore_args +
                                       extra_args),
                 environment_class=testing.FakeEnvironment)

    def _test_upload_valid_reference(self, pii_key, download_args):
        # Make ETL archive of item with PII in key using encoding.
        sites.setup_courses(self.raw)
        joes_score = 12345
        with Namespace(self.namespace):
            pii = EtlTestEntityPii(key=pii_key, name='Joe', score=joes_score)
            pii.put()
            ref = EtlTestEntityPiiReference(pii=pii)
            ref.put()

        self._download_archive(download_args)
        self._clear_datastore()
        self._upload_archive()

        # Upload data.

        with Namespace(self.namespace):
            piis = EtlTestEntityPii.all().fetch(100)
            refs = EtlTestEntityPiiReference.all().fetch(100)
            self.assertEquals(1, len(piis))
            self.assertEquals(1, len(refs))
            self.assertEquals(joes_score, piis[0].score)
            self.assertEquals(None, piis[0].name,
                              'Blacklisted field should be None')
            self.assertEquals(
                joes_score, refs[0].pii.score,
                'Reference by key using explicit name where key is PII')

    def test_upload_null_encoded_reference(self):
        self._test_upload_null_reference(['--privacy',
                                          '--privacy_secret', 'super_seekrit'])

    def test_upload_null_plaintext_reference(self):
        self._test_upload_null_reference([])

    def _test_upload_null_reference(self, download_args):
        # Make ETL archive of item with PII in key using encoding.
        sites.setup_courses(self.raw)
        with Namespace(self.namespace):
            ref = EtlTestEntityPiiReference(pii=None)
            ref.put()

        self._download_archive(download_args)
        self._clear_datastore()
        self._upload_archive()

        with Namespace(self.namespace):
            refs = EtlTestEntityPiiReference.all().fetch(100)
            self.assertEquals(1, len(refs))
            self.assertEquals(None, refs[0].pii)

    def test_upload_unsupported_type_fails(self):
        sites.setup_courses(self.raw)
        with Namespace(self.namespace):
            EtlTestEntityIllegal(score=123).put()
        etl.main(etl.PARSER.parse_args([etl._MODE_DOWNLOAD] +
                                       self.common_datastore_args),
                 environment_class=testing.FakeEnvironment)

        with self.assertRaises(SystemExit):
            etl.main(etl.PARSER.parse_args([etl._MODE_UPLOAD] +
                                           self.common_datastore_args),
                     environment_class=testing.FakeEnvironment)

    def test_upload_with_pre_existing_data(self):
        # make archive file with one element.
        sites.setup_courses(self.raw)
        with Namespace(self.namespace):
            EtlTestEntityPii(name='Fred').put()

        self._download_archive()
        # Upload that file - should fail since item still exists.
        with self.assertRaises(SystemExit):
            self._upload_archive()

        # Upload with --force_overwrite should succeed where previous failed.
        self._upload_archive(['--force_overwrite'])

    def test_upload_empty_archive_fails(self):
        sites.setup_courses(self.raw)
        self._download_archive()
        with self.assertRaises(SystemExit):
            self._upload_archive()

    def test_upload_with_no_classes_allowed_fails(self):
        # make archive file with one element.
        sites.setup_courses(self.raw)
        with Namespace(self.namespace):
            pii = EtlTestEntityPii(name='Fred')
            pii.put()

        self._download_archive()
        self._clear_datastore()

        # Upload should fail since --datastore_types does not mention
        # only type in archive.
        with self.assertRaises(SystemExit):
            self._upload_archive(['--datastore_types=FooBar'])

        # Upload should fail since --exclude_types names the
        # only type in archive.
        with self.assertRaises(SystemExit):
            self._upload_archive(['--exclude_types=EtlTestEntityPii'])

    def _build_entity_batch(self):
        ret = []
        for _ in xrange(etl.PARSER.get_default('batch_size')):
            ret.append(EtlTestEntityPii(score=self.make_items_distinct_counter))
            self.make_items_distinct_counter += 1
        return ret

    def test_upload_resumption_with_trivial_quantity(self):
        sites.setup_courses(self.raw)
        with Namespace(self.namespace):
            thing_one = EtlTestEntityPii(name='Thing One')
            thing_one.put()
            thing_two = EtlTestEntityPii(name='Thing Two')
            thing_two.put()
        self._download_archive()
        self._clear_datastore()

        # Simulate 1st upload having partially succeeded.
        with Namespace(self.namespace):
            thing_one.put()

        # Should not barf.
        self._upload_archive(['--resume'])
        self.assertIn('Resuming upload at item number 0 of 2.',
                      self.get_log())

        # Upload again; everything should be seen to be present.
        self._upload_archive(['--resume'])
        self.assertIn('All 2 entities already uploaded; skipping',
                      self.get_log())

    def test_upload_resumption_with_batch_quantity(self):
        sites.setup_courses(self.raw)
        with Namespace(self.namespace):
            batch_one = self._build_entity_batch()
            batch_two = self._build_entity_batch()
            db.put(batch_one)
            db.put(batch_two)
        self._download_archive()

        # Simulate 1st batch having partially succeeded, 2nd batch not at all.
        self._clear_datastore()
        with Namespace(self.namespace):
            db.put([x for x in batch_one if x.score % 2])
        self._upload_archive(['--resume'])
        self.assertIn('Resuming upload at item number 0 of 40.',
                      self.get_log())

        # Simulate 1st batch having fully succeeded, 2nd batch not at all.
        self._clear_datastore()
        with Namespace(self.namespace):
            db.put(batch_one)
        self._upload_archive(['--resume'])
        self.assertIn('Resuming upload at item number 20 of 40.',
                      self.get_log())

        # Simulate 1st batch having fully succeeded, 2nd batch partial
        self._clear_datastore()
        with Namespace(self.namespace):
            db.put(batch_one)
            db.put([x for x in batch_one if x.score % 2])
        self._upload_archive(['--resume'])
        self.assertIn('Resuming upload at item number 20 of 40.',
                      self.get_log())

        # Upload again; everything should be seen to be present.
        self._upload_archive(['--resume'])
        self.assertIn('All 40 entities already uploaded; skipping',
                      self.get_log())

    def test_is_identity_transform_when_privacy_false(self):
        self.assertEqual(
            1, etl._get_privacy_transform_fn(False, 'no_effect')(1))
        self.assertEqual(
            1, etl._get_privacy_transform_fn(False, 'other_value')(1))

    def test_is_hmac_sha_2_256_when_privacy_true(self):
        # Must run etl.main() to get crypto module loaded.
        args = etl.PARSER.parse_args(['download'] + self.common_course_args)
        etl.main(args, environment_class=testing.FakeEnvironment)
        self.assertEqual(
            crypto.hmac_sha_2_256_transform('secret', 'value'),
            # Testing protected functions. pylint: disable=protected-access
            etl._get_privacy_transform_fn(True, 'secret')('value'))


# TODO(johncox): re-enable these tests once we figure out how to make webtest
# play nice with remote_api.
class EtlRemoteEnvironmentTestCase(actions.TestBase):
    """Tests tools/etl/remote.py."""

    # Method name determined by superclass. pylint: disable=g-bad-name
    def setUp(self):
        super(EtlRemoteEnvironmentTestCase, self).setUp()
        self.test_environ = copy.deepcopy(os.environ)

    # Allow access to protected members under test.
    # pylint: disable=protected-access
    def disabled_test_can_establish_environment_in_dev_mode(self):
        # Stub the call that requires user input so the test runs unattended.
        self.swap(__builtin__, 'raw_input', lambda _: 'username')
        self.assertEqual(os.environ['SERVER_SOFTWARE'], remote.SERVER_SOFTWARE)
        # establish() performs RPC. If it doesn't throw, we're good.
        remote.Environment('mycourse', 'localhost:8080').establish()

    def disabled_test_can_establish_environment_in_test_mode(self):
        self.test_environ['SERVER_SOFTWARE'] = remote.TEST_SERVER_SOFTWARE
        self.swap(os, 'environ', self.test_environ)
        # establish() performs RPC. If it doesn't throw, we're good.
        remote.Environment('mycourse', 'localhost:8080').establish()


class CourseUrlRewritingTest(CourseUrlRewritingTestBase):
    """Run all existing tests using '/courses/pswg' base URL rewrite rules."""


class VirtualFileSystemTest(VirtualFileSystemTestBase):
    """Run all existing tests using virtual local file system."""


class MemcacheTestBase(actions.TestBase):
    """Executes all tests with memcache enabled."""

    def setUp(self):  # pylint: disable=g-bad-name
        super(MemcacheTestBase, self).setUp()
        config.Registry.test_overrides = {models.CAN_USE_MEMCACHE.name: True}

    def tearDown(self):  # pylint: disable=g-bad-name
        config.Registry.test_overrides = {}
        super(MemcacheTestBase, self).tearDown()


class MemcacheTest(MemcacheTestBase):
    """Executes all tests with memcache enabled."""


class PiiHolder(entities.BaseEntity):
    user_id = db.StringProperty(indexed=True)
    age = db.IntegerProperty(indexed=False)
    class_rank = db.IntegerProperty(indexed=False)
    registration_date = db.DateTimeProperty(indexed=True, required=True)
    class_goal = db.StringProperty(indexed=False, required=True)
    albedo = db.FloatProperty(indexed=False)

    _PROPERTY_EXPORT_BLACKLIST = [user_id, age]


class TransformsEntitySchema(actions.TestBase):

    def test_schema(self):
        schema = transforms.get_schema_for_entity(PiiHolder)
        schema = schema.get_json_schema_dict()['properties']
        self.assertNotIn('user_id', schema)
        self.assertNotIn('age', schema)
        self.assertIn('class_rank', schema)
        self.assertEquals('integer', schema['class_rank']['type'])
        self.assertIn('optional', schema['class_rank'])
        self.assertEquals(True, schema['class_rank']['optional'])
        self.assertIn('registration_date', schema)
        self.assertEquals('datetime', schema['registration_date']['type'])
        self.assertNotIn('optional', schema['registration_date'])
        self.assertIn('class_goal', schema)
        self.assertEquals('string', schema['class_goal']['type'])
        self.assertNotIn('optional', schema['class_goal'])
        self.assertIn('albedo', schema)
        self.assertEquals('number', schema['albedo']['type'])
        self.assertIn('optional', schema['albedo'])
        self.assertEquals(True, schema['albedo']['optional'])


class TransformsJsonFileTestCase(actions.TestBase):
    """Tests for models/transforms.py's JsonFile."""

    # Method name determined by superclass. pylint: disable=g-bad-name
    def setUp(self):
        super(TransformsJsonFileTestCase, self).setUp()
        # Treat as module-protected. pylint: disable=protected-access
        self.path = os.path.join(self.test_tempdir, 'file.json')
        self.reader = transforms.JsonFile(self.path)
        self.writer = transforms.JsonFile(self.path)
        self.first = 1
        self.second = {'c': 'c_value', 'd': {'nested': 'e'}}

    def tearDown(self):
        self.reader.close()
        self.writer.close()
        super(TransformsJsonFileTestCase, self).tearDown()

    def test_round_trip_of_file_with_zero_records(self):
        self.writer.open('w')
        self.writer.close()
        self.reader.open('r')
        self.assertEqual([], [entity for entity in self.reader])
        self.reader.reset()
        self.assertEqual({'rows': []}, self.reader.read())

    def test_round_trip_of_file_with_one_record(self):
        self.writer.open('w')
        self.writer.write(self.first)
        self.writer.close()
        self.reader.open('r')
        self.assertEqual([self.first], [entity for entity in self.reader])
        self.reader.reset()
        self.assertEqual({'rows': [self.first]}, self.reader.read())

    def test_round_trip_of_file_with_multiple_records(self):
        self.writer.open('w')
        self.writer.write(self.first)
        self.writer.write(self.second)
        self.writer.close()
        self.reader.open('r')
        self.assertEqual(
            [self.first, self.second], [entity for entity in self.reader])
        self.reader.reset()
        self.assertEqual(
            {'rows': [self.first, self.second]}, self.reader.read())


class ImportAssessmentTests(DatastoreBackedCourseTest):
    """Functional tests for assessments."""

    def test_assessment_old_style(self):

        # test that assessment version 1.3 with empty html_content
        # is not assessment version 1.2
        sites.setup_courses('course:/test::ns_test, course:/:/')
        course = courses.Course(None, app_context=sites.get_all_courses()[0])
        a1 = course.add_assessment()
        course.save()
        assert course.find_unit_by_id(a1.unit_id)
        assert not courses.has_at_least_one_old_style_assessment(course)
        assert courses.has_only_new_style_assessments(course)

        # test that assessment version 1.3 with empty html_content
        # and js content is considered old-style assessment
        a2 = course.add_assessment()
        a2.title = 'Assessment 2'
        course.update_unit(a2)
        assessment_content = open(os.path.join(
            appengine_config.BUNDLE_ROOT,
            'assets/js/assessment-Pre.js'), 'rb').readlines()
        assessment_content = u''.join(assessment_content)
        course.set_assessment_content(a2, assessment_content, [])
        course.save()
        assert courses.has_at_least_one_old_style_assessment(course)
        assert not courses.has_only_new_style_assessments(course)

    def test_import_empty_assessment(self):
        sites.setup_courses('course:/a::ns_a, course:/b::ns_b')
        src = courses.Course(None, app_context=sites.get_all_courses()[0])
        src.add_assessment()
        src.save()
        dst = courses.Course(None, app_context=sites.get_all_courses()[1])
        errors = []
        dst.import_from(src.app_context, errors)
        self.assertEqual(0, len(errors))
        self.assertEqual(1, len(dst.get_assessment_list()))
        assert courses.has_only_new_style_assessments(dst)

    def test_import_course13_w_assessment12(self):
        """Tests importing a new-style course with old-style assessment."""

        # set up the src and dst courses ver.13
        sites.setup_courses('course:/a::ns_a, course:/b::ns_b, course:/:/')
        src_app_ctx = sites.get_all_courses()[0]
        src_course = courses.Course(None, app_context=src_app_ctx)
        dst_app_ctx = sites.get_all_courses()[0]
        dst_course = courses.Course(None, app_context=dst_app_ctx)

        # add old-style assessment to the src
        a1_title = 'Assessment content version 12'
        a1 = src_course.add_assessment()
        a1.title = a1_title
        src_course.update_unit(a1)
        assessment_content = open(os.path.join(
            appengine_config.BUNDLE_ROOT,
            'assets/js/assessment-Pre.js'), 'rb').readlines()
        assessment_content = u''.join(assessment_content)
        errors = []
        src_course.set_assessment_content(
            a1, assessment_content, errors)

        # add new style assessment to src
        a2_title = 'Assessment content version 13'
        a2_html_content = 'content'
        a2 = src_course.add_assessment()
        a2.title = a2_title
        a2.html_content = a2_html_content
        a2.html_check_answers = 'check'
        a2.html_review_form = 'review'
        a2.workflow_yaml = 'a: 3'
        src_course.update_unit(a2)

        # save course and confirm assessments
        src_course.save()
        assert not errors
        assessment_content_stored = src_course.app_context.fs.get(os.path.join(
            src_course.app_context.get_home(),
            src_course.get_assessment_filename(a1.unit_id)))
        assert assessment_content == assessment_content_stored

        # import course
        dst_course.import_from(src_app_ctx, errors)

        # assert old-style assessment has been ported to a new-style one
        dst_a1 = dst_course.get_units()[0]
        self.assertEqual('A', dst_a1.type)
        self.assertEqual(a1_title, dst_a1.title)
        assert dst_a1.html_content
        dst_a2 = dst_course.get_units()[1]
        self.assertEqual('A', dst_a1.type)
        self.assertEqual(a2_title, dst_a2.title)
        self.assertEqual(a2_html_content, dst_a2.html_content)

        # cleaning up
        sites.reset_courses()


class ImportActivityTests(DatastoreBackedCourseTest):
    """Functional tests for importing legacy activities into lessons."""

    FREETEXT_QUESTION = """
var activity = [
  { questionType: 'freetext',
    correctAnswerRegex: /abc/i,
    correctAnswerOutput: "Correct.",
    incorrectAnswerOutput: "Try again.",
    showAnswerOutput: "A hint."
  }
];
"""
    MULTPLE_CHOICE_QUESTION = """
var activity = [
  {questionType: 'multiple choice',
    choices: [
      ['a', false, 'A'],
      ['b', true, 'B'],
      ['c', false, 'C'],
      ['d', false, 'D']
    ]
  }
];
"""
    MULTPLE_CHOICE_GROUP_QUESTION = """
var activity = [
  {questionType: 'multiple choice group',
    questionsList: [
      {
        questionHTML: 'choose a',
        choices: ['aa', 'bb'],
        correctIndex: 0
      },
      {
        questionHTML: 'choose b or c',
        choices: ['aa', 'bb', 'cc'],
        correctIndex: [1, 2]
      }
    ]
    allCorrectOutput: 'unused',
    someIncorrectOutput: 'also unused'
  }
];
"""

    def setUp(self):
        super(ImportActivityTests, self).setUp()
        self.course = courses.Course(None, app_context=self.app_context)
        self.unit = self.course.add_unit()
        self.lesson = self.course.add_lesson(self.unit)
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace(self.app_context.get_namespace_name())

    def tearDown(self):
        namespace_manager.set_namespace(self.old_namespace)
        super(ImportActivityTests, self).tearDown()

    def test_hide_activity(self):
        """Tests old-style activity annotations."""

        # set up a version 13 course
        sites.setup_courses('course:/test::ns_test, course:/:/')
        app_ctx = sites.get_all_courses()[0]
        course = courses.Course(None, app_context=app_ctx)

        # add a unit & a lesson w.o. activity
        unit = course.add_unit()
        course.add_lesson(unit)
        course.save()

        # admin logs in and gets the lesson for editing
        actions.login('admin@foo.com', is_admin=True)
        response = self.get('/test/dashboard?action=edit_lesson&key=2')
        self.assertEqual(200, response.status_int)

        # assert that there are 3 hidden annotations
        self.assert_num_hidden_annotations(response.body, 3)

        # add a lesson w. old-style activity
        lesson = course.add_lesson(unit)
        lesson.scored = True
        lesson.has_activity = True
        lesson.activity_title = 'activity title'
        lesson.activity_listed = True
        errors = []
        course.set_activity_content(
            lesson, unicode(self.FREETEXT_QUESTION), errors)
        assert not errors
        course.save()

        # assert that there are no hidden annotations
        actions.login('admin@foo.com', is_admin=True)
        response = self.get('/test/dashboard?action=edit_lesson&key=3')
        self.assertEqual(200, response.status_int)
        self.assert_num_hidden_annotations(response.body, 0)

        # cleaning up
        sites.reset_courses()

    def assert_num_hidden_annotations(self, body, n):
        start_marker = 'load_schema_with_annotations = function(schema)'
        suffix = body.split(start_marker)[1]
        end_marker = re.compile(r'\s+}')
        func_body = end_marker.split(suffix)[0]
        self.assertEqual(n, func_body.count('hidden'))

    def test_import_lesson13_w_activity12_to_lesson13(self):

        # Setup the src and destination courses.
        sites.setup_courses('course:/a::ns_a, course:/b::ns_b')
        src_ctx = sites.get_all_courses()[0]
        src_course = courses.Course(None, app_context=src_ctx)
        dst_course = courses.Course(
            None, app_context=sites.get_all_courses()[1])

        # Add a unit & a lesson
        title = 'activity title'
        src_unit = src_course.add_unit()
        src_lesson = src_course.add_lesson(src_unit)
        src_lesson.title = 'Test Lesson'
        src_lesson.scored = True
        src_lesson.objectives = 'objectives'
        src_lesson.video = 'video'
        src_lesson.notes = 'notes'
        src_lesson.duration = 'duration'
        src_lesson.now_available = True
        src_lesson.has_activity = True
        src_lesson.activity_title = title
        src_lesson.activity_listed = True
        src_lesson.properties = {'key': 'value'}
        src_course.save()

        # Add an old style activity to the src lesson
        activity = unicode(self.FREETEXT_QUESTION)
        errors = []
        src_course.set_activity_content(src_lesson, activity, errors)
        assert not errors

        # Import course and verify activities
        errors = []
        dst_course.import_from(src_ctx, errors)
        self.assertEqual(0, len(errors))
        u1, l1, a1, _ = self.calc_course_stats(src_course)
        u2, l2, _, _ = self.calc_course_stats(dst_course)
        self.assertEqual(1, l1)
        self.assertEqual(2, l2)
        self.assertEqual(u1, u2)
        self.assertEqual(l1 + a1, l2)
        new_lesson = dst_course.get_lessons('1')[1]
        assert 'quid=' in new_lesson.objectives
        self.assertEqual(title, new_lesson.title)
        assert courses.has_at_least_one_old_style_activity(src_course)
        assert courses.has_only_new_style_activities(dst_course)

    def test_import_free_text_activity(self):
        text = self.FREETEXT_QUESTION
        content, noverify_text = verify.convert_javascript_to_python(
            text, 'activity')
        activity = verify.evaluate_python_expression_from_text(
            content, 'activity', verify.Activity().scope, noverify_text)

        qid, instance_id = models.QuestionImporter.import_question(
            activity['activity'][0], self.unit, self.lesson.title, 1, ['task'])
        assert qid and isinstance(qid, (int, long))
        assert re.match(r'^[a-zA-Z0-9]{12}$', instance_id)

        question = models.QuestionDAO.load(qid)
        self.assertEqual(question.type, models.QuestionDTO.SHORT_ANSWER)
        self.assertEqual(question.dict['version'], '1.5')
        self.assertEqual(
            question.dict['description'],
            'Imported from unit "New Unit", lesson "New Lesson" (question #1)')
        self.assertEqual(question.dict['question'], 'task')
        self.assertEqual(question.dict['hint'], 'A hint.')
        self.assertEqual(question.dict['defaultFeedback'], 'Try again.')
        self.assertEqual(len(question.dict['graders']), 1)

        grader = question.dict['graders'][0]
        self.assertEqual(grader['score'], 1.0)
        self.assertEqual(grader['matcher'], 'regex')
        self.assertEqual(grader['response'], '/abc/i')
        self.assertEqual(grader['feedback'], 'Correct.')

    def test_import_free_text_with_missing_fields(self):
        # correctAnswerOutput and incorrectAnswerOutput are missing
        text = """
var activity = [
  { questionType: 'freetext',
    correctAnswerRegex: /abc/i,
    showAnswerOutput: "A hint."
  }
];
"""
        content, noverify_text = verify.convert_javascript_to_python(
            text, 'activity')
        activity = verify.evaluate_python_expression_from_text(
            content, 'activity', verify.Activity().scope, noverify_text)

        qid, instance_id = models.QuestionImporter.import_question(
            activity['activity'][0], self.unit, self.lesson.title, 1, ['task'])
        assert qid and isinstance(qid, (int, long))
        assert re.match(r'^[a-zA-Z0-9]{12}$', instance_id)

        question = models.QuestionDAO.load(qid)
        self.assertEqual(question.type, models.QuestionDTO.SHORT_ANSWER)
        self.assertEqual(question.dict['version'], '1.5')
        self.assertEqual(
            question.dict['description'],
            'Imported from unit "New Unit", lesson "New Lesson" (question #1)')
        self.assertEqual(question.dict['question'], 'task')
        self.assertEqual(question.dict['hint'], 'A hint.')
        self.assertEqual(question.dict['defaultFeedback'], '')
        self.assertEqual(len(question.dict['graders']), 1)

        grader = question.dict['graders'][0]
        self.assertEqual(grader['score'], 1.0)
        self.assertEqual(grader['matcher'], 'regex')
        self.assertEqual(grader['response'], '/abc/i')
        self.assertEqual(grader['feedback'], '')

    def test_activity_import_unique_constraint(self):
        text = self.FREETEXT_QUESTION
        content, noverify_text = verify.convert_javascript_to_python(
            text, 'activity')
        activity = verify.evaluate_python_expression_from_text(
            content, 'activity', verify.Activity().scope, noverify_text)

        qid, _ = models.QuestionImporter.import_question(
            activity['activity'][0], self.unit, self.lesson.title, 1, ['task'])
        assert qid and isinstance(qid, (int, long))

        self.assertRaises(models.CollisionError,
                          models.QuestionImporter.import_question,
                          activity['activity'][0], self.unit,
                          self.lesson.title, 1, ['task'])

    def test_import_multiple_choice_activity(self):
        text = self.MULTPLE_CHOICE_QUESTION
        content, noverify_text = verify.convert_javascript_to_python(
            text, 'activity')
        activity = verify.evaluate_python_expression_from_text(
            content, 'activity', verify.Activity().scope, noverify_text)

        verify.Verifier().verify_activity_instance(activity, 'none')
        qid, instance_id = models.QuestionImporter.import_question(
            activity['activity'][0], self.unit, self.lesson.title, 1, ['task'])
        assert qid and isinstance(qid, (int, long))
        assert re.match(r'^[a-zA-Z0-9]{12}$', instance_id)

        question = models.QuestionDAO.load(qid)
        self.assertEqual(question.type, models.QuestionDTO.MULTIPLE_CHOICE)
        self.assertEqual(question.dict['version'], '1.5')
        self.assertEqual(
            question.dict['description'],
            'Imported from unit "New Unit", lesson "New Lesson" (question #1)')
        self.assertEqual(question.dict['question'], 'task')
        self.assertEqual(question.dict['multiple_selections'], False)
        self.assertEqual(len(question.dict['choices']), 4)

        choices = question.dict['choices']
        choices_data = [
            ['a', 0.0, 'A'], ['b', 1.0, 'B'], ['c', 0.0, 'C'],
            ['d', 0.0, 'D']]
        for i, choice in enumerate(choices):
            self.assertEqual(choice['text'], choices_data[i][0])
            self.assertEqual(choice['score'], choices_data[i][1])
            self.assertEqual(choice['feedback'], choices_data[i][2])

    def test_import_multiple_choice_group_activity(self):
        text = self.MULTPLE_CHOICE_GROUP_QUESTION
        content, noverify_text = verify.convert_javascript_to_python(
            text, 'activity')
        activity = verify.evaluate_python_expression_from_text(
            content, 'activity', verify.Activity().scope, noverify_text)
        verify.Verifier().verify_activity_instance(activity, 'none')

        qid, instance_id = models.QuestionImporter.import_question(
            activity['activity'][0], self.unit, self.lesson.title, 1, ['task'])
        assert qid and isinstance(qid, (int, long))
        assert re.match(r'^[a-zA-Z0-9]{12}$', instance_id)

        question_group = models.QuestionGroupDAO.load(qid)
        self.assertEqual(question_group.dict['version'], '1.5')
        self.assertEqual(
            question_group.dict['description'],
            'Imported from unit "New Unit", lesson "New Lesson" (question #1)')
        self.assertEqual(len(question_group.dict['items']), 2)

        items = question_group.dict['items']
        self.assertEqual(items[0]['weight'], 1.0)
        self.assertEqual(items[1]['weight'], 1.0)

        # The first question is multiple choice with single selection
        qid = items[0]['question']
        question = models.QuestionDAO.load(qid)
        self.assertEqual(question.type, models.QuestionDTO.MULTIPLE_CHOICE)
        self.assertEqual(question.dict['version'], '1.5')
        self.assertEqual(
            question.dict['description'],
            (
                'Imported from unit "New Unit", lesson "New Lesson" '
                '(question #1, part #1)'))
        self.assertEqual(question.dict['question'], 'choose a')
        self.assertEqual(question.dict['multiple_selections'], False)
        self.assertEqual(len(question.dict['choices']), 2)

        choices = question.dict['choices']
        self.assertEqual(choices[0]['text'], 'aa')
        self.assertEqual(choices[0]['score'], 1.0)
        self.assertEqual(choices[1]['text'], 'bb')
        self.assertEqual(choices[1]['score'], 0.0)

        # The second question is multiple choice with multiple selection
        qid = items[1]['question']
        question = models.QuestionDAO.load(qid)
        self.assertEqual(question.type, models.QuestionDTO.MULTIPLE_CHOICE)
        self.assertEqual(question.dict['version'], '1.5')
        self.assertEqual(
            question.dict['description'],
            (
                'Imported from unit "New Unit", lesson "New Lesson" '
                '(question #1, part #2)'))
        self.assertEqual(question.dict['question'], 'choose b or c')
        self.assertEqual(question.dict['multiple_selections'], True)
        self.assertEqual(len(question.dict['choices']), 3)

        choices = question.dict['choices']
        self.assertEqual(choices[0]['text'], 'aa')
        self.assertEqual(choices[0]['score'], -1.0)
        self.assertEqual(choices[1]['text'], 'bb')
        self.assertEqual(choices[1]['score'], 0.5)
        self.assertEqual(choices[1]['text'], 'bb')
        self.assertEqual(choices[1]['score'], 0.5)


class NamespaceTest(actions.TestBase):

    def test_namespace_context_manager(self):
        pre_test_namespace = namespace_manager.get_namespace()
        with Namespace('xyzzy'):
            self.assertEqual(namespace_manager.get_namespace(), 'xyzzy')
            with Namespace('plugh'):
                self.assertEqual(namespace_manager.get_namespace(), 'plugh')
            self.assertEqual(namespace_manager.get_namespace(), 'xyzzy')
        self.assertEqual(namespace_manager.get_namespace(), pre_test_namespace)

    def test_namespace_context_manager_handles_exception(self):
        pre_test_namespace = namespace_manager.get_namespace()
        try:
            with Namespace('xyzzy'):
                self.assertEqual(namespace_manager.get_namespace(), 'xyzzy')
                raise RuntimeError('No way, Jose')
        except RuntimeError:
            pass
        self.assertEqual(namespace_manager.get_namespace(), pre_test_namespace)


ALL_COURSE_TESTS = (
    StudentAspectTest, AssessmentTest, CourseAuthorAspectTest,
    StaticHandlerTest, AdminAspectTest, PeerReviewControllerTest,
    PeerReviewDashboardAdminTest, PeerReviewAnalyticsTest)

MemcacheTest.__bases__ += (InfrastructureTest,) + ALL_COURSE_TESTS
CourseUrlRewritingTest.__bases__ += ALL_COURSE_TESTS
VirtualFileSystemTest.__bases__ += ALL_COURSE_TESTS
DatastoreBackedSampleCourseTest.__bases__ += ALL_COURSE_TESTS
