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

import datetime
import json
import logging
import os
import re
import shutil
import urllib
import appengine_config
from controllers import lessons
from controllers import sites
from controllers import utils
from controllers.utils import XsrfTokenManager
from models import config
from models import jobs
from models import models
from models.utils import get_all_scores
from models.utils import get_score
from modules.announcements.announcements import AnnouncementEntity
from tools import verify
import actions
from actions import assert_contains
from actions import assert_does_not_contain
from actions import assert_equals
from google.appengine.api import namespace_manager


class InfrastructureTest(actions.TestBase):
    """Test core infrastructure classes agnostic to specific user roles."""

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

        self.assert_queriable(AnnouncementEntity, 'date', datetime.date)
        self.assert_queriable(models.EventEntity, 'recorded_on')
        self.assert_queriable(models.Student, 'enrolled_on')
        self.assert_queriable(models.StudentAnswersEntity, 'updated_on')
        self.assert_queriable(jobs.DurableJobEntity, 'updated_on')

    def test_assets_and_date(self):
        """Verify semantics of all asset and data files."""

        def echo(unused_message):
            pass

        warnings, errors = verify.Verifier().load_and_verify_model(echo)
        assert not errors and not warnings

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

    def test_python_console(self):
        """Test access rights to the Python console."""

        email = 'test_python_console@google.com'

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
        actions.login(email, True)
        response = self.testapp.get('/admin?action=console')
        assert_equals(response.status_int, 200)

        response.form.set('code', 'print "foo" + "bar"')
        response = self.submit(response.form)
        assert_contains('foobar', response.body)

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
        json_dict = json.loads(response.body)
        assert json_dict['status'] == 401
        assert json_dict['message'] == 'Access denied.'

        # Check user has no rights to PUT verb.
        payload_dict = {}
        payload_dict['value'] = '666'
        payload_dict['is_draft'] = False
        request = {}
        request['key'] = 'gcb_config_update_interval_sec'
        request['payload'] = json.dumps(payload_dict)

        # Check XSRF token is required.
        response = self.testapp.put('/rest/config/item?%s' % urllib.urlencode(
            {'request': json.dumps(request)}), {})
        assert_equals(response.status_int, 200)
        assert_contains('"status": 403', response.body)

        # Check user still has no rights to PUT verb even if he somehow
        # obtained a valid XSRF token.
        request['xsrf_token'] = XsrfTokenManager.create_xsrf_token(
            'config-property-put')
        response = self.testapp.put('/rest/config/item?%s' % urllib.urlencode(
            {'request': json.dumps(request)}), {})
        assert_equals(response.status_int, 200)
        json_dict = json.loads(response.body)
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
            '/admin?action=config_override&name=gcb_admin_user_emails',
            response.body)
        assert_contains(
            '/admin?action=config_edit&name=gcb_config_update_interval_sec',
            response.body)

        # Check editor page has proper actions.
        response = self.testapp.get(
            '/admin?action=config_edit&name=gcb_config_update_interval_sec')
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

        actions.login(email, True)
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

        courses = 'course:/foo:/foo-data, course:/bar:/bar-data:nsbar'
        os.environ[sites.GCB_COURSES_CONFIG_ENV_VAR_NAME] = courses

        email = 'test_multiple_courses@google.com'

        actions.login(email, True)
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


class CourseAuthorAspectTest(actions.TestBase):
    """Tests the site from the Course Author perspective."""

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
        actions.login(email, True)
        response = self.get('dashboard')
        assert_contains('Google &gt; Dashboard &gt; Outline', response.body)

        # Tests outline view.
        response = self.get('dashboard')
        assert_contains('Unit 3 - Advanced techniques', response.body)

        # Test assets view.
        response = self.get('dashboard?action=assets')
        assert_contains('Google &gt; Dashboard &gt; Assets', response.body)
        assert_contains('data/lesson.csv', response.body)
        assert_contains('assets/css/main.css', response.body)
        assert_contains('assets/img/Image1.5.png', response.body)
        assert_contains('assets/js/activity-3.2.js', response.body)

        # Test settings view.
        response = self.get('dashboard?action=settings')
        assert_contains(
            'Google &gt; Dashboard &gt; Settings', response.body)
        assert_contains('course.yaml', response.body)
        assert_contains('title: \'Power Searching with Google\'', response.body)
        assert_contains('locale: \'en_US\'', response.body)

        # Tests student statistics view.
        response = self.get('dashboard?action=students')
        assert_contains(
            'Google &gt; Dashboard &gt; Students', response.body)
        assert_contains('have not been calculated yet', response.body)

        compute_form = response.forms['gcb-compute-student-stats']
        response = self.submit(compute_form)
        assert_equals(response.status_int, 302)
        assert len(self.taskq.GetTasks('default')) == 1

        response = self.get('dashboard?action=students')
        assert_contains('is running', response.body)

        self.execute_all_deferred_tasks()

        response = self.get('dashboard?action=students')
        assert_contains('were last updated on', response.body)
        assert_contains('currently enrolled: 1', response.body)
        assert_contains('total: 1', response.body)

        # Tests assessment statistics.
        old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace(self.namespace)
        try:
            for i in range(5):
                student = models.Student(key_name='key-%s' % i)
                student.is_enrolled = True
                student.scores = json.dumps({'test-assessment': i})
                student.put()
        finally:
            namespace_manager.set_namespace(old_namespace)

        response = self.get('dashboard?action=students')
        compute_form = response.forms['gcb-compute-student-stats']
        response = self.submit(compute_form)

        self.execute_all_deferred_tasks()

        response = self.get('dashboard?action=students')
        assert_contains('currently enrolled: 6', response.body)
        assert_contains(
            'test-assessment: completed 5, average score 2.0', response.body)

    def test_trigger_sample_announcements(self):
        """Test course author can trigger adding sample announcements."""
        email = 'test_announcements@google.com'
        name = 'Test Announcements'

        actions.login(email, True)
        actions.register(self, name)

        response = actions.view_announcements(self)
        assert_contains('Example Announcement', response.body)
        assert_contains('Welcome to the final class!', response.body)
        assert_does_not_contain('No announcements yet.', response.body)

    def test_manage_announcements(self):
        """Test course author can manage announcements."""
        email = 'test_announcements@google.com'
        name = 'Test Announcements'

        actions.login(email, True)
        actions.register(self, name)

        # add new
        response = actions.view_announcements(self)
        add_form = response.forms['gcb-add-announcement']
        response = self.submit(add_form)
        assert_equals(response.status_int, 302)

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

        actions.login(email, True)
        actions.register(self, name)

        response = actions.view_announcements(self)
        assert_does_not_contain('My Test Title', response.body)

        # REST GET existing item
        items = AnnouncementEntity.all().fetch(1)
        for item in items:
            response = self.get('rest/announcements/item?key=%s' % item.key())
            json_dict = json.loads(response.body)
            assert json_dict['status'] == 200
            assert 'message' in json_dict
            assert 'payload' in json_dict

            payload_dict = json.loads(json_dict['payload'])
            assert 'title' in payload_dict
            assert 'date' in payload_dict

            # REST PUT item
            payload_dict['title'] = 'My Test Title'
            payload_dict['date'] = '2012/12/31'
            payload_dict['is_draft'] = True
            request = {}
            request['key'] = str(item.key())
            request['payload'] = json.dumps(payload_dict)

            # Check XSRF is required.
            response = self.put('rest/announcements/item?%s' % urllib.urlencode(
                {'request': json.dumps(request)}), {})
            assert_equals(response.status_int, 200)
            assert_contains('"status": 403', response.body)

            # Check PUT works.
            request['xsrf_token'] = json_dict['xsrf_token']
            response = self.put('rest/announcements/item?%s' % urllib.urlencode(
                {'request': json.dumps(request)}), {})
            assert_equals(response.status_int, 200)
            assert_contains('"status": 200', response.body)

            # Confirm change is visible on the page.
            response = self.get('announcements')
            assert_contains('My Test Title (Draft)', response.body)

        # REST GET not-existing item
        response = self.get('rest/announcements/item?key=not_existent_key')
        json_dict = json.loads(response.body)
        assert json_dict['status'] == 404


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
        actions.login('admin@sample.com', True)
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
                json_dict = json.loads(response.body)
                assert json_dict['status'] == 401
            else:
                assert_equals(response.status_int, 200)

    def test_registration(self):
        """Test student registration."""
        email = 'test_registration@example.com'
        name1 = 'Test Student'
        name2 = 'John Smith'
        name3 = 'Pavel Simakov'

        actions.login(email)

        actions.register(self, name1)
        actions.check_profile(self, name1)

        actions.change_name(self, name2)
        actions.unregister(self)

        actions.register(self, name3)
        actions.check_profile(self, name3)

    def test_registration_closed(self):
        """Test student registration when course is full."""

        email = 'test_registration_closed@example.com'
        name = 'Test Registration Closed'

        # Override course.yaml settings by patching app_context.
        get_environ_old = sites.ApplicationContext.get_environ

        def get_environ_new(self):
            environ = get_environ_old(self)
            environ['reg_form']['can_register'] = False
            return environ

        sites.ApplicationContext.get_environ = get_environ_new

        # Try to ogin and register.
        actions.login(email)
        try:
            actions.register(self, name)
            raise actions.MustFail('Expected to fail.')
        except actions.MustFail as e:
            raise e
        except:
            pass

        # Clean up app_context.
        sites.ApplicationContext.get_environ = get_environ_old

    def test_permissions(self):
        """Test student permissions, and which pages they can view."""
        email = 'test_permissions@example.com'
        name = 'Test Permissions'

        actions.login(email)

        actions.register(self, name)
        actions.Permissions.assert_enrolled(self)

        actions.unregister(self)
        actions.Permissions.assert_unenrolled(self)

        actions.register(self, name)
        actions.Permissions.assert_enrolled(self)

    def test_login_and_logout(self):
        """Test if login and logout behave as expected."""
        email = 'test_login_logout@example.com'

        actions.Permissions.assert_logged_out(self)
        actions.login(email)

        actions.Permissions.assert_unenrolled(self)

        actions.logout()
        actions.Permissions.assert_logged_out(self)

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

    def test_attempt_activity_event(self):
        """Test activity attempt generates event."""

        email = 'test_attempt_activity_event@example.com'
        name = 'Test Attempt Activity Event'

        actions.login(email)
        actions.register(self, name)

        # Enable event recording.
        config.Registry.db_overrides[
            lessons.CAN_PERSIST_ACTIVITY_EVENTS.name] = True

        # Prepare event.
        request = {}
        request['source'] = 'test-source'
        request['payload'] = json.dumps({'Alice': 'Bob'})

        # Check XSRF token is required.
        response = self.post('rest/events?%s' % urllib.urlencode(
            {'request': json.dumps(request)}), {})
        assert_equals(response.status_int, 200)
        assert_contains('"status": 403', response.body)

        # Check PUT works.
        request['xsrf_token'] = XsrfTokenManager.create_xsrf_token(
            'event-post')
        response = self.post('rest/events?%s' % urllib.urlencode(
            {'request': json.dumps(request)}), {})
        assert_equals(response.status_int, 200)
        assert not response.body

        # Clean up.
        config.Registry.db_overrides = {}

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
        response.form.set('name', 'My New Name')
        response.form.set('xsrf_token', 'bad token')

        response = response.form.submit(expect_errors=True)
        assert_equals(response.status_int, 403)


class StaticHandlerTest(actions.TestBase):
    """Check serving of static resources."""

    def test_static_files_cache_control(self):
        """Test static/zip handlers use proper Cache-Control headers."""

        # Check static handler.
        response = self.get('/assets/css/main.css')
        assert_equals(response.status_int, 200)
        assert_contains('max-age=600', response.headers['Cache-Control'])
        assert_contains('public', response.headers['Cache-Control'])
        assert_does_not_contain('no-cache', response.headers['Cache-Control'])

        # Check zip file handler.
        response = self.get(
            '/static/inputex-3.1.0/src/inputex/assets/skins/sam/inputex.css')
        assert_equals(response.status_int, 200)
        assert_contains('max-age=600', response.headers['Cache-Control'])
        assert_contains('public', response.headers['Cache-Control'])
        assert_does_not_contain('no-cache', response.headers['Cache-Control'])


class AssessmentTest(actions.TestBase):
    """Test for assessments."""

    def submit_assessment(self, name, args):
        """Test student taking an assessment."""

        response = self.get('assessment?name=%s' % name)
        assert_contains(
            '<script src="assets/js/assessment-%s.js"></script>' % name,
            response.body)

        # Extract XSRF token from the page.
        match = re.search(r'assessmentXsrfToken = [\']([^\']+)', response.body)
        assert match
        xsrf_token = match.group(1)
        args['xsrf_token'] = xsrf_token

        response = self.post('answer', args)
        assert_equals(response.status_int, 200)
        return response

    def test_course_pass(self):
        """Test student passing final exam."""
        email = 'test_pass@google.com'
        name = 'Test Pass'

        post = {'assessment_type': 'postcourse', 'score': '100.00'}

        # Register.
        actions.login(email)
        actions.register(self, name)

        # Submit answer.
        response = self.submit_assessment('Post', post)
        assert_equals(response.status_int, 200)
        assert_contains('Your score is 70%', response.body)
        assert_contains('you have passed the course', response.body)

        # Check that the result shows up on the profile page.
        response = actions.check_profile(self, name)
        assert_contains('70', response.body)
        assert_contains('100', response.body)

    def test_assessments(self):
        """Test assessment scores are properly submitted and summarized."""
        email = 'test_assessments@google.com'
        name = 'Test Assessments'

        pre_answers = [{'foo': 'bar'}, {'Alice': 'Bob'}]
        pre = {
            'assessment_type': 'precourse', 'score': '1.00',
            'answers': json.dumps(pre_answers)}
        mid = {'assessment_type': 'midcourse', 'score': '2.00'}
        post = {'assessment_type': 'postcourse', 'score': '3.00'}
        second_mid = {'assessment_type': 'midcourse', 'score': '1.00'}
        second_post = {'assessment_type': 'postcourse', 'score': '100000'}

        # Register.
        actions.login(email)
        actions.register(self, name)

        old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace(self.namespace)
        try:
            # Check that no scores exist right now.
            student = models.Student.get_enrolled_student_by_email(email)
            assert len(get_all_scores(student)) == 0  # pylint: disable=C6411

            # Submit assessments and check the numbers of scores recorded.
            self.submit_assessment('Pre', pre)
            student = models.Student.get_enrolled_student_by_email(email)
            assert len(get_all_scores(student)) == 1

            self.submit_assessment('Mid', mid)
            student = models.Student.get_enrolled_student_by_email(email)
            assert len(get_all_scores(student)) == 2

            self.submit_assessment('Post', post)
            student = models.Student.get_enrolled_student_by_email(email)

            # Check final score also includes overall_score.
            assert len(get_all_scores(student)) == 4

            # Check assessment answers.
            answers = json.loads(
                models.StudentAnswersEntity.get_by_key_name(
                    student.user_id).data)
            assert pre_answers == answers['precourse']

            # pylint: disable-msg=g-explicit-bool-comparison
            assert [] == answers['midcourse']
            assert [] == answers['postcourse']
            # pylint: enable-msg=g-explicit-bool-comparison

            # Check that scores are recorded properly.
            student = models.Student.get_enrolled_student_by_email(email)
            assert int(get_score(student, 'precourse')) == 1
            assert int(get_score(student, 'midcourse')) == 2
            assert int(get_score(student, 'postcourse')) == 3
            assert (int(get_score(student, 'overall_score')) ==
                    int((0.30 * 2) + (0.70 * 3)))

            # Try posting a new midcourse exam with a lower score;
            # nothing should change.
            self.submit_assessment('Mid', second_mid)
            student = models.Student.get_enrolled_student_by_email(email)
            assert int(get_score(student, 'precourse')) == 1
            assert int(get_score(student, 'midcourse')) == 2
            assert int(get_score(student, 'postcourse')) == 3
            assert (int(get_score(student, 'overall_score')) ==
                    int((0.30 * 2) + (0.70 * 3)))

            # Now try posting a postcourse exam with a higher score and note
            # the changes.
            self.submit_assessment('Post', second_post)
            student = models.Student.get_enrolled_student_by_email(email)
            assert int(get_score(student, 'precourse')) == 1
            assert int(get_score(student, 'midcourse')) == 2
            assert int(get_score(student, 'postcourse')) == 100000
            assert (int(get_score(student, 'overall_score')) ==
                    int((0.30 * 2) + (0.70 * 100000)))
        finally:
            namespace_manager.set_namespace(old_namespace)


# TODO(psimakov): if mixin method names overlap, we don't run them all; must fix
class CourseUrlRewritingTest(
    StudentAspectTest, AssessmentTest, CourseAuthorAspectTest, AdminAspectTest):
    """Run existing tests using rewrite rules for '/courses/pswg' base URL."""

    def setUp(self):  # pylint: disable-msg=g-bad-name
        super(CourseUrlRewritingTest, self).setUp()

        self.base = '/courses/pswg'
        self.namespace = 'gcb-courses-pswg-tests-ns'

        courses = 'course:%s:/:%s' % (self.base, self.namespace)
        os.environ[sites.GCB_COURSES_CONFIG_ENV_VAR_NAME] = courses

    def tearDown(self):  # pylint: disable-msg=g-bad-name
        del os.environ[sites.GCB_COURSES_CONFIG_ENV_VAR_NAME]

        super(CourseUrlRewritingTest, self).tearDown()

    def canonicalize(self, href, response=None):
        """Canonicalize URL's using either <base> or self.base."""
        # Check if already canonicalized.
        if href.startswith(
                self.base) or utils.ApplicationHandler.is_absolute(href):
            pass
        else:
            # Look for <base> tag in the response to compute the canonical URL.
            if response:
                return super(CourseUrlRewritingTest, self).canonicalize(
                    href, response)

            # Prepend self.base to compute the canonical URL.
            if not href.startswith('/'):
                href = '/%s' % href
            href = '%s%s' % (self.base, href)

        self.audit_url(href)
        return href


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


class GeneratedCourse(object):
    """A helper class for a dynamically generated course content."""

    # All data for this test will be placed here.
    data_home = '/tmp/experimental/coursebuilder/test-data'

    def __init__(self, ns):
        self.path = ns

    @property
    def namespace(self):
        return 'ns%s' % self.path

    @property
    def title(self):
        return 'Power title-%s Searching with Google' % self.path

    @property
    def unit_title(self):
        return 'Interpreting unit-title-%s results' % self.path

    @property
    def lesson_title(self):
        return 'Word lesson-title-%s order matters' % self.path

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


class MultipleCoursesTest(actions.TestBase):
    """Test several courses running concurrently."""

    def prepare_canonical_course_data(self, course):
        """Make a copy of canonical course content."""
        clean_dir(course.home)

        def copytree(name):
            shutil.copytree(
                os.path.join(self.bundle_root, name),
                os.path.join(course.home, name))

        copytree('assets')
        copytree('data')
        copytree('views')

        shutil.copy(
            os.path.join(self.bundle_root, 'course.yaml'),
            os.path.join(course.home, 'course.yaml'))

        # Make all files writable.
        for root, unused_dirs, files in os.walk(course.home):
            for afile in files:
                fname = os.path.join(root, afile)
                os.chmod(fname, 0777)

    def modify_file(self, filename, find, replace):
        """Read, modify and write back the file."""

        lines = open(filename, 'r').readlines()
        text = ''.join(lines)

        # Make sure target text is not in the file.
        assert not replace in text
        text = text.replace(find, replace)
        assert replace in text

        open(filename, 'w').write(text)

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

        self.prepare_canonical_course_data(course)
        self.modify_canonical_course_data(course)

    def setUp(self):  # pylint: disable-msg=g-bad-name
        """Configure the test."""

        super(MultipleCoursesTest, self).setUp()

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
            'locale: \'ru_RU\'')

        # Configure courses.
        courses = '%s, %s, %s' % (
            'course:/courses/a:/data-a:nsa',
            'course:/courses/b:/data-b:nsb',
            'course:/courses/ru:/data-ru:nsru')
        os.environ[sites.GCB_COURSES_CONFIG_ENV_VAR_NAME] = courses

    def tearDown(self):  # pylint: disable-msg=g-bad-name
        """Clean up."""

        del os.environ[sites.GCB_COURSES_CONFIG_ENV_VAR_NAME]
        appengine_config.BUNDLE_ROOT = self.bundle_root
        super(MultipleCoursesTest, self).tearDown()

    def test_i18n(self):
        """Test course is properly internationalized."""

        response = self.get('/courses/%s/preview' % self.course_ru.path)

        # Assertions below fail because Russian is not being rendered. Why?
        assert_contains('Вход', response.body)
        assert_contains('Регистрация', response.body)
        assert_contains('Расписание', response.body)
        assert_contains('Курс', response.body)

    def test_courses_are_isolated(self):
        """Test each course serves its own assets, views and data."""

        # Pretend students visit courses.
        self.walk_the_course(self.course_a)
        self.walk_the_course(self.course_b)
        self.walk_the_course(self.course_a, False)
        self.walk_the_course(self.course_b, False)

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

    def walk_the_course(self, course, first_time=True):
        """Visit a course as a Student would."""

        # Check normal user has no access.
        actions.login(course.email)

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
            response.form.set('form01', course.name)
            response.form.action = '/courses/%s/register' % course.path
            response = self.submit(response.form)

            assert_contains(course.title, response.body)
            assert_contains(course.head, response.body)
            assert_contains('Thank you for registering for', response.body)

        # Check lesson page.
        response = self.testapp.get(
            '/courses/%s/unit?unit=1&lesson=5' % course.path)
        assert_contains(course.title, response.body)
        assert_contains(course.lesson_title, response.body)
        assert_contains(course.head, response.body)

        actions.logout()
