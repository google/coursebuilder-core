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

import appengine_config

from common import utils as common_utils
from common import users
from models import data_removal as models_data_removal
from models import models
from models import student_work
from modules.analytics import student_aggregate
from modules.data_removal import data_removal
from modules.data_removal import removal_models
from modules.gitkit import gitkit
from modules.invitation import invitation
from modules.questionnaire import questionnaire
from modules.notifications import notifications
from modules.oeditor import oeditor
from modules.review import domain
from modules.review import peer
from modules.skill_map import competency
from modules.unsubscribe import unsubscribe
from tests.functional import actions

from google.appengine.ext import db

class DataRemovalTestBase(actions.TestBase):

    def setUp(self):
        super(DataRemovalTestBase, self).setUp()

        # If the optional wipeout module is present, it will enforce some
        # requirements that we're not prepared to construct in core
        # Course Builder.  Unilaterally remove its registrations.
        event_callbacks = models.StudentLifecycleObserver.EVENT_CALLBACKS
        for event_type in event_callbacks:
            if 'wipeout' in event_callbacks[event_type]:
                del event_callbacks[event_type]['wipeout']
        enqueue_callbacks = models.StudentLifecycleObserver.EVENT_CALLBACKS
        for event_type in enqueue_callbacks:
            if 'wipeout' in enqueue_callbacks[event_type]:
                del enqueue_callbacks[event_type]['wipeout']

    def _unregister_and_request_data_removal(self, course):
        response = self.get('/%s/student/home' % course)
        response = self.click(response, 'Unenroll')
        self.assertIn('to unenroll from', response.body)
        form = response.form
        form['data_removal'].checked = True
        form.action = self.canonicalize(form.action, response)
        response = form.submit()
        form = response.form
        form.action = self.canonicalize(form.action, response)
        response = form.submit('data_removal')
        self.assertIn('You have been unenrolled', response.body)

    def _complete_removal(self):
        # Remove indexed items, add to-do items for map/reduce.
        task_count = self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        # Add map/reduce jobs on default queue
        response = self.get(
            data_removal.DataRemovalCronHandler.URL,
            headers={'X-AppEngine-Cron': 'True'})
        # Run map/reduce jobs
        self.execute_all_deferred_tasks()
        # Final call to cron to do cleanup once map/reduce work items done.
        response = self.get(
            data_removal.DataRemovalCronHandler.URL,
            headers={'X-AppEngine-Cron': 'True'})


class DataRemovalTests(DataRemovalTestBase):

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
            self.execute_all_deferred_tasks(
                models.StudentLifecycleObserver.QUEUE_NAME)

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

            actions.unregister(self, course=self.COURSE)

            # Expect to see unregister event on queue -- register event handled
            # as part of actions.register.
            task_count = self.execute_all_deferred_tasks(
                models.StudentLifecycleObserver.QUEUE_NAME)
            self.assertEquals(1, task_count)

            # Running deletion cycle should have no effect.  Verify that.
            self._complete_removal()

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
        self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        user_id = None

        with common_utils.Namespace(self.NAMESPACE):
            # After registration, we should have a student object, and
            # a ImmediateRemovalState instance, and no to-do deletion work.
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

        self._unregister_and_request_data_removal(self.COURSE)

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

        # We should now be nearly clean; in the normal course of events, only
        # the ImmediateRemovalState should still be present.  However, due to
        # race conditions, an analysis map/reduce job may have finished in the
        # meantime, and written a per-student record.  Add such a record.
        with common_utils.Namespace(self.NAMESPACE):
            student = models.Student.get_by_user(user)
            self.assertIsNone(student)
            removal_state = removal_models.ImmediateRemovalState.get_by_user_id(
                user_id)
            self.assertIsNotNone(removal_state)
            # Events should now be gone.
            events = list(models.EventEntity.all().run())
            self.assertEquals(0, len(events))

            # Cron batch cleanup record should be present, but now empty.
            r = removal_models.BatchRemovalState.get_by_user_ids([user_id])
            self.assertEquals(1, len(r))
            removal_record = r[0]
            self.assertEquals([], removal_record.resource_types)

            # Simulate map/reduce finishing asychronously & adding a per-student
            # item.  Verify that the record is present so we know the test
            # below that checks for it being gone is correct.
            student_aggregate.StudentAggregateEntity(key_name=user_id).put()
            a = student_aggregate.StudentAggregateEntity.get_by_key_name(
                user_id)
            self.assertIsNotNone(a)

        # Call the cron handler one more time.  Because the batch work item
        # is empty, this should do one more round of cleanup on items indexed
        # by user id.
        response = self.get(
            data_removal.DataRemovalCronHandler.URL,
            headers={'X-AppEngine-Cron': 'True'})
        self.assertEquals(200, response.status_int)
        self.assertEquals('OK.', response.body)

        # We should now have zero data about the user.
        with common_utils.Namespace(self.NAMESPACE):
            student = models.Student.get_by_user(user)
            self.assertIsNone(student)
            removal_state = removal_models.ImmediateRemovalState.get_by_user_id(
                user_id)
            self.assertIsNone(removal_state)
            # Events should now be gone.
            events = list(models.EventEntity.all().run())
            self.assertEquals(0, len(events))
            # Cron batch cleanup record should be gone.
            r = removal_models.BatchRemovalState.get_by_user_ids([user_id])
            self.assertEqual([None], r)
            # Map/reduce results should be gone.
            a = student_aggregate.StudentAggregateEntity.get_by_key_name(
                user_id)
            self.assertIsNone(a)

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
        self._unregister_and_request_data_removal(self.COURSE)
        self._complete_removal()

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

        # Slight cheat: Register gitkit data remover manually, rather than
        # enabling the entire module, which disrupts normal functional test
        # user login handling
        gitkit.EmailMapping.register_for_data_removal()

        actions.simple_add_course(
            COURSE_TWO, self.ADMIN_EMAIL, 'Data Removal Test Two')
        user = actions.login(self.STUDENT_EMAIL)

        actions.register(self, user.email(), course=self.COURSE)
        actions.register(self, user.email(), course=COURSE_TWO)
        # Slight cheat: Rather than enabling gitkit module, just call
        # the method that will insert the EmailMapping row.
        gitkit.EmailUpdatePolicy.apply(user)

        # Global profile object(s) should now exist.
        profile = models.StudentProfileDAO.get_profile_by_user_id(
            user.user_id())
        self.assertIsNotNone(profile)
        email_policy = gitkit.EmailMapping.get_by_user_id(user.user_id())
        self.assertIsNotNone(email_policy)

        # Unregister from 'data_removal_test' course.
        self._unregister_and_request_data_removal(self.COURSE)
        self._complete_removal()

        # Student object should be gone from data_removal_test course, but
        # not from course_two.
        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(models.Student.get_by_user(user))
        with common_utils.Namespace(COURSE_TWO_NS):
            self.assertIsNotNone(models.Student.get_by_user(user))

        # Global profile object(s) should still exist.
        profile = models.StudentProfileDAO.get_profile_by_user_id(
            user.user_id())
        self.assertIsNotNone(profile)
        email_policy = gitkit.EmailMapping.get_by_user_id(user.user_id())
        self.assertIsNotNone(email_policy)

        # Unregister from other course.
        self._unregister_and_request_data_removal(COURSE_TWO)
        self._complete_removal()

        # Both Student objects should now be gone.
        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNone(models.Student.get_by_user(user))
        with common_utils.Namespace(COURSE_TWO_NS):
            self.assertIsNone(models.Student.get_by_user(user))

        # Global profile object(s) should also be gone.
        profile = models.StudentProfileDAO.get_profile_by_user_id(
            user.user_id())
        self.assertIsNone(profile)
        email_policy = gitkit.EmailMapping.get_by_user_id(user.user_id())
        self.assertIsNone(email_policy)

    def test_records_indexed_by_user_id_removed(self):
        """Test a sampling of types whose index is or contains the user ID."""
        user_id = None
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL, course=self.COURSE)

        # Get IDs of those students; make an event for each.
        with common_utils.Namespace(self.NAMESPACE):
            student = models.Student.get_by_user(user)
            user_id = student.user_id

            # Indexed by user ID suffixed with a string.
            p = models.StudentPropertyEntity.create(student, 'foo')
            p.value = 'foo'
            p.put()
            invitation.InvitationStudentProperty.load_or_default(student).put()
            questionnaire.StudentFormEntity.load_or_default(
                student, 'a_form').put()

            # User ID plus skill name.
            cm = competency.BaseCompetencyMeasure.load(user_id, 1)
            cm.save()

            # models.student_work.KeyProperty - a foreign key to Student.
            reviewee_key = db.Key.from_path(models.Student.kind(), user_id)
            reviewer_key = db.Key.from_path(models.Student.kind(), 'xyzzy')
            student_work.Review(contents='abcdef', reviewee_key=reviewee_key,
                                reviewer_key=reviewer_key, unit_id='7').put()
            submission_key = student_work.Submission(
                unit_id='7', reviewee_key=reviewee_key).put()
            peer.ReviewSummary(submission_key=submission_key,
                               reviewee_key=reviewee_key, unit_id='7').put()
            peer.ReviewStep(
                submission_key=submission_key, reviewee_key=reviewee_key,
                reviewer_key=reviewer_key, unit_id='7',
                state=domain.REVIEW_STATE_ASSIGNED,
                assigner_kind=domain.ASSIGNER_KIND_AUTO).put()

            key_name = oeditor.EditorPrefsDao.create_key_name(
                user_id, 'dasboard?action=foo', 'frammis')
            editor_prefs = oeditor.EditorPrefsDto(key_name, {'this': 'that'})
            oeditor.EditorPrefsDao.save(editor_prefs)


        # Assure ourselves that we have all of the items we just added.
        with common_utils.Namespace(self.NAMESPACE):
            l = list(models.StudentPropertyEntity.all().run())
            self.assertEquals(2, len(l))  # 'foo', 'linear-course-completion'
            l = list(invitation.InvitationStudentProperty.all().run())
            self.assertEquals(1, len(l))
            l = list(questionnaire.StudentFormEntity.all().run())
            self.assertEquals(1, len(l))
            l = list(competency.CompetencyMeasureEntity.all().run())
            self.assertEquals(1, len(l))
            l = list(student_work.Review.all().run())
            self.assertEquals(1, len(l))
            l = list(student_work.Submission.all().run())
            self.assertEquals(1, len(l))
            l = list(peer.ReviewSummary.all().run())
            self.assertEquals(1, len(l))
            l = list(peer.ReviewStep.all().run())
            self.assertEquals(1, len(l))
            l = list(oeditor.EditorPrefsEntity.all().run())
            self.assertEquals(1, len(l))


        self._unregister_and_request_data_removal(self.COURSE)
        self._complete_removal()

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
            l = list(student_work.Review.all().run())
            self.assertEquals(0, len(l))
            l = list(student_work.Submission.all().run())
            self.assertEquals(0, len(l))
            l = list(peer.ReviewSummary.all().run())
            self.assertEquals(0, len(l))
            l = list(peer.ReviewStep.all().run())
            self.assertEquals(0, len(l))
            l = list(oeditor.EditorPrefsEntity.all().run())
            self.assertEquals(0, len(l))

    def test_remove_by_email(self):
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, user.email(), course=self.COURSE)

        with common_utils.Namespace(self.NAMESPACE):
            sse = unsubscribe.SubscriptionStateEntity(
                key_name=user.email())
            sse.is_subscribed = True
            sse.save()

            notifications.Manager.send_async(
                user.email(), self.ADMIN_EMAIL, 'testemail',
                'Mary had a little lamb.  She fed it beans and buns.',
                'Pets for Mary', '{"audit_trail": "yes"}',
                retention_policy=notifications.RetainAll)
            # Finish deferred tasks so notifications subsystem would have
            # deleted items if it were going to.  It shouldn't based on our
            # use of RetainAll above, but belt-and-suspenders.
            self.execute_all_deferred_tasks()
            l = list(notifications.Notification.all().run())
            self.assertEquals(1, len(l))
            l = list(notifications.Payload.all().run())
            self.assertEquals(1, len(l))

        self._unregister_and_request_data_removal(self.COURSE)
        self._complete_removal()

        with common_utils.Namespace(self.NAMESPACE):
            l = list(unsubscribe.SubscriptionStateEntity.all().run())
            self.assertEquals(0, len(l))
            l = list(notifications.Notification.all().run())
            self.assertEquals(0, len(l))
            l = list(notifications.Payload.all().run())
            self.assertEquals(0, len(l))

    def test_subscription_state_entity_unsubscribed_not_removed(self):
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, user.email(), course=self.COURSE)

        # Get IDs of those students; make an event for each.
        with common_utils.Namespace(self.NAMESPACE):
            sse = unsubscribe.SubscriptionStateEntity(
                key_name=user.email())
            sse.is_subscribed = False
            sse.save()

        self._unregister_and_request_data_removal(self.COURSE)
        self._complete_removal()

        with common_utils.Namespace(self.NAMESPACE):
            l = list(unsubscribe.SubscriptionStateEntity.all().run())
            self.assertEquals(1, len(l))

    def test_unenroll_commanded_with_delete_requested(self):
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL, course=self.COURSE)

        # Verify user is really there.
        with common_utils.Namespace(self.NAMESPACE):
            self.assertIsNotNone(models.Student.get_by_user_id(user.user_id()))

            # Mark user for data deletion upon unenroll
            removal_models.ImmediateRemovalState.set_deletion_pending(
                user.user_id())

            response = self.post(
                models.StudentLifecycleObserver.URL,
                {'user_id': user.user_id(),
                 'event':
                     models.StudentLifecycleObserver.EVENT_UNENROLL_COMMANDED,
                 'timestamp': '2015-05-14T10:02:09.758704Z',
                 'callbacks': appengine_config.CORE_MODULE_NAME},
                headers={'X-AppEngine-QueueName':
                         models.StudentLifecycleObserver.QUEUE_NAME})
            self.assertEquals(response.status_int, 200)
            self.assertEquals('', self.get_log())

            # User should still be there, but now marked unenrolled.
            student = models.Student.get_by_user_id(user.user_id())
            self.assertFalse(student.is_enrolled)

            # Running lifecycle queue should cause data removal to delete user.
            self.execute_all_deferred_tasks(
                models.StudentLifecycleObserver.QUEUE_NAME)

            # User should now be gone.
            self.assertIsNone(models.Student.get_by_user_id(user.user_id()))


class UserInteractionTests(DataRemovalTestBase):

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
        self.assertIn('Delete all associated data', response.body)

    def test_unregister_without_deletion_permits_reregistration(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL)
        actions.unregister(self)
        actions.register(self, self.STUDENT_EMAIL)

    def _unregister_flow(self, response,
                         with_deletion_checked=False,
                         cancel_on_unregister=False,
                         cancel_on_deletion=False):
        unregistration_expected = (not cancel_on_unregister and
                                   not cancel_on_deletion)
        data_deletion_expected = (unregistration_expected and
                                  with_deletion_checked)

        # Caller should have arranged for us to be at the unregister form.
        form = response.form
        if with_deletion_checked:
            form['data_removal'].checked = True
        if cancel_on_unregister:
            response = self.click(response, "No")
            return response

        # Submit unregister form.
        response = form.submit()

        if with_deletion_checked:
            self.assertIn(
                'Once you delete your data, there is no way to recover it.',
                response.body)
            form = response.form
            form.action = self.canonicalize(form.action, response)
            if cancel_on_deletion:
                response = form.submit('cancel_removal').follow()
                self.assertIn(
                    'To leave the course permanently, click on Unenroll',
                    response.body)
            else:
                response = form.submit('data_removal')
                self.assertIn('You have been unenrolled', response.body)

        # Try to visit student's profile - verify can or can't depending
        # on whether we unregistered the student.
        response = self.get('student/home')
        if unregistration_expected:
            self.assertEquals(response.status_int, 302)
            self.assertEquals(response.location,
                              'http://localhost/%s/course' % self.COURSE)
            response = response.follow()
            self.assertEquals(response.status_int, 200)
        else:
            self.assertEquals(response.status_int, 200)  # not 302 to /course

        # Run pipeline which might do deletion to ensure we are really
        # giving the code the opportunity to do the deletion before we
        # check whether the Student is not gone.
        self._complete_removal()
        with common_utils.Namespace(self.NAMESPACE):
            user = users.get_current_user()
            if data_deletion_expected:
                self.assertIsNone(models.Student.get_by_user(user))
            else:
                self.assertIsNotNone(models.Student.get_by_user(user))

    def _deletion_flow_for_unregistered_student(self, response, cancel):
        self.assertIn(
            'Once you delete your data, there is no way to recover it.',
            response.body)
        form = response.form
        form.action = self.canonicalize(form.action, response)

        if cancel:
            response = form.submit('cancel_removal')

            # Verify redirected back to /course page in either case.
            self.assertEquals(response.status_int, 302)
            self.assertEquals(response.location,
                              'http://localhost/%s/student/home' % self.COURSE)
            response = response.follow()
            self.assertEquals(response.status_int, 302)
            self.assertEquals(response.location,
                              'http://localhost/%s/course' % self.COURSE)
            response = response.follow()
            self.assertEquals(response.status_int, 200)
        else:
            response = form.submit('data_removal')

            self.assertEquals(response.status_int, 302)
            self.assertEquals(response.location,
                              'http://localhost/%s/' % self.COURSE)
            response = response.follow()
            self.assertEquals(response.status_int, 200)

        # Run pipeline which might do deletion to ensure we are really
        # giving the code the opportunity to do the deletion before we
        # check whether the Student is not gone.
        self._complete_removal()
        with common_utils.Namespace(self.NAMESPACE):
            user = users.get_current_user()
            if cancel:
                self.assertIsNotNone(models.Student.get_by_user(user))
            else:
                self.assertIsNone(models.Student.get_by_user(user))

    def test_unregister_then_cancel_does_not_unregister_or_delete(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL)
        response = self.get('student/unenroll')
        self._unregister_flow(response, cancel_on_unregister=True)

    def test_unregister_without_deletion_unregisters_but_does_not_delete(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL)
        response = self.get('student/unenroll')
        self._unregister_flow(response)

    def test_unregister_with_deletion_then_cancel_does_not_unregister(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL)
        response = self.get('student/unenroll')
        self._unregister_flow(response, with_deletion_checked=True,
                              cancel_on_deletion=True)

    def test_unregister_with_deletion_does_deletion(self):
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL)
        response = self.get('student/unenroll')
        self._unregister_flow(response, with_deletion_checked=True)

    def test_delete_link_in_footer_not_present_when_not_logged_in(self):
        response = self.get('course')
        self.assertNotIn('Delete My Data', response.body)

    def test_delete_link_in_footer_not_present_when_not_registered(self):
        actions.login(self.STUDENT_EMAIL)
        response = self.get('course')
        self.assertNotIn('Delete My Data', response.body)

    def test_delete_link_when_registered_then_cancel_unregister(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL)
        response = self.get('course')
        response = self.click(response, 'Delete My Data')
        self._unregister_flow(response, cancel_on_unregister=True)

    def test_delete_link_when_registered_then_cancel_deletion(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL)
        response = self.get('course')
        response = self.click(response, 'Delete My Data')
        self._unregister_flow(response, with_deletion_checked=True,
                              cancel_on_deletion=True)

    def test_delete_link_when_registered_then_unregister_without_deletion(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL)
        response = self.get('course')
        response = self.click(response, 'Delete My Data')
        self._unregister_flow(response)

    def test_delete_link_when_registered_then_proceed_and_delete(self):
        actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL)
        response = self.get('course')
        response = self.click(response, 'Delete My Data')
        self._unregister_flow(response, with_deletion_checked=True)

    def test_delete_link_when_unregistered_then_cancel(self):
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL)
        actions.unregister(self)
        response = self.get('course')
        response = self.click(response, 'Delete My Data')
        self._deletion_flow_for_unregistered_student(response, cancel=True)
        response = self.get('course')
        self.assertIn('Delete My Data', response.body)

    def test_delete_link_when_unregistered_then_proceed(self):
        user = actions.login(self.STUDENT_EMAIL)
        actions.register(self, self.STUDENT_EMAIL)
        actions.unregister(self)
        response = self.get('course')
        response = self.click(response, 'Delete My Data')
        self._deletion_flow_for_unregistered_student(response, cancel=False)
        response = self.get('course')
        self.assertNotIn('Delete My Data', response.body)

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

        self._unregister_and_request_data_removal(self.COURSE)

        # On submitting the unregister form, the user's ImmediateRemovalState
        # will have been marked as deltion-in-progress, and so user cannot
        # re-register yet.
        assert_cannot_register()

        # Run the queue to do the cleanup of indexed items, and add the
        # work-to-do items for batched cleanup.
        self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)
        assert_cannot_register()

        # Run the cron job that launches the map/reduce jobs to clean up
        # bulk items.  Still not able to re-register.
        self.get(
            data_removal.DataRemovalCronHandler.URL,
            headers={'X-AppEngine-Cron': 'True'})
        assert_cannot_register()

        # Run the map/reduce jobs.  Bulk items should now be cleaned.
        self.execute_all_deferred_tasks()
        with common_utils.Namespace(self.NAMESPACE):
            student = models.Student.get_by_user(user)
            self.assertIsNone(student)
            removal_state = removal_models.ImmediateRemovalState.get_by_user_id(
                user_id)
            self.assertIsNotNone(removal_state)
        assert_cannot_register()

        # Run the cron job one more time.  When no bulk to-do items remain,
        # we then clean up the ImmediateRemovalState.  Re-registration should
        # now be possible.
        self.get(
            data_removal.DataRemovalCronHandler.URL,
            headers={'X-AppEngine-Cron': 'True'})
        with common_utils.Namespace(self.NAMESPACE):
            student = models.Student.get_by_user(user)
            self.assertIsNone(student)
            removal_state = removal_models.ImmediateRemovalState.get_by_user_id(
                user_id)
            self.assertIsNone(removal_state)

        actions.register(self, self.STUDENT_EMAIL)
