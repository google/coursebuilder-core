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
            self.assertEquals(new_dto.get(), 0)
            self.assertTrue(new_dto.is_empty)

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
            self.assertEquals(len(new_dto.binned), 0)
            self.assertEquals(load_dto.get(now), 0)
            self.assertTrue(load_dto.is_empty)
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
                    self.assertTrue(popped.is_empty)
                else:
                    ns_total = course_totals[ns_name]

                self.assertEquals(popped.namespace_name, ns_name)
                self.assertEquals(popped.get(), ns_total)

                self.assertTrue(ns_name in mapped)
                self.assertEquals(mapped[ns_name].namespace_name, ns_name)
                self.assertEquals(mapped[ns_name].get(), ns_total)


class EventHandlersTests(actions.TestBase):

    COURSE = 'enrollments_events'
    NAMESPACE = 'ns_' + COURSE
    ADMIN_EMAIL = 'admin@example.com'
    STUDENT_EMAIL = 'student@example.com'
    LOG_LEVEL = logging.DEBUG

    def setUp(self):
        super(EventHandlersTests, self).setUp()
        enrollments.register_callbacks()
        actions.simple_add_course(
            self.COURSE, self.ADMIN_EMAIL, 'Enrollments Events')

    def tearDown(self):
        sites.reset_courses()

    def test_counters(self):
        with utils.Namespace(self.NAMESPACE):
            start = utc.day_start(utc.now_as_timestamp())
            start_dt = datetime.datetime.utcfromtimestamp(start)
            user = actions.login(self.STUDENT_EMAIL)

            # All counters should start out at zero.
            self.assertEquals(enrollments.TotalEnrollmentDAO.get(
                self.NAMESPACE), 0)
            total_dto = enrollments.TotalEnrollmentDAO.load_or_default(
                self.NAMESPACE)
            self.assertTrue(total_dto.is_empty)

            self.assertEquals(enrollments.EnrollmentsAddedDAO.get(
                self.NAMESPACE, start_dt), 0)
            added_dto = enrollments.EnrollmentsAddedDAO.load_or_default(
                self.NAMESPACE)
            self.assertTrue(added_dto.is_empty)

            self.assertEquals(enrollments.EnrollmentsDroppedDAO.get(
                self.NAMESPACE, start_dt), 0)
            dropped_dto = enrollments.EnrollmentsDroppedDAO.load_or_default(
                self.NAMESPACE)
            self.assertTrue(dropped_dto.is_empty)

            actions.register(self, self.STUDENT_EMAIL, course=self.COURSE)
            self.execute_all_deferred_tasks(
                models.StudentLifecycleObserver.QUEUE_NAME)

            # Confirm executing deferred tasks did not cross day boundary.
            registered = utc.now_as_timestamp()
            self.assertEquals(utc.day_start(registered), start)
            total_dto = enrollments.TotalEnrollmentDAO.load_or_default(
                self.NAMESPACE)
            self.assertFalse(total_dto.is_empty)
            self.assertEquals(enrollments.TotalEnrollmentDAO.get(
                self.NAMESPACE), 1)

            added_dto = enrollments.EnrollmentsAddedDAO.load_or_default(
                self.NAMESPACE)
            self.assertFalse(added_dto.is_empty)
            self.assertEquals(enrollments.EnrollmentsAddedDAO.get(
                self.NAMESPACE, start_dt), 1)

            dropped_dto = enrollments.EnrollmentsDroppedDAO.load_or_default(
                self.NAMESPACE)
            self.assertTrue(dropped_dto.is_empty) # Not yet incremented.
            self.assertEquals(enrollments.EnrollmentsDroppedDAO.get(
                self.NAMESPACE, start_dt), 0)

            actions.unregister(self, course=self.COURSE)
            self.execute_all_deferred_tasks(
                models.StudentLifecycleObserver.QUEUE_NAME)

            # Confirm executing deferred tasks did not cross day boundary.
            unregistered = utc.now_as_timestamp()
            self.assertEquals(utc.day_start(unregistered), start)

            total_dto = enrollments.TotalEnrollmentDAO.load_or_default(
                self.NAMESPACE)
            self.assertFalse(total_dto.is_empty) # Back to zero, not "empty".
            self.assertEquals(enrollments.TotalEnrollmentDAO.get(
                self.NAMESPACE), 0)

            added_dto = enrollments.EnrollmentsAddedDAO.load_or_default(
                self.NAMESPACE)
            self.assertFalse(added_dto.is_empty)
            self.assertEquals(enrollments.EnrollmentsAddedDAO.get(
                self.NAMESPACE, start_dt), 1)

            dropped_dto = enrollments.EnrollmentsDroppedDAO.load_or_default(
                self.NAMESPACE)
            self.assertFalse(dropped_dto.is_empty) # Finally incremented.
            self.assertEquals(enrollments.EnrollmentsDroppedDAO.get(
                self.NAMESPACE, start_dt), 1)

            models.StudentProfileDAO.update(
                user.user_id(), self.STUDENT_EMAIL, is_enrolled=True)
            self.execute_all_deferred_tasks(
                models.StudentLifecycleObserver.QUEUE_NAME)

            # Confirm executing deferred tasks did not cross day boundary.
            updated = utc.now_as_timestamp()
            self.assertEquals(utc.day_start(updated), start)

            total_dto = enrollments.TotalEnrollmentDAO.load_or_default(
                self.NAMESPACE)
            self.assertFalse(total_dto.is_empty)
            self.assertEquals(enrollments.TotalEnrollmentDAO.get(
                self.NAMESPACE), 1)

            added_dto = enrollments.EnrollmentsAddedDAO.load_or_default(
                self.NAMESPACE)
            self.assertFalse(added_dto.is_empty)
            self.assertEquals(enrollments.EnrollmentsAddedDAO.get(
                self.NAMESPACE, start_dt), 2)

            dropped_dto = enrollments.EnrollmentsDroppedDAO.load_or_default(
                self.NAMESPACE)
            self.assertFalse(dropped_dto.is_empty)
            self.assertEquals(enrollments.EnrollmentsDroppedDAO.get(
                self.NAMESPACE, start_dt), 1)
