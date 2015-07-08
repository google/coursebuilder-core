# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Tests for modules/usage_reporting/*"""

__author__ = 'Mike Gainer (mgainer@google.com)'

from common import utils as common_utils
from models import data_removal as models_data_removal
from models import models
from modules.data_removal import data_removal
from modules.data_removal import removal_models
from modules.invitation import invitation
from modules.questionnaire import questionnaire
from modules.skill_map import competency
from modules.unsubscribe import unsubscribe
from tests.functional import actions


class DataRemovalTests(actions.TestBase):

    COURSE = 'data_removal_test'
    NAMESPACE = 'ns_' + COURSE
    ADMIN_EMAIL = 'admin@foo.com'
    STUDENT_EMAIL = 'student@foo.com'

    def setUp(self):
        super(DataRemovalTests, self).setUp()
        app_context = actions.simple_add_course(
            self.COURSE, self.ADMIN_EMAIL, 'Data Removal Test')

    def test_cron_handler_requires_reserved_header(self):
        response = self.get(
            data_removal.DataRemovalCronHandler.URL, expect_errors=True)
        self.assertEquals(403, response.status_int)
        self.assertEquals('Forbidden.', response.body)

    def test_cron_handler_ok_when_no_work_to_do(self):
        response = self.get(
            data_removal.DataRemovalCronHandler.URL,
            headers={'X-AppEngine-Cron': 'True'})
        self.assertEquals(200, response.status_int)
        self.assertEquals('OK.', response.body)

    def test_non_removal_policy(self):
        with actions.OverriddenEnvironment({
            data_removal.DATA_REMOVAL_SETTINGS_SECTION: {
                data_removal.REMOVAL_POLICY:
                data_removal.IndefiniteRetentionPolicy.get_name()}}):

            user = actions.login(self.STUDENT_EMAIL)
            actions.register(self, self.STUDENT_EMAIL, course=self.COURSE)

            with common_utils.Namespace(self.NAMESPACE):
                # After registration, we should have a student object, and no
                # ImmediateRemovalState instance due to the don't-care policy.
                student = models.Student.get_by_user(user)
                self.assertIsNotNone(student)
                self.assertIsNone(
                    removal_models.ImmediateRemovalState.get_by_user_id(
                        student.user_id))
                r = removal_models.BatchRemovalState.get_by_user_ids(
                    [student.user_id])
                self.assertEqual([None], r)

            actions.unregister(self, self.COURSE, do_data_removal=True)

            # Expect to see register, unregister events on queue.
            task_count = self.execute_all_deferred_tasks(
                models.StudentLifecycleObserver.QUEUE_NAME)
            self.assertEquals(2, task_count)
            with common_utils.Namespace(self.NAMESPACE):
                # After unregister, we should still have a student object.
                student = models.Student.get_by_user(user)
                self.assertIsNotNone(student)
                self.assertIsNone(
                    removal_models.ImmediateRemovalState.get_by_user_id(
                        student.user_id))
                r = removal_models.BatchRemovalState.get_by_user_ids(
                    [student.user_id])
                self.assertEqual([None], r)

    def test_immediate_removal_policy(self):
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL, course=self.COURSE)
        task_count = self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        self.assertEquals(1, task_count)  # registration.
        user_id = None

        with common_utils.Namespace(self.NAMESPACE):
            # After registration, we should have a student object, and
            # a ImmediateRemovalState instance.
            student = models.Student.get_by_user(user)
            self.assertIsNotNone(student)
            user_id = student.user_id
            removal_state = removal_models.ImmediateRemovalState.get_by_user_id(
                user_id)
            self.assertIsNotNone(removal_state)
            self.assertEquals(
                removal_models.ImmediateRemovalState.STATE_REGISTERED,
                removal_state.state)
            r = removal_models.BatchRemovalState.get_by_user_ids([user_id])
            self.assertEqual([None], r)

            # Add an EventEntity record so we can see it being removed.
            event = models.EventEntity(user_id=user_id, source='test')
            event.put()

        actions.unregister(self, self.COURSE, do_data_removal=True)

        with common_utils.Namespace(self.NAMESPACE):
            # Immediately upon unregistration, we should still have the student
            # record, and removal state should be pending deletion.
            student = models.Student.get_by_user(user)
            self.assertIsNotNone(student)
            removal_state = removal_models.ImmediateRemovalState.get_by_user_id(
                user_id)
            self.assertIsNotNone(removal_state)
            self.assertEquals(
                removal_models.ImmediateRemovalState.STATE_DELETION_PENDING,
                removal_state.state)
            r = removal_models.BatchRemovalState.get_by_user_ids([user_id])
            self.assertEqual([None], r)
            events = list(models.EventEntity.all().run())
            self.assertEquals(1, len(events))

        # We should have gotten a to-do item on the task queue for student
        # removal.
        task_count = self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        self.assertEquals(1, task_count)  # unregistration.

        with common_utils.Namespace(self.NAMESPACE):
            # Having processed the queue item, the student record should now
            # be gone.
            students = list(models.Student.all().run())
            student = models.Student.get_by_user(user)
            self.assertIsNone(student)
            # But the record tracking removal should not yet be gone.
            removal_state = removal_models.ImmediateRemovalState.get_by_user_id(
                user_id)
            self.assertIsNotNone(removal_state)
            self.assertEquals(
                removal_models.ImmediateRemovalState.STATE_DELETION_PENDING,
                removal_state.state)
            # And we should have a to-do item for the cron batch cleanup.
            r = removal_models.BatchRemovalState.get_by_user_ids([user_id])
            self.assertEquals(1, len(r))
            removal_record = r[0]
            self.assertEquals(
                models_data_removal.Registry.get_unindexed_class_names(),
                removal_record.resource_types)
            # Events won't have been cleaned up yet; need cron batch to run.
            events = list(models.EventEntity.all().run())
            self.assertEquals(1, len(events))

        # Call the cron handler to schedule batch removal tasks.  This, in
        # turn, will schedule map/reduce jobs to remove records for that
        # student.
        response = self.get(
            data_removal.DataRemovalCronHandler.URL,
            headers={'X-AppEngine-Cron': 'True'})
        self.assertEquals(200, response.status_int)
        self.assertEquals('OK.', response.body)

        # Run the map/reduce jobs to completion.
        self.execute_all_deferred_tasks()

        # We should now be completely clean; the M/R job that finishes last
        # should also clean up the to-do tracking item.
        with common_utils.Namespace(self.NAMESPACE):
            student = models.Student.get_by_user(user)
            self.assertIsNone(student)
            removal_state = removal_models.ImmediateRemovalState.get_by_user_id(
                user_id)
            self.assertIsNone(removal_state)
            # Events should now be gone.
            events = list(models.EventEntity.all().run())
            self.assertEquals(0, len(events))


    def test_multiple_students(self):
        # Register two students
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, user.email(), course=self.COURSE)

        other_user = actions.login('student002@foo.com')
        actions.register(self, other_user.email(), course=self.COURSE)

        # Get IDs of those students; make an event for each.
        with common_utils.Namespace(self.NAMESPACE):
            student1_id = (
                models.Student.get_by_user(user).user_id)
            student2_id = (
                models.Student.get_by_user(other_user).user_id)
            models.EventEntity(user_id=student1_id, source='test').put()
            models.EventEntity(user_id=student2_id, source='test').put()

        # Unregister one of them.
        actions.login(self.STUDENT_EMAIL)
        actions.unregister(self, self.COURSE, do_data_removal=True)

        # Complete all data removal tasks.
        self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        self.get(
            data_removal.DataRemovalCronHandler.URL,
            headers={'X-AppEngine-Cron': 'True'})
        self.execute_all_deferred_tasks()

        # Unregistered student and his data are gone; still-registered
        # student's data is still present.
        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(models.Student.get_by_user(user))
            self.assertIsNotNone(models.Student.get_by_user(other_user))
            entities = list(models.EventEntity.all().run())
            self.assertEquals(1, len(entities))
            self.assertEquals(student2_id, entities[0].user_id)

    def test_multiple_courses(self):
        COURSE_TWO = 'course_two'
        COURSE_TWO_NS = 'ns_' + COURSE_TWO

        actions.simple_add_course(
            COURSE_TWO, self.ADMIN_EMAIL, 'Data Removal Test Two')

        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, user.email(), course=self.COURSE)
        actions.register(self, user.email(), course=COURSE_TWO)
        actions.unregister(self, self.COURSE, do_data_removal=True)

        self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        self.get(
            data_removal.DataRemovalCronHandler.URL,
            headers={'X-AppEngine-Cron': 'True'})
        self.execute_all_deferred_tasks()

        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(models.Student.get_by_user(user))
        with common_utils.Namespace(COURSE_TWO_NS):
            self.assertIsNotNone(
                models.Student.get_by_user(user))

    def test_student_property_removed(self):
        """Test a sampling of types whose index contains user ID.

        Here, indices start with the user ID, but are suffixed with the name
        of a specific property sub-type.  Verify that these are removed.
        """
        user_id = None
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL, course=self.COURSE)

        # Get IDs of those students; make an event for each.
        with common_utils.Namespace(self.NAMESPACE):
            student = models.Student.get_by_user(user)
            user_id = student.user_id
            p = models.StudentPropertyEntity.create(student, 'foo')
            p.value = 'foo'
            p.put()
            invitation.InvitationStudentProperty.load_or_create(student)
            questionnaire.StudentFormEntity.load_or_create(student, 'a_form')
            cm = competency.BaseCompetencyMeasure.load(user_id, 1)
            cm.save()

        # Assure ourselves that we have exactly one of the items we just added.
        with common_utils.Namespace(self.NAMESPACE):
            l = list(models.StudentPropertyEntity.all().run())
            self.assertEquals(2, len(l))  # 'foo', 'linear-course-completion'
            l = list(invitation.InvitationStudentProperty.all().run())
            self.assertEquals(1, len(l))
            l = list(questionnaire.StudentFormEntity.all().run())
            self.assertEquals(1, len(l))
            l = list(competency.CompetencyMeasureEntity.all().run())
            self.assertEquals(1, len(l))


        actions.unregister(self, self.COURSE, do_data_removal=True)
        self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        self.get(
            data_removal.DataRemovalCronHandler.URL,
            headers={'X-AppEngine-Cron': 'True'})
        self.execute_all_deferred_tasks()

        # Assure ourselves that all added items are now gone.
        with common_utils.Namespace(self.NAMESPACE):
            l = list(models.StudentPropertyEntity.all().run())
            self.assertEquals(0, len(l))
            l = list(invitation.InvitationStudentProperty.all().run())
            self.assertEquals(0, len(l))
            l = list(questionnaire.StudentFormEntity.all().run())
            self.assertEquals(0, len(l))
            l = list(competency.CompetencyMeasureEntity.all().run())
            self.assertEquals(0, len(l))

    def test_remove_by_email(self):
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, user.email(), course=self.COURSE)

        # Get IDs of those students; make an event for each.
        with common_utils.Namespace(self.NAMESPACE):
            sse = unsubscribe.SubscriptionStateEntity(
                key_name=user.email())
            sse.save()

        actions.unregister(self, self.COURSE, do_data_removal=True)
        self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        self.get(
            data_removal.DataRemovalCronHandler.URL,
            headers={'X-AppEngine-Cron': 'True'})
        self.execute_all_deferred_tasks()

        with common_utils.Namespace(self.NAMESPACE):
            l = list(unsubscribe.SubscriptionStateEntity.all().run())
            self.assertEquals(0, len(l))


class UserInteractionTests(actions.TestBase):

    COURSE = 'data_removal_test'
    NAMESPACE = 'ns_' + COURSE
    ADMIN_EMAIL = 'admin@foo.com'
    STUDENT_EMAIL = 'student@foo.com'

    def setUp(self):
        super(UserInteractionTests, self).setUp()
        app_context = actions.simple_add_course(
            self.COURSE, self.ADMIN_EMAIL, 'Data Removal Test')
        self.base = '/' + self.COURSE

    def test_unregister_hides_deletion_option_when_no_deletion_policy(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL)
        with actions.OverriddenEnvironment({
            data_removal.DATA_REMOVAL_SETTINGS_SECTION: {
                data_removal.REMOVAL_POLICY:
                data_removal.IndefiniteRetentionPolicy.get_name()}}):
            response = self.get('student/unenroll')
        self.assertNotIn('Remove all my data from the course', response.body)

    def test_unregister_shows_deletion_option_when_deletion_possible(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL)
        response = self.get('student/unenroll')
        self.assertIn('Remove all my data from the course', response.body)

    def test_unregister_without_deletion_permits_reregistration(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL)
        actions.unregister(self)
        actions.register(self, self.STUDENT_EMAIL)

    def test_reregistration_blocked_during_deletion(self):

        def assert_cannot_register():
            response = self.get('register')
            self.assertIn('You cannot re-register for this course',
                          response.body)
            self.assertNotIn('What is your name?', response.body)

        user_id = None
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, user.email())
        with common_utils.Namespace(self.NAMESPACE):
            # After registration, we should have a student object, and
            # a ImmediateRemovalState instance.
            student = models.Student.get_by_user(user)
            self.assertIsNotNone(student)
            user_id = student.user_id

        actions.unregister(self, do_data_removal=True)
        assert_cannot_register()

        self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        assert_cannot_register()

        self.get(
            data_removal.DataRemovalCronHandler.URL,
            headers={'X-AppEngine-Cron': 'True'})
        assert_cannot_register()

        # Can re-register after all items are cleaned.
        self.execute_all_deferred_tasks()
        with common_utils.Namespace(self.NAMESPACE):
            student = models.Student.get_by_user(user)
            self.assertIsNone(student)
            removal_state = removal_models.ImmediateRemovalState.get_by_user_id(
                user_id)
            self.assertIsNone(removal_state)

        actions.register(self, self.STUDENT_EMAIL)
