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

"""Functional tests for models/courses.py."""

__author__ = [
    'mgainer@google.com (Mike Gainer)',
]

from common import utils as common_utils
from controllers import sites
from models import config
from models import courses
from models import models
from models import vfs
from tests.functional import actions

LOREM_IPSUM = """
Lorem ipsum dolor sit amet, consectetur adipiscing elit. Pellentesque nisl
libero, interdum vel lectus eget, lacinia vestibulum eros. Maecenas posuere
finibus pulvinar. Aenean eu eros mauris. Quisque maximus feugiat
sollicitudin. Vestibulum aliquam vulputate nulla vel volutpat. Donec in
pharetra enim. Nullam et nunc sed nisi ornare suscipit. Curabitur sit amet
enim eu ante tristique tincidunt. Aliquam ac nunc luctus arcu ornare iaculis
vitae nec turpis.

Vivamus ut justo pellentesque, accumsan dui ut, iaculis elit. Nullam congue
nunc odio, sed laoreet nisl iaculis eget. Aenean urna libero, iaculis ac
sapien at, condimentum pellentesque tellus. Phasellus dapibus arcu a dolor
sollicitudin, non tempus erat dapibus. Pellentesque id pellentesque
nunc. Nullam interdum, nulla sit amet convallis scelerisque, ligula tellus
placerat risus, sit amet sodales elit diam sed tellus. Pellentesque
sollicitudin orci imperdiet fermentum semper. Curabitur id ornare elit. Proin
pharetra, diam ac iaculis sed.
""" * 10


class CourseCachingTest(actions.TestBase):

    COURSE_NAME = 'test_course'
    ADMIN_EMAIL = 'admin@foo.com'
    NAMESPACE = 'ns_%s' % COURSE_NAME

    def setUp(self):
        super(CourseCachingTest, self).setUp()
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Test Course')
        self.course = courses.Course(handler=None, app_context=self.app_context)
        actions.login(self.ADMIN_EMAIL)
        config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name] = True

    def tearDown(self):
        del config.Registry.test_overrides[models.CAN_USE_MEMCACHE.name]
        super(CourseCachingTest, self).tearDown()

    def _add_large_unit(self, num_lessons):
        unit = self.course.add_unit()
        for unused in range(num_lessons):
            lesson = self.course.add_lesson(unit)
            lesson.objectives = LOREM_IPSUM
        self.course.save()
        return unit

    def test_large_course_is_cached_in_memcache(self):
        num_lessons = models.MEMCACHE_MAX / len(LOREM_IPSUM)
        unit = self._add_large_unit(num_lessons)

        memcache_keys = courses.CachedCourse13._make_keys()

        # Verify memcache has no contents upon initial save.
        memcache_values = models.MemcacheManager.get_multi(
            memcache_keys, self.NAMESPACE)
        self.assertEquals({}, memcache_values)

        # Load course.  It won't be in memcache, so Course will fetch it
        # from VFS and save it in memcache.
        course = courses.Course(handler=None, app_context=self.app_context)

        # Check that things have gotten into memcache.
        memcache_values = models.MemcacheManager.get_multi(
            memcache_keys, self.NAMESPACE)
        self.assertEquals(
            memcache_keys[0:2],
            sorted(memcache_values.keys()),
            'Only two keys should be present.')
        self.assertEquals(
            models.MEMCACHE_MAX,
            len(memcache_values[memcache_keys[0]]),
            'Shard #0 should be full of data.')
        self.assertGreater(
            len(memcache_values[memcache_keys[1]]), 0,
            'Shard #1 should have data.')

        # Destroy the contents of the course from VFS, so that we are
        # absolutely certain that if the next course load succeeds, it has
        # come from the memcache version, rather than VFS.
        file_key_names = vfs.DatastoreBackedFileSystem._generate_file_key_names(
            '/data/course.json', vfs._MAX_VFS_SHARD_SIZE + 1)
        with common_utils.Namespace(self.NAMESPACE):
            shard_0 = vfs.FileDataEntity.get_by_key_name(file_key_names[0])
            shard_0.delete()
            shard_1 = vfs.FileDataEntity.get_by_key_name(file_key_names[1])
            shard_1.delete()

        # Re-load course to force load from memcache.
        course = courses.Course(handler=None, app_context=self.app_context)

        # Verify contents.
        lessons = course.get_lessons(unit.unit_id)
        self.assertEquals(num_lessons, len(lessons))
        for lesson in lessons:
            self.assertEquals(lesson.objectives, LOREM_IPSUM)

        # Delete items from memcache, and verify that loading fails.  This
        # re-verifies that the loaded data was, in fact, coming from memcache.
        courses.CachedCourse13.delete(self.app_context)
        with self.assertRaises(AttributeError):
            course = courses.Course(handler=None, app_context=self.app_context)

    def test_recovery_from_missing_initial_shard(self):
        self._test_recovery_from_missing_shard(0)

    def test_recovery_from_missing_trailing_shard(self):
        self._test_recovery_from_missing_shard(1)

    def _test_recovery_from_missing_shard(self, shard_index):
        num_lessons = models.MEMCACHE_MAX / len(LOREM_IPSUM)
        unit = self._add_large_unit(num_lessons)
        memcache_keys = courses.CachedCourse13._make_keys()

        # Load course.  It won't be in memcache, so Course will fetch it
        # from VFS and save it in memcache.
        course = courses.Course(handler=None, app_context=self.app_context)

        models.MemcacheManager.delete(memcache_keys[shard_index])

        # Re-load course to force load from memcache.  This should fail back
        # to VFS, and still load successfully.
        course = courses.Course(handler=None, app_context=self.app_context)

        # Verify contents.
        lessons = course.get_lessons(unit.unit_id)
        self.assertEquals(num_lessons, len(lessons))
        for lesson in lessons:
            self.assertEquals(lesson.objectives, LOREM_IPSUM)

    def test_course_that_is_too_large_to_cache_is_not_cached(self):
        num_lessons = courses.CachedCourse13._max_size() / len(LOREM_IPSUM)
        # Fudge factor to get size of course as saved to under the VFS limit
        # but over the memcache limit.
        num_lessons -= 19
        unit = self._add_large_unit(num_lessons)
        memcache_keys = courses.CachedCourse13._make_keys()

        # Load the course, which would normally populate memcache with the
        # loaded content, but will not have, because the course is too large.
        # Verify that.
        course = courses.Course(handler=None, app_context=self.app_context)
        memcache_values = models.MemcacheManager.get_multi(
            memcache_keys, self.NAMESPACE)
        self.assertEquals(
            {}, memcache_values,
            'Memcache for too-large course should be cleared.')

    def test_small_course_occupies_only_one_shard(self):
        self._add_large_unit(num_lessons=1)
        memcache_keys = courses.CachedCourse13._make_keys()

        # Load course to get shard put into memcache.
        course = courses.Course(handler=None, app_context=self.app_context)
        memcache_values = models.MemcacheManager.get_multi(
            memcache_keys, self.NAMESPACE)
        self.assertEquals(
            memcache_keys[0:1],
            memcache_values.keys(),
            'Only shard zero should be present in memcache.')


class PermissionsTest(actions.TestBase):

    def setUp(self):
        super(PermissionsTest, self).setUp()
        self.app_context = sites.get_all_courses()[0]
        self.email = 'test@example.com'
        actions.login(self.email)

    def get_env(self, now_available=None, whitelist=None):
        now_available = now_available if now_available is not None else False
        whitelist = whitelist if whitelist is not None else ''
        return {
            'course': {
                'now_available': now_available,
                'whitelist': whitelist,
            }
        }

    def test_can_enroll_false_when_whitelist_empty_and_course_unavailable(self):
        with actions.OverriddenEnvironment(self.get_env()):
            self.assertFalse(
                courses.Course.get(self.app_context).can_enroll_current_user())

    def test_can_enroll_false_when_not_in_whitelist_course_unavailable(self):
        with actions.OverriddenEnvironment(self.get_env(
                whitelist='other@example.com')):
            self.assertFalse(
                courses.Course.get(self.app_context).can_enroll_current_user())

    def test_can_enroll_true_when_whitelist_empty_and_course_available(self):
        with actions.OverriddenEnvironment(self.get_env(now_available=True)):
            self.assertTrue(
                courses.Course.get(self.app_context).can_enroll_current_user())

    def test_can_enroll_true_when_in_whitelist_and_course_available(self):
        complex_whitelist = (
            ' foo@example.com, %s \n bar@example.com' % self.email)

        with actions.OverriddenEnvironment(self.get_env(
                now_available=True, whitelist=complex_whitelist)):
            self.assertTrue(
                courses.Course.get(self.app_context).can_enroll_current_user())
