# Copyright 2016 Google Inc. All Rights Reserved.
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

"""Functional tests for the Admin module."""

__author__ = 'Todd larsen (tlarsen@google.com)'

import datetime
import logging
import random

import appengine_config
from google.appengine.ext import db

from common import utc
from common import utils
from controllers import sites
from models import models
from models import transforms
from models.data_sources import paginated_table
from modules.admin import enrollments
from tests.functional import actions


class EnrollmentsTests(actions.TestBase):
    """Functional tests for enrollments counters."""

    def test_total_inc_get_set(self):
        ns_name = "ns_single"
        key_name = "%s:total" % ns_name
        key = db.Key.from_path(
            enrollments.TotalEnrollmentDAO.ENTITY.kind(), key_name,
            namespace=appengine_config.DEFAULT_NAMESPACE_NAME)

        # Use namespace that is *not* appengine_config.DEFAULT_NAMESPACE_NAME.
        with utils.Namespace("test_total_inc_get_set"):
            self.assertEquals(
                enrollments.TotalEnrollmentDAO.get(ns_name), 0)
            load_dto = enrollments.TotalEnrollmentDAO.load_or_default(ns_name)
            new_dto = enrollments.TotalEnrollmentDAO.new_dto(ns_name)

            # DAO.get(), DAO.load_or_default(), and DAO.new_dto() do *not*
            # save a zero-value counter in the Datastore for missing counters.
            self.assertEquals(
                enrollments.TotalEnrollmentDAO.ENTITY.get(key), None)

            # DTO.get() does not save a zero-value 'count' in the DTO.
            self.assertEquals(load_dto.get(), 0)
            self.assertTrue(load_dto.is_empty)
            self.assertTrue(load_dto.is_missing)
            self.assertFalse(load_dto.is_pending)
            self.assertFalse(load_dto.is_stalled)
            self.assertEquals(new_dto.get(), 0)
            self.assertTrue(new_dto.is_empty)
            self.assertTrue(new_dto.is_missing)
            self.assertFalse(new_dto.is_pending)
            self.assertFalse(new_dto.is_stalled)

            # Increment the missing total enrollment count for ns_single
            # (which should also initially create the DTO and store it,
            # JSON-encoded, in the Datastore).
            expected_count = 1  # Expecting non-existant counter (0) + 1.
            inc_dto = enrollments.TotalEnrollmentDAO.inc(ns_name)
            self.assertEquals(inc_dto.get(), expected_count)
            self.assertEquals(
                enrollments.TotalEnrollmentDAO.get(ns_name), inc_dto.get())

            # Confirm that a JSON-encoded DTO containing the incremented total
            # enrollment count was stored in the AppEngine default namespace
            # (not the test_total_inc_get_set "course" namespace).
            entity = enrollments.TotalEnrollmentDAO.ENTITY.get(key)
            db_dto = enrollments.TotalEnrollmentDAO.new_dto("", entity=entity)
            self.assertEquals(db_dto.get(), inc_dto.get())

            # Set "ns_single:total" to a value of 5.
            expected_count = 5  # Forces to fixed value, ignoring old value.
            set_dto = enrollments.TotalEnrollmentDAO.set(ns_name, 5)
            self.assertEquals(set_dto.get(), expected_count)
            self.assertEquals(
                enrollments.TotalEnrollmentDAO.get(ns_name), set_dto.get())

            # Increment the existing total enrollment count for ns_single
            # by an arbitrary offset (not the default offset of 1). Expecting
            # what was just set() plus this offset.
            expected_count = set_dto.get() + 10
            ofs_dto = enrollments.TotalEnrollmentDAO.inc(ns_name, offset=10)
            self.assertEquals(ofs_dto.get(), expected_count)
            self.assertEquals(
                enrollments.TotalEnrollmentDAO.get(ns_name), ofs_dto.get())

    def test_total_delete(self):
        ns_name = "ns_delete"
        key_name = "%s:total" % ns_name
        key = db.Key.from_path(
            enrollments.TotalEnrollmentDAO.ENTITY.kind(), key_name,
            namespace=appengine_config.DEFAULT_NAMESPACE_NAME)

        # Use namespace that is *not* appengine_config.DEFAULT_NAMESPACE_NAME.
        with utils.Namespace("test_total_delete"):
            # Set "ns_delete:total" to a value of 5.
            expected_count = 5  # Forces to fixed value, ignoring old value.
            set_dto = enrollments.TotalEnrollmentDAO.set(ns_name, 5)
            self.assertFalse(set_dto.is_empty)
            self.assertFalse(set_dto.is_missing)
            self.assertFalse(set_dto.is_pending)
            self.assertFalse(set_dto.is_stalled)
            self.assertEquals(set_dto.get(), expected_count)
            self.assertEquals(
                enrollments.TotalEnrollmentDAO.get(ns_name), set_dto.get())

            # Confirm that a JSON-encoded DTO containing the set total
            # enrollment count was stored in the AppEngine default namespace
            # (not the test_total_delete "course" namespace).
            entity = enrollments.TotalEnrollmentDAO.ENTITY.get(key)
            db_dto = enrollments.TotalEnrollmentDAO.new_dto("", entity=entity)
            self.assertEquals(db_dto.get(), set_dto.get())

            # Delete the existing total enrollment count for ns_delete.
            enrollments.TotalEnrollmentDAO.delete(ns_name)

            # Confirm that DAO.delete() removed the entity from the Datastore.
            self.assertEquals(
                enrollments.TotalEnrollmentDAO.ENTITY.get(key), None)
            load_dto = enrollments.TotalEnrollmentDAO.load_or_default(ns_name)
            self.assertEquals(load_dto.get(), 0)
            self.assertTrue(load_dto.is_empty)
            self.assertTrue(load_dto.is_missing)
            self.assertFalse(load_dto.is_pending)
            self.assertFalse(load_dto.is_stalled)
            self.assertEquals(
                enrollments.TotalEnrollmentDAO.get(ns_name), 0)

    def test_binned_inc_get_set(self):
        now_dt = datetime.datetime.utcnow()
        now = utc.datetime_to_timestamp(now_dt)
        ns_name = "ns_binned"
        key_name = "%s:adds" % ns_name
        key = db.Key.from_path(
            enrollments.EnrollmentsAddedDAO.ENTITY.kind(), key_name,
            namespace=appengine_config.DEFAULT_NAMESPACE_NAME)

        # Use namespace that is *not* appengine_config.DEFAULT_NAMESPACE_NAME.
        with utils.Namespace("test_binned_inc_get_set"):
            self.assertEquals(
                enrollments.EnrollmentsAddedDAO.get(ns_name, now_dt), 0)
            load_dto = enrollments.EnrollmentsAddedDAO.load_or_default(ns_name)
            new_dto = enrollments.EnrollmentsAddedDAO.new_dto(ns_name)

            # DAO.get(), DAO.load_or_default(), and DAO.new_dto() do *not* save
            # a zero-value binned counter in the Datastore for missing counters.
            self.assertEquals(
                enrollments.EnrollmentsAddedDAO.ENTITY.get(key), None)

            # DTO.get() does not create zero-value bins for missing bins.
            self.assertEquals(new_dto.get(now), 0)
            self.assertTrue(new_dto.is_empty)
            self.assertTrue(new_dto.is_missing)
            self.assertFalse(new_dto.is_pending)
            self.assertFalse(new_dto.is_stalled)
            self.assertEquals(len(new_dto.binned), 0)
            self.assertEquals(load_dto.get(now), 0)
            self.assertTrue(load_dto.is_empty)
            self.assertTrue(load_dto.is_missing)
            self.assertFalse(load_dto.is_pending)
            self.assertFalse(load_dto.is_stalled)
            self.assertEquals(len(load_dto.binned), 0)

            # Increment a missing ns_single:adds enrollment count for the
            # "now" bin (which should also initially create the DTO and store
            # it, JSON-encoded, in the Datastore).
            expected_count = 1  # Expecting non-existant counter (0) + 1.
            inc_dto = enrollments.EnrollmentsAddedDAO.inc(ns_name, now_dt)
            self.assertEquals(len(inc_dto.binned), 1)
            self.assertEquals(inc_dto.get(now), expected_count)
            self.assertEquals(
                enrollments.EnrollmentsAddedDAO.get(ns_name, now_dt),
                inc_dto.get(now))

            # DTO.get() and DAO.get() do not create zero-value bins for missing
            # bins in existing counters. (0 seconds since epoch is most
            # certainly not in the same daily bin as the "now" time.)
            zero_dt = datetime.datetime.utcfromtimestamp(0)
            self.assertEquals(
                enrollments.EnrollmentsAddedDAO.get(ns_name, zero_dt), 0)
            self.assertEquals(inc_dto.get(0), 0)
            self.assertEquals(len(inc_dto.binned), 1)

            # Confirm that a JSON-encoded DTO containing the incremented
            # enrollment counter bins was stored in the AppEngine default
            # namespace (not the test_binned_inc_get_set "course" namespace).
            entity = enrollments.EnrollmentsAddedDAO.ENTITY.get(key)
            db_dto = enrollments.EnrollmentsAddedDAO.new_dto("", entity=entity)
            self.assertEquals(db_dto.get(now), inc_dto.get(now))
            self.assertEquals(len(db_dto.binned), len(inc_dto.binned))

            # Force "ns_single:adds" to a value of 5.
            expected_count = 5  # Forces to fixed value, ignoring old value.
            set_dto = enrollments.EnrollmentsAddedDAO.set(ns_name, now_dt, 5)
            self.assertEquals(len(set_dto.binned), 1)
            self.assertEquals(set_dto.get(now), expected_count)
            self.assertEquals(
                enrollments.EnrollmentsAddedDAO.get(ns_name, now_dt),
                set_dto.get(now))

            # Increment the existing enrollment counter bin for ns_single
            # by an arbitrary offset (not the default offset of 1).
            # Expecting what was just set() plus this offset.
            expected_count = set_dto.get(now) + 10
            ofs_dto = enrollments.EnrollmentsAddedDAO.inc(
                ns_name, now_dt, offset=10)
            self.assertEquals(ofs_dto.get(now), expected_count)
            self.assertEquals(
                enrollments.EnrollmentsAddedDAO.get(ns_name, now_dt),
                ofs_dto.get(now))

            # Increment the "start-of-day" time computed from "now" and show
            # that it is the same bin as the "now" bin (and that no new bins
            # were created).
            now_start = utc.day_start(now)
            now_start_dt = now_dt.replace(hour=0, minute=0, second=0)
            # Expecting just-incremented value + 1.
            expected_count = ofs_dto.get(now) + 1
            start_dto = enrollments.EnrollmentsAddedDAO.inc(
                ns_name, now_start_dt)
            self.assertEquals(len(start_dto.binned), 1)
            self.assertEquals(start_dto.get(now), expected_count)
            self.assertEquals(
                enrollments.EnrollmentsAddedDAO.get(ns_name, now_dt),
                start_dto.get(now))

            # Increment the "end-of-day" time computed from "now" and show
            # that it is in the same bin as the "now" bin"
            now_end = utc.day_end(now)
            now_end_dt = now_dt.replace(hour=23, minute=59, second=59)
            # Expecting just-incremented value + 1.
            expected_count = start_dto.get(now) + 1
            end_dto = enrollments.EnrollmentsAddedDAO.inc(
                ns_name, now_end_dt)
            self.assertEquals(len(end_dto.binned), 1)
            self.assertEquals(end_dto.get(now), expected_count)
            self.assertEquals(
                enrollments.EnrollmentsAddedDAO.get(ns_name, now_dt),
                end_dto.get(now))

    def test_load_many(self):
        NUM_MANY = 100
        ns_names = ["ns_many_%03d" % i for i in xrange(NUM_MANY)]
        course_totals = dict([(ns_name, random.randrange(1, 1000))
                              for ns_name in ns_names])

        # Use namespace that is *not* appengine_config.DEFAULT_NAMESPACE_NAME.
        with utils.Namespace("test_total_load_many"):
            for ns_name, count in course_totals.iteritems():
                enrollments.TotalEnrollmentDAO.set(ns_name, count)

            # load_many() should not fail in the presence of bad course
            # namespace names. Instead, the returned results list should have
            # None values in the corresponding locations.
            bad_ns_names = ["missing_course", "also_missing"]
            all_names = ns_names + bad_ns_names

            many_dtos = enrollments.TotalEnrollmentDAO.load_many(all_names)
            self.assertEquals(len(many_dtos), len(all_names))

            mapped = enrollments.TotalEnrollmentDAO.load_many_mapped(all_names)
            self.assertEquals(len(mapped), len(all_names))

            for ns_name in all_names:
                popped = many_dtos.pop(0)

                if ns_name in bad_ns_names:
                    ns_total = 0
                    self.assertTrue(mapped[ns_name].is_empty)
                    self.assertTrue(mapped[ns_name].is_missing)
                    self.assertFalse(mapped[ns_name].is_pending)
                    self.assertFalse(mapped[ns_name].is_stalled)
                    self.assertTrue(popped.is_empty)
                    self.assertTrue(popped.is_missing)
                    self.assertFalse(popped.is_pending)
                    self.assertFalse(popped.is_stalled)
                else:
                    ns_total = course_totals[ns_name]

                key_name = enrollments.TotalEnrollmentDAO.key_name(ns_name)
                self.assertEquals(popped.id, key_name)
                self.assertEquals(
                    enrollments.TotalEnrollmentDAO.namespace_name(popped.id),
                    ns_name)
                self.assertEquals(popped.get(), ns_total)

                self.assertTrue(ns_name in mapped)
                self.assertEquals(mapped[ns_name].id, key_name)
                self.assertEquals(mapped[ns_name].get(), ns_total)

    def test_load_all(self):
        # 500 is larger than the default common.utils.iter_all() batch_size.
        all_totals = dict([("ns_all_%03d" % i, random.randrange(1, 1000))
                           for i in xrange(500)])

        # Use namespace that is *not* appengine_config.DEFAULT_NAMESPACE_NAME.
        with utils.Namespace("test_total_load_all"):
            for ns, count in all_totals.iteritems():
                enrollments.TotalEnrollmentDAO.set(ns, count)

            for total in enrollments.TotalEnrollmentDAO.load_all():
                ns = enrollments.TotalEnrollmentDAO.namespace_name(total.id)
                self.assertEquals(
                    enrollments.TotalEnrollmentDAO.key_name(ns), total.id)
                self.assertEquals(total.get(), all_totals[ns])
                del all_totals[ns]

            # All totals should have been checked, and checked exactly once.
            self.assertEquals(len(all_totals), 0)


class LogsExaminer(actions.TestBase):

    CHARS_IN_ISO_8601_DATETIME = '[0-9T:.Z-]+'
    CHARS_IN_TIME_DELTA = '[0-9:]+'
    CHARS_IN_TOTAL = '[0-9]+'

    ## Log messages emitted by StartComputeCounts.cron_action().

    CANCELING_PATTERN_FMT = (
        '.*CANCELING periodic "{}" enrollments total refresh found'
        ' unexpectedly still running.')

    def expect_canceling_in_logs(self, logs, dto):
        self.assertRegexpMatches(logs,
            self.CANCELING_PATTERN_FMT.format(dto.id))

    def expect_no_canceling_in_logs(self, logs, dto):
        self.assertNotRegexpMatches(logs,
            self.CANCELING_PATTERN_FMT.format(dto.id))

    INTERRUPTING_PATTERN_FMT = (
        '.*INTERRUPTING missing "{{}}" enrollments total initialization'
            ' started on {}.'.format(CHARS_IN_ISO_8601_DATETIME))

    def expect_interrupting_in_logs(self, logs, dto):
        self.assertRegexpMatches(logs,
            self.INTERRUPTING_PATTERN_FMT.format(dto.id))

    def expect_no_interrupting_in_logs(self, logs, dto):
        self.assertNotRegexpMatches(logs,
            self.INTERRUPTING_PATTERN_FMT.format(dto.id))

    REFRESHING_PATTERN_FMT = (
        '.*REFRESHING existing "{{}}" enrollments total, {{}}'
        ' as of {}.'.format(CHARS_IN_ISO_8601_DATETIME))

    def expect_refreshing_in_logs(self, logs, dto):
        self.assertRegexpMatches(logs,
            self.REFRESHING_PATTERN_FMT.format(dto.id, dto.get()))

    def expect_no_refreshing_in_logs(self, logs, dto):
        self.assertNotRegexpMatches(logs,
            self.REFRESHING_PATTERN_FMT.format(dto.id, self.CHARS_IN_TOTAL))

    COMPLETING_PATTERN_FMT = (
        '.*COMPLETING "{{}}" enrollments total initialization'
        ' started on {} stalled for {}.'.format(
            CHARS_IN_ISO_8601_DATETIME, CHARS_IN_TIME_DELTA))

    def expect_completing_in_logs(self, logs, dto):
        self.assertRegexpMatches(logs,
            self.COMPLETING_PATTERN_FMT.format(dto.id))

    def expect_no_completing_in_logs(self, logs, dto):
        self.assertNotRegexpMatches(logs,
            self.COMPLETING_PATTERN_FMT.format(dto.id))

    ## Log messages emitted by init_missing_total().

    SKIPPING_PATTERN_FMT = (
        '.*SKIPPING existing "{{}}" enrollments total recomputation,'
        ' {{}} as of {}.'.format(CHARS_IN_ISO_8601_DATETIME))

    def expect_skipping_in_logs(self, logs, dto):
        self.assertRegexpMatches(logs,
            self.SKIPPING_PATTERN_FMT.format(dto.id, dto.get()))

    def expect_no_skipping_in_logs(self, logs, dto):
        self.assertNotRegexpMatches(logs,
            self.SKIPPING_PATTERN_FMT.format(dto.id, self.CHARS_IN_TOTAL))

    PENDING_PATTERN_FMT = (
        '.*PENDING "{{}}" enrollments total initialization in progress for'
        ' {}, since {}.'.format(
            CHARS_IN_TIME_DELTA, CHARS_IN_ISO_8601_DATETIME))

    def expect_pending_in_logs(self, logs, dto):
        self.assertRegexpMatches(logs,
            self.PENDING_PATTERN_FMT.format(dto.id))

    def expect_no_pending_in_logs(self, logs, dto):
        self.assertNotRegexpMatches(logs,
            self.PENDING_PATTERN_FMT.format(dto.id))

    STALLED_PATTERN_FMT = (
        '.*STALLED "{{}}" enrollments total initialization for'
        ' {}, since {}.'.format(
            CHARS_IN_TIME_DELTA, CHARS_IN_ISO_8601_DATETIME))

    def expect_stalled_in_logs(self, logs, dto):
        self.assertRegexpMatches(logs,
            self.STALLED_PATTERN_FMT.format(dto.id))

    def expect_no_stalled_in_logs(self, logs, dto):
        self.assertNotRegexpMatches(logs,
            self.STALLED_PATTERN_FMT.format(dto.id))

    SCHEDULING_PATTERN_FMT = (
        '.*SCHEDULING "{{}}" enrollments total update at {}.'.format(
            CHARS_IN_ISO_8601_DATETIME))

    def expect_scheduling_in_logs(self, logs, dto):
        self.assertRegexpMatches(logs,
            self.SCHEDULING_PATTERN_FMT.format(dto.id))

    def expect_no_scheduling_in_logs(self, logs, dto):
        self.assertNotRegexpMatches(logs,
            self.SCHEDULING_PATTERN_FMT.format(dto.id))

    def check_no_exceptional_states_in_logs(self, logs, dto, ignore=None):
        if ignore is None:
            ignore = frozenset()

        if 'CANCELING' not in ignore:
            self.expect_no_canceling_in_logs(logs, dto)
        if 'INTERRUPTING' not in ignore:
            self.expect_no_interrupting_in_logs(logs, dto)
        if 'COMPLETING' not in ignore:
            self.expect_no_completing_in_logs(logs, dto)
        if 'SKIPPING' not in ignore:
            self.expect_no_skipping_in_logs(logs, dto)
        if 'PENDING' not in ignore:
            self.expect_no_pending_in_logs(logs, dto)
        if 'STALLED' not in ignore:
            self.expect_no_stalled_in_logs(logs, dto)

    def get_new_logs(self, previous_logs):
        """Get log lines since previous all_logs, plus new all_logs lines."""
        num_previous_log_lines = len(previous_logs)
        all_logs = self.get_log()
        return all_logs[num_previous_log_lines:], all_logs


class EventHandlersTests(LogsExaminer):

    ADMIN_EMAIL = 'admin@example.com'
    STUDENT_EMAIL = 'student@example.com'
    STUDENT_NAME = 'Test Student'
    LOG_LEVEL = logging.DEBUG

    def tearDown(self):
        sites.reset_courses()

    def test_counters(self):
        # pylint: disable=too-many-statements
        COURSE = 'test_counters_event_handlers'
        NAMESPACE = 'ns_' + COURSE
        all_logs = []  # No log lines yet obtained via get_log().

        # This test relies on the fact that simple_add_course() does *not*
        # execute the CoursesItemRESTHandler.NEW_COURSE_ADDED_HOOKS, to
        # simulate "legacy" courses existing prior to enrollments counters.
        self.app_ctxt = actions.simple_add_course(
            COURSE, self.ADMIN_EMAIL, 'Enrollments Events')

        with utils.Namespace(NAMESPACE):
            start = utc.day_start(utc.now_as_timestamp())
            start_dt = datetime.datetime.utcfromtimestamp(start)
            user = actions.login(self.STUDENT_EMAIL)

            # _new_course_counts() was not called by simple_add_course().
            # As a result, all counters will *not exist at all*, instead of
            # simply starting out with zero values (as is the case when
            # courses are created via the actual web UI.
            self.assertEquals(enrollments.TotalEnrollmentDAO.get(
                NAMESPACE), 0)
            total_dto = enrollments.TotalEnrollmentDAO.load_or_default(
                NAMESPACE)
            self.assertTrue(total_dto.is_empty)
            self.assertTrue(total_dto.is_missing)
            self.assertFalse(total_dto.is_pending)
            self.assertFalse(total_dto.is_stalled)

            self.assertEquals(enrollments.EnrollmentsAddedDAO.get(
                NAMESPACE, start_dt), 0)
            added_dto = enrollments.EnrollmentsAddedDAO.load_or_default(
                NAMESPACE)
            self.assertTrue(added_dto.is_empty)
            self.assertTrue(added_dto.is_missing)
            self.assertFalse(added_dto.is_pending)
            self.assertFalse(added_dto.is_stalled)

            self.assertEquals(enrollments.EnrollmentsDroppedDAO.get(
                NAMESPACE, start_dt), 0)
            dropped_dto = enrollments.EnrollmentsDroppedDAO.load_or_default(
                NAMESPACE)
            self.assertTrue(dropped_dto.is_empty)
            self.assertTrue(dropped_dto.is_missing)
            self.assertFalse(dropped_dto.is_pending)
            self.assertFalse(dropped_dto.is_stalled)

            actions.login(self.STUDENT_EMAIL)
            actions.register(self, self.STUDENT_NAME, course=COURSE)
            self.execute_all_deferred_tasks(
                models.StudentLifecycleObserver.QUEUE_NAME)

            # The enrollments._count_add() callback is triggered by the above
            # StudentLifecycleObserver.EVENT_ADD action. That callback will
            # call init_missing_total() because the counter was "missing"
            # (did not exist *at all*).
            pending_add_dto = enrollments.TotalEnrollmentDAO.load_or_default(
                NAMESPACE)
            # Still no count value, since the MapReduce has not run (and will
            # not, because execute_all_deferred_tasks() is being called by
            # this test *only* for the StudentLifecycleObserver.QUEUE_NAME).
            self.assertTrue(pending_add_dto.is_empty)
            self.assertTrue(pending_add_dto.is_pending)
            # Now "pending" instead of "missing" because last_modified has
            # been set by init_missing_total() via mark_pending().
            self.assertFalse(pending_add_dto.is_missing)
            self.assertFalse(pending_add_dto.is_stalled)

            # init_missing_total() will have logged that it is "SCHEDULING"
            # a ComputeCounts MapReduce (that will never be run by this test).
            logs, all_logs = self.get_new_logs(all_logs)
            self.check_no_exceptional_states_in_logs(logs, pending_add_dto)
            self.expect_scheduling_in_logs(logs, pending_add_dto)

            # Confirm executing deferred tasks did not cross day boundary.
            registered = utc.now_as_timestamp()
            self.assertEquals(utc.day_start(registered), start)

            # When the counters are completely uninitialized (e.g. "legacy"
            # courses in an installation that is upgrading to enrollments
            # counters), student lifecycle events will *not* increment or
            # decrement missing 'total' counters. However, the information is
            # not lost, since ComputeCounts MapReduceJobs will recover actual
            # enrollment totals when they are scheduled (e.g. via the register
            # and unregister student lifecycle events, or via the
            # site_admin_enrollments cron jobs).

            total_dto = enrollments.TotalEnrollmentDAO.load_or_default(
                NAMESPACE)
            self.assertTrue(total_dto.is_empty)  # No inc for a missing total.
            self.assertFalse(total_dto.is_missing)
            self.assertTrue(total_dto.is_pending)
            self.assertFalse(total_dto.is_stalled)
            self.assertEquals(enrollments.TotalEnrollmentDAO.get(
                NAMESPACE), 0)

            added_dto = enrollments.EnrollmentsAddedDAO.load_or_default(
                NAMESPACE)
            # Always count today's 'adds', since ComputeCounts will not.
            self.assertFalse(added_dto.is_empty)
            self.assertFalse(added_dto.is_missing)
            self.assertFalse(added_dto.is_pending)
            self.assertFalse(added_dto.is_stalled)
            self.assertEquals(1, added_dto.get(start))
            self.assertEquals(enrollments.EnrollmentsAddedDAO.get(
                NAMESPACE, start_dt), 1)

            dropped_dto = enrollments.EnrollmentsDroppedDAO.load_or_default(
                NAMESPACE)
            self.assertTrue(dropped_dto.is_empty)  # No 'drops' to count yet.
            self.assertTrue(dropped_dto.is_missing)
            self.assertFalse(dropped_dto.is_pending)
            self.assertFalse(dropped_dto.is_stalled)
            self.assertEquals(enrollments.EnrollmentsDroppedDAO.get(
                NAMESPACE, start_dt), 0)

            actions.unregister(self, course=COURSE)
            self.execute_all_deferred_tasks(
                models.StudentLifecycleObserver.QUEUE_NAME)

            # The enrollments._count_drop() callback is triggered by the above
            # StudentLifecycleObserver.EVENT_UNENROLL_COMMANDED action. That
            # callback will *not* call init_missing_total() because this time,
            # while the counter is "empty" (contains no count), it *does* have
            # a last modified time, so is "pending" and no longer "missing".

            # Confirm executing deferred tasks did not cross day boundary.
            unregistered = utc.now_as_timestamp()
            self.assertEquals(utc.day_start(unregistered), start)

            total_dto = enrollments.TotalEnrollmentDAO.load_or_default(
                NAMESPACE)
            self.assertTrue(total_dto.is_empty)  # Still does not exist.
            self.assertFalse(total_dto.is_missing)
            self.assertTrue(total_dto.is_pending)  # Still pending.
            self.assertFalse(total_dto.is_stalled)
            self.assertEquals(enrollments.TotalEnrollmentDAO.get(
                NAMESPACE), 0)

            added_dto = enrollments.EnrollmentsAddedDAO.load_or_default(
                NAMESPACE)
            self.assertFalse(added_dto.is_empty)  # Unchanged by a drop event.
            self.assertFalse(added_dto.is_missing)
            self.assertFalse(added_dto.is_pending)
            self.assertFalse(added_dto.is_stalled)
            self.assertEquals(1, added_dto.get(start))
            self.assertEquals(enrollments.EnrollmentsAddedDAO.get(
                NAMESPACE, start_dt), 1)

            dropped_dto = enrollments.EnrollmentsDroppedDAO.load_or_default(
                NAMESPACE)
            # Always count today's 'drops', since ComputeCounts will not.
            self.assertFalse(dropped_dto.is_empty)
            self.assertFalse(dropped_dto.is_missing)
            self.assertFalse(dropped_dto.is_pending)
            self.assertFalse(dropped_dto.is_stalled)
            self.assertEquals(1, dropped_dto.get(start))
            self.assertEquals(enrollments.EnrollmentsDroppedDAO.get(
                NAMESPACE, start_dt), 1)

            # Run the MapReduceJob to recover the missing 'total' and 'adds'.
            enrollments.init_missing_total(total_dto, self.app_ctxt)
            self.execute_all_deferred_tasks()

            total_dto = enrollments.TotalEnrollmentDAO.load_or_default(
                NAMESPACE)
            self.assertFalse(total_dto.is_empty)  # Finally exists.
            self.assertFalse(total_dto.is_missing)
            self.assertFalse(total_dto.is_pending)
            self.assertFalse(total_dto.is_stalled)
            self.assertEquals(0, total_dto.get())  # Add and then drop is 0.
            self.assertEquals(enrollments.TotalEnrollmentDAO.get(
                NAMESPACE), 0)

            models.StudentProfileDAO.update(
                user.user_id(), self.STUDENT_EMAIL, is_enrolled=True)
            self.execute_all_deferred_tasks(
                models.StudentLifecycleObserver.QUEUE_NAME)

            # Confirm executing deferred tasks did not cross day boundary.
            updated = utc.now_as_timestamp()
            self.assertEquals(utc.day_start(updated), start)

            total_dto = enrollments.TotalEnrollmentDAO.load_or_default(
                NAMESPACE)
            self.assertFalse(total_dto.is_empty)
            self.assertFalse(total_dto.is_missing)
            self.assertFalse(total_dto.is_pending)
            self.assertFalse(total_dto.is_stalled)
            self.assertEquals(1, total_dto.get())
            self.assertEquals(enrollments.TotalEnrollmentDAO.get(
                NAMESPACE), 1)

            added_dto = enrollments.EnrollmentsAddedDAO.load_or_default(
                NAMESPACE)
            self.assertFalse(added_dto.is_empty)
            self.assertFalse(added_dto.is_missing)
            self.assertFalse(added_dto.is_pending)
            self.assertFalse(added_dto.is_stalled)
            self.assertEquals(2, added_dto.get(start))
            self.assertEquals(enrollments.EnrollmentsAddedDAO.get(
                NAMESPACE, start_dt), 2)

            dropped_dto = enrollments.EnrollmentsDroppedDAO.load_or_default(
                NAMESPACE)
            self.assertFalse(dropped_dto.is_empty)
            self.assertFalse(dropped_dto.is_missing)
            self.assertFalse(dropped_dto.is_pending)
            self.assertFalse(dropped_dto.is_stalled)
            self.assertEquals(1, dropped_dto.get(start))
            self.assertEquals(enrollments.EnrollmentsDroppedDAO.get(
                NAMESPACE, start_dt), 1)


class MapReduceTests(LogsExaminer):

    ADMIN1_EMAIL = 'admin1@example.com'
    STUDENT2_EMAIL = 'student2@example.com'
    STUDENT3_EMAIL = 'student3@example.com'
    STUDENT4_EMAIL = 'student4@example.com'
    LOG_LEVEL = logging.DEBUG

    @staticmethod
    def _count_add(unused_id, unused_utc_date_time):
        pass

    @staticmethod
    def _count_drop(unused_id, unused_utc_date_time):
        pass

    @staticmethod
    def _new_course_counts(unused_app_context, unused_errors):
        pass

    def setUp(self):
        super(MapReduceTests, self).setUp()

        # Replace enrollments counters callbacks with ones that do *not*
        # increment or decrement the 'total' enrollment counters.
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_ADD][
                enrollments.MODULE_NAME] = MapReduceTests._count_add
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_REENROLL][
                enrollments.MODULE_NAME] = MapReduceTests._count_add
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_UNENROLL][
                enrollments.MODULE_NAME] = MapReduceTests._count_drop
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_UNENROLL_COMMANDED][
                enrollments.MODULE_NAME] = MapReduceTests._count_drop

    def tearDown(self):
        sites.reset_courses()

        # Restore enrollments counters callbacks to originals.
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_ADD][
                enrollments.MODULE_NAME] = enrollments._count_add
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_REENROLL][
                enrollments.MODULE_NAME] = enrollments._count_add
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_UNENROLL][
                enrollments.MODULE_NAME] = enrollments._count_drop
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_UNENROLL_COMMANDED][
                enrollments.MODULE_NAME] = enrollments._count_drop

    def test_total_enrollment_map_reduce_job(self):
        # pylint: disable=too-many-statements
        COURSE = 'test_total_enrollment_map_reduce_job'
        NAMESPACE = 'ns_' + COURSE
        all_logs = []  # No log lines yet obtained via get_log().

        # This test relies on the fact that simple_add_course() does *not*
        # execute the CoursesItemRESTHandler.NEW_COURSE_ADDED_HOOKS, to
        # simulate "legacy" courses existing prior to enrollments counters.
        app_context = actions.simple_add_course(
            COURSE, self.ADMIN1_EMAIL, 'Total Enrollment MapReduce Job')

        with utils.Namespace(NAMESPACE):
            start = utc.day_start(utc.now_as_timestamp())
            start_dt = datetime.datetime.utcfromtimestamp(start)

            # Both 'total' and 'adds' counters should start out at zero.
            self.assertEquals(enrollments.TotalEnrollmentDAO.get(
                NAMESPACE), 0)
            empty_total = enrollments.TotalEnrollmentDAO.load_or_default(
                NAMESPACE)
            self.assertTrue(empty_total.is_empty)
            self.assertTrue(empty_total.is_missing)
            self.assertFalse(empty_total.is_pending)
            self.assertFalse(empty_total.is_stalled)

            self.assertEquals(enrollments.EnrollmentsAddedDAO.get(
                NAMESPACE, start_dt), 0)
            empty_adds = enrollments.EnrollmentsAddedDAO.load_or_default(
                NAMESPACE)
            self.assertTrue(empty_adds.is_empty)
            self.assertTrue(empty_adds.is_missing)
            self.assertFalse(empty_adds.is_pending)
            self.assertFalse(empty_adds.is_stalled)

            admin1 = actions.login(self.ADMIN1_EMAIL)
            actions.register(self, self.ADMIN1_EMAIL, course=COURSE)

            # Manipulate the enrolled_on time of the first student (the
            # course creator admin) to be last month.
            student1 = models.Student.get_by_user(admin1)
            last_month_dt = start_dt - datetime.timedelta(days=30)
            student1.enrolled_on = last_month_dt
            student1.put()

            user2 = actions.login(self.STUDENT2_EMAIL)
            actions.register(self, self.STUDENT2_EMAIL, course=COURSE)

            # Manipulate the enrolled_on time of the second student to be
            # last week.
            student2 = models.Student.get_by_user(user2)
            last_week_dt = start_dt - datetime.timedelta(days=7)
            student2.enrolled_on = last_week_dt
            student2.put()

            user3 = actions.login(self.STUDENT3_EMAIL)
            actions.register(self, self.STUDENT3_EMAIL, course=COURSE)

            # Manipulate the enrolled_on time of the third student to be
            # yesterday.
            student3 = models.Student.get_by_user(user3)
            yesterday_dt = start_dt - datetime.timedelta(days=1)
            student3.enrolled_on = yesterday_dt
            student3.put()

            # Unregister and re-enroll today, which does not affect the original
            # (manipulated above) enrolled_on value.
            actions.unregister(self, course=COURSE)
            models.StudentProfileDAO.update(
                user3.user_id(), self.STUDENT3_EMAIL, is_enrolled=True)

            # Leave the fourth student enrollment as happening today.
            student4 = actions.login(self.STUDENT4_EMAIL)
            actions.register(self, self.STUDENT4_EMAIL, course=COURSE)

        self.execute_all_deferred_tasks(
            models.StudentLifecycleObserver.QUEUE_NAME)

        # Both 'total' and 'adds' counters should still be zero, because
        # student lifecycle event handlers for modules.admin.enrollments have
        # been disabled by MapReduceTests.setUp().
        self.assertEquals(enrollments.TotalEnrollmentDAO.get(
            NAMESPACE), 0)
        after_queue_total = enrollments.TotalEnrollmentDAO.load_or_default(
            NAMESPACE)
        self.assertTrue(after_queue_total.is_empty)
        self.assertTrue(after_queue_total.is_missing)
        self.assertFalse(after_queue_total.is_pending)
        self.assertFalse(after_queue_total.is_stalled)

        self.assertEquals(enrollments.EnrollmentsAddedDAO.get(
            NAMESPACE, start_dt), 0)
        after_queue_adds = enrollments.EnrollmentsAddedDAO.load_or_default(
            NAMESPACE)
        self.assertTrue(after_queue_adds.is_empty)
        self.assertTrue(after_queue_adds.is_missing)
        self.assertFalse(after_queue_adds.is_pending)
        self.assertFalse(after_queue_adds.is_stalled)

        enrollments.init_missing_total(after_queue_total, app_context)
        logs, all_logs = self.get_new_logs(all_logs)
        self.check_no_exceptional_states_in_logs(logs, after_queue_total)
        self.expect_scheduling_in_logs(logs, after_queue_total)

        self.execute_all_deferred_tasks()
        logs, all_logs = self.get_new_logs(all_logs)
        self.check_no_exceptional_states_in_logs(logs, after_queue_total)
        self.assertEquals(enrollments.TotalEnrollmentDAO.get(
            NAMESPACE), 4)  # ADMIN1, STUDENT2, STUDENT3, STUDENT4
        after_mr_dto = enrollments.TotalEnrollmentDAO.load_or_default(
            NAMESPACE)
        self.assertFalse(after_mr_dto.is_empty)
        self.assertFalse(after_mr_dto.is_missing)
        self.assertFalse(after_mr_dto.is_pending)
        self.assertFalse(after_mr_dto.is_stalled)

        # The 'adds' DTO will not be empty, because some of the enrollments
        # occurred on days other than "today".
        after_mr_adds = enrollments.EnrollmentsAddedDAO.load_or_default(
            NAMESPACE)
        self.assertFalse(after_mr_adds.is_empty)
        self.assertFalse(after_mr_adds.is_missing)
        self.assertFalse(after_mr_adds.is_pending)
        self.assertFalse(after_mr_adds.is_stalled)

        self.assertEquals(enrollments.EnrollmentsAddedDAO.get(
            NAMESPACE, last_month_dt), 1)  # ADMIN1

        self.assertEquals(enrollments.EnrollmentsAddedDAO.get(
            NAMESPACE, last_week_dt), 1)  # STUDENT2

        # The third student registered yesterday, but then unregistered and
        # re-enrolled today. Those subsequent activities do not affect the
        # original enrolled_on value.
        self.assertEquals(enrollments.EnrollmentsAddedDAO.get(
            NAMESPACE, yesterday_dt), 1)  # STUDENT3

        # Even after the ComputeCounts MapReduce runs, the "today" 'adds'
        # 'adds' counter for the course will still be empty, because any
        # registration events inside the `with` block that above happened
        # today are not updated, to avoid race conditions with real time
        # updates that would be occurring in production (where the student
        # lifecycle handlers have not been disabled by test code as in
        # this test).
        self.assertEquals(enrollments.EnrollmentsAddedDAO.get(
            NAMESPACE, start_dt), 0)  # STUDENT4

        # Log in as an admin and cause the /cron/site_admin_enrollments/total
        # MapReduce to be enqueued, but do this *twice*.  This should produce
        # both a "REFRESHING" log message for the existing enrollments total
        # counter *and* a "CANCELING" log message when one of the calls to
        # StartComputeCounts.cron_action() cancels the job just started by the
        # previous call.
        actions.login(self.ADMIN1_EMAIL, is_admin=True)
        response = self.get(enrollments.StartComputeCounts.URL)
        self.assertEquals(200, response.status_int)
        response = self.get(enrollments.StartComputeCounts.URL)
        self.assertEquals(200, response.status_int)
        self.execute_all_deferred_tasks()

        self.assertEquals(enrollments.TotalEnrollmentDAO.get(
            NAMESPACE), 4)  # Refreshed value still includes all enrollees.
        after_refresh_total = enrollments.TotalEnrollmentDAO.load_or_default(
            NAMESPACE)
        self.assertFalse(after_refresh_total.is_empty)
        self.assertFalse(after_refresh_total.is_missing)
        self.assertFalse(after_refresh_total.is_pending)
        self.assertFalse(after_refresh_total.is_stalled)

        # No other "exceptional" states are expected other than 'CANCELING'.
        logs, all_logs = self.get_new_logs(all_logs)
        self.check_no_exceptional_states_in_logs(logs, after_refresh_total,
            ignore=frozenset(['CANCELING']))
        self.expect_canceling_in_logs(logs, after_refresh_total)
        self.expect_refreshing_in_logs(logs, after_refresh_total)

        # Inject some "exceptional" states and confirm that the corresponding
        # condition is detected and logged.

        # Put the DTO for the NAMESPACE course into the "pending" state, having
        # a last_modified time but no count.
        marked_dto = enrollments.TotalEnrollmentDAO.mark_pending(
            namespace_name=NAMESPACE)
        # A DTO in the "pending" state contains no count value.
        self.assertTrue(marked_dto.is_empty)
        # DTO *does* have a last modified time, even though it is empty.
        self.assertTrue(marked_dto.is_pending)
        # DTO has not be in the "pending" state for longer than the maximum
        # pending time (MAX_PENDING_SEC), so is not yet "stalled".
        self.assertFalse(marked_dto.is_stalled)
        # DTO is not "missing" because, even though it is "empty", it is in
        # the "pending" state (waiting for a MapReduce started by
        # init_missing_total() MapReduce to complete.
        self.assertFalse(marked_dto.is_missing)
        self.assertEquals(enrollments.TotalEnrollmentDAO.get(
            NAMESPACE), 0)  # mark_pending() sets last_modified but not count.

        # Now cause the /cron/site_admin_enrollments/total cron job to run,
        # but schedule *two* of them, so that one will be "COMPLETING" because
        # the DTO is marked "pending", and the other will be "INTERRUPTING"
        # because the DTO is "pending" *and* another ComputeCounts MapReduce
        # job appears to already be running.
        response = self.get(enrollments.StartComputeCounts.URL)
        self.assertEquals(200, response.status_int)
        response = self.get(enrollments.StartComputeCounts.URL)
        self.assertEquals(200, response.status_int)
        self.execute_all_deferred_tasks()

        # Correct total should have been computed and stored despite one
        # StartComputeCounts.cron_action() canceling the other.
        self.assertEquals(enrollments.TotalEnrollmentDAO.get(
            NAMESPACE), 4)  # Computed value still includes all enrollees.
        exceptional_dto = enrollments.TotalEnrollmentDAO.load_or_default(
            NAMESPACE)
        self.assertFalse(exceptional_dto.is_empty)
        self.assertFalse(exceptional_dto.is_missing)
        self.assertFalse(exceptional_dto.is_pending)
        self.assertFalse(exceptional_dto.is_stalled)

        # No other "exceptional" states are expected other than the two below.
        logs, all_logs = self.get_new_logs(all_logs)
        self.check_no_exceptional_states_in_logs(logs, marked_dto,
            ignore=frozenset(['COMPLETING', 'INTERRUPTING']))
        self.expect_completing_in_logs(logs, marked_dto)
        self.expect_interrupting_in_logs(logs, marked_dto)

        # No existing count value (since DTO is "empty"), so no "REFRESHING"
        # of an existing enrollments total.
        self.expect_no_refreshing_in_logs(logs, marked_dto)
        self.expect_no_scheduling_in_logs(logs, marked_dto)

    def test_start_init_missing_counts(self):
        COURSE = 'test_start_init_missing_counts'
        NAMESPACE = 'ns_' + COURSE
        all_logs = []  # No log lines yet obtained via get_log().

        # This test relies on the fact that simple_add_course() does *not*
        # execute the CoursesItemRESTHandler.NEW_COURSE_ADDED_HOOKS, to
        # simulate "legacy" courses existing prior to enrollments counters.
        app_context = actions.simple_add_course(
            COURSE, self.ADMIN1_EMAIL, 'Init Missing Counts')

        admin1 = actions.login(self.ADMIN1_EMAIL, is_admin=True)

        # Courses list page should show em dashes for enrollment total counts.
        response = self.get('/admin?action=courses')
        dom = self.parse_html_string_to_soup(response.body)
        enrollment_div = dom.select('#enrolled_')[0]
        self.assertEquals(enrollments.NONE_ENROLLED,
                          enrollment_div.text.strip())

        # The resulting DTO should be empty (have no count) and should *not*
        # be "pending" (last_modified value should be zero).
        before = enrollments.TotalEnrollmentDAO.load_or_default(NAMESPACE)
        self.assertTrue(before.is_empty)
        self.assertTrue(before.is_missing)
        self.assertNotIn('count', before.dict)
        self.assertFalse(before.is_pending)
        self.assertFalse(before.is_stalled)
        self.assertFalse(before.last_modified)

        # Confirm that the StartInitMissingCounts cron job will find the
        # courses that are missing an enrollment total entity in the Datastore
        # and trigger the ComputeCounts MapReduce for them, but only once.
        response = self.get(enrollments.StartInitMissingCounts.URL)
        self.assertEquals(200, response.status_int)
        self.execute_all_deferred_tasks()

        logs, all_logs = self.get_new_logs(all_logs)
        self.check_no_exceptional_states_in_logs(logs, before)
        self.expect_scheduling_in_logs(logs, before)
        # init_missing_total() does not use StartComputeCounts, but instead
        # invokes ComputeCounts.submit() directly.
        self.expect_no_refreshing_in_logs(logs, before)

        # Load the courses page again, now getting 0 for number of students.
        response = self.get('/admin?action=courses')
        dom = self.parse_html_string_to_soup(response.body)
        enrollment_div = dom.select('#enrolled_')[0]
        self.assertEquals('0', enrollment_div.text.strip())

        # The resulting DTO should be non-empty (have a count of zero) and
        # thus should also not be "pending".
        after = enrollments.TotalEnrollmentDAO.load_or_default(NAMESPACE)
        self.assertFalse(after.is_empty)
        self.assertIn('count', after.dict)
        self.assertEquals(0, after.get())
        self.assertFalse(after.is_pending)
        self.assertTrue(after.last_modified)

        # Run the cron job a second time, which should find nothing needing
        # to be done.
        response = self.get(enrollments.StartInitMissingCounts.URL)
        self.assertEquals(200, response.status_int)
        self.execute_all_deferred_tasks()

        logs, all_logs = self.get_new_logs(all_logs)
        self.check_no_exceptional_states_in_logs(logs, after,
            ignore=frozenset(['SKIPPING']))
        self.expect_skipping_in_logs(logs, after)
        self.expect_no_scheduling_in_logs(logs, after)
        self.expect_no_refreshing_in_logs(logs, after)

        # Inject some "exceptional" states and confirm that the corresponding
        # condition is detected and logged.

        # Put the DTO for the NAMESPACE course into the "pending" state, having
        # a last_modified time but no count.
        marked_dto = enrollments.TotalEnrollmentDAO.mark_pending(
            namespace_name=NAMESPACE)
        self.assertTrue(marked_dto.is_empty)
        self.assertTrue(marked_dto.is_pending)
        self.assertFalse(marked_dto.is_stalled)
        self.assertFalse(marked_dto.is_missing)
        self.assertEquals(enrollments.TotalEnrollmentDAO.get(
            NAMESPACE), 0)  # mark_pending() sets last_modified but not count.

        # Run the cron job again, which should find a "pending" but not
        # "stalled" count, 'SKIPPING' it to allow a previously deferred
        # MapReduce to initialize it.
        response = self.get(enrollments.StartInitMissingCounts.URL)
        self.assertEquals(200, response.status_int)
        self.execute_all_deferred_tasks()

        # No other "exceptional" states are expected other than 'SKIPPING'.
        logs, all_logs = self.get_new_logs(all_logs)
        self.check_no_exceptional_states_in_logs(logs, marked_dto,
            ignore=frozenset(['SKIPPING']))
        self.expect_skipping_in_logs(logs, marked_dto)

        # StartInitMissingCounts.cron_action() deferred enrollments totals
        # that are not "stalled" to be initialized by previously scheduled
        # MapReduce jobs.
        self.expect_no_scheduling_in_logs(logs, marked_dto)
        self.expect_no_refreshing_in_logs(logs, marked_dto)

        # Now call init_missing_total() directly, which logs a 'PENDING'
        # messages instead. (StartInitMissingCounts.cron_action() did not even
        # invoke init_missing_total() in the above get().)
        enrollments.init_missing_total(marked_dto, app_context)

        # No other "exceptional" states are expected other than 'PENDING'.
        logs, all_logs = self.get_new_logs(all_logs)
        self.check_no_exceptional_states_in_logs(logs, marked_dto,
            ignore=frozenset(['PENDING']))
        self.expect_pending_in_logs(logs, marked_dto)

        # init_missing_total() leaves "pending" but not "stalled" deferred
        # enrollments totals to be initialized by previously scheduled
        # MapReduce jobs.
        self.expect_no_scheduling_in_logs(logs, marked_dto)
        self.expect_no_refreshing_in_logs(logs, marked_dto)

        # Force the "pending" DTO into the "stalled" state by setting its
        # last modified value into the past by more than MAX_PENDING_SEC.
        past = 2 * enrollments.EnrollmentsDTO.MAX_PENDING_SEC
        marked_dto._force_last_modified(marked_dto.last_modified - past)
        enrollments.TotalEnrollmentDAO._save(marked_dto)
        past_dto = enrollments.TotalEnrollmentDAO.load_or_default(NAMESPACE)
        self.assertTrue(past_dto.is_empty)
        self.assertTrue(past_dto.is_pending)
        self.assertTrue(past_dto.is_stalled)
        self.assertFalse(past_dto.is_missing)

        # Run the cron job again, which should find a "stalled" count.
        # StartInitMissingCounts.cron_action() calls init_missing_total() for
        # a "stalled" count. init_missing_total() should then log that the
        # count is 'STALLED'.
        response = self.get(enrollments.StartInitMissingCounts.URL)
        self.assertEquals(200, response.status_int)
        self.execute_all_deferred_tasks()

        # No other "exceptional" states are expected other than 'STALLED'.
        logs, all_logs = self.get_new_logs(all_logs)
        self.check_no_exceptional_states_in_logs(logs, marked_dto,
            ignore=frozenset(['STALLED']))
        self.expect_stalled_in_logs(logs, marked_dto)

        # init_missing_total() should be 'SCHEDULING' a new MapReduce, via a
        # direct invocation of ComputeCounts.submit(), to replace the
        # stalled total.
        self.expect_scheduling_in_logs(logs, marked_dto)
        self.expect_no_refreshing_in_logs(logs, marked_dto)


class GraphTests(actions.TestBase):

    COURSE = 'test_course'
    NAMESPACE = 'ns_%s' % COURSE
    ADMIN_EMAIL = 'admin@example.com'

    def setUp(self):
        super(GraphTests, self).setUp()
        self.app_context = actions.simple_add_course(
            self.COURSE, self.ADMIN_EMAIL, 'Test Course')
        self.base = '/%s' % self.COURSE
        actions.login(self.ADMIN_EMAIL)

    def tearDown(self):
        sites.reset_courses()
        super(GraphTests, self).tearDown()

    def _get_items(self):
        data_source_token = paginated_table._DbTableContext._build_secret(
            {'data_source_token': 'xyzzy'})
        response = self.post('rest/data/enrollments/items',
                             {'page_number': 0,
                              'chunk_size': 0,
                              'data_source_token': data_source_token})
        self.assertEquals(response.status_int, 200)
        result = transforms.loads(response.body)
        return result.get('data')

    def _get_dashboard_page(self):
        response = self.get('dashboard?action=analytics_enrollments')
        self.assertEquals(response.status_int, 200)
        return response

    def test_no_enrollments(self):
        self.assertEquals([], self._get_items())

        body = self._get_dashboard_page().body
        self.assertIn('No student enrollment data.', body)

    def test_one_add(self):
        now = utc.now_as_timestamp()
        now_dt = utc.timestamp_to_datetime(now)
        enrollments.EnrollmentsAddedDAO.inc(self.NAMESPACE, now_dt)
        expected = [{
            'timestamp_millis': utc.day_start(now) * 1000,
            'add': 1,
            'drop': 0,
        }]
        self.assertEquals(expected, self._get_items())

        body = self._get_dashboard_page().body
        self.assertNotIn('No student enrollment data.', body)

    def test_only_drops(self):
        now_dt = utc.timestamp_to_datetime(utc.now_as_timestamp())
        enrollments.EnrollmentsDroppedDAO.inc(self.NAMESPACE, now_dt)

        body = self._get_dashboard_page().body
        self.assertIn('No student enrollment data.', body)

    def test_one_add_and_one_drop(self):
        now = utc.now_as_timestamp()
        now_dt = utc.timestamp_to_datetime(now)
        enrollments.EnrollmentsAddedDAO.inc(self.NAMESPACE, now_dt)
        enrollments.EnrollmentsDroppedDAO.inc(self.NAMESPACE, now_dt)
        expected = [{
            'timestamp_millis': utc.day_start(now) * 1000,
            'add': 1,
            'drop': 1,
        }]
        self.assertEquals(expected, self._get_items())

        body = self._get_dashboard_page().body
        self.assertNotIn('No student enrollment data.', body)

    def test_many(self):
        now = utc.now_as_timestamp()
        num_items = 1000

        # Add a lot of enrollments, drops.
        for x in xrange(num_items):
            when = utc.timestamp_to_datetime(
                now - random.randrange(365 * 24 * 60 * 60))
            if x % 10:
                enrollments.EnrollmentsAddedDAO.inc(self.NAMESPACE, when)
            else:
                enrollments.EnrollmentsDroppedDAO.inc(self.NAMESPACE, when)
        items = self._get_items()

        # Expect some overlap, but still many distinct items.  Here, we're
        # looking to ensure that we get some duplicate items binned together.
        self.assertGreater(len(items), num_items / 10)
        self.assertLess(len(items), num_items)
        self.assertEquals(num_items, sum([i['add'] + i['drop'] for i in items]))
