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

"""Functional tests for VFS features."""

__author__ = [
    'mgainer@google.com (Mike Gainer)',
]

import os
import random
import StringIO
import tempfile

from common import utils as common_utils
from models import vfs
from models import courses
from tests.functional import actions
from tools.etl import etl

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


class VfsLargeFileSupportTest(actions.TestBase):

    COURSE_NAME = 'test_course'
    ADMIN_EMAIL = 'admin@foo.com'
    NAMESPACE = 'ns_%s' % COURSE_NAME

    def setUp(self):
        super(VfsLargeFileSupportTest, self).setUp()
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Test Course')
        self.course = courses.Course(handler=None, app_context=self.app_context)
        actions.login(self.ADMIN_EMAIL)

    def test_course_larger_than_datastore_max_size_is_sharded(self):
        unit = self.course.add_unit()
        num_lessons = vfs._MAX_VFS_SHARD_SIZE / len(LOREM_IPSUM)
        for unused in range(num_lessons):
            lesson = self.course.add_lesson(unit)
            lesson.objectives = LOREM_IPSUM
        serializer = courses.PersistentCourse13(
            next_id=self.course._model.next_id,
            units=self.course._model.units,
            lessons=self.course._model.lessons)
        serialized_length = len(serializer.serialize())
        self.assertGreater(
            serialized_length, vfs._MAX_VFS_SHARD_SIZE,
            'Verify that serialized course is larger than the max entity size')

        self.course.save()
        # course.save() clears cache, so we don't need to do that here.

        # Verify contents of course.
        course = courses.Course(handler=None, app_context=self.app_context)
        lessons = course.get_lessons(unit.unit_id)
        self.assertEquals(num_lessons, len(lessons))
        for lesson in lessons:
            self.assertEquals(lesson.objectives, LOREM_IPSUM)

        # Verify that sharded items exist with appropriate sizes.
        file_key_names = vfs.DatastoreBackedFileSystem._generate_file_key_names(
            '/data/course.json', serialized_length)
        self.assertEquals(
            2, len(file_key_names),
            'Verify attempting to store a too-large file makes multiple shards')
        with common_utils.Namespace(self.NAMESPACE):
            shard_0 = vfs.FileDataEntity.get_by_key_name(file_key_names[0])
            self.assertEquals(vfs._MAX_VFS_SHARD_SIZE, len(shard_0.data))

            shard_1 = vfs.FileDataEntity.get_by_key_name(file_key_names[1])
            self.assertGreater(len(shard_1.data), 0)


    def test_course_larger_than_datastore_max_can_be_exported_and_loaded(self):
        unit = self.course.add_unit()
        num_lessons = vfs._MAX_VFS_SHARD_SIZE / len(LOREM_IPSUM)
        for unused in range(num_lessons):
            lesson = self.course.add_lesson(unit)
            lesson.objectives = LOREM_IPSUM
        self.course.save()

        other_course_name = 'other_course'
        other_course_context = actions.simple_add_course(
            other_course_name, self.ADMIN_EMAIL, 'Other')

        # Verify that a large course can be ETL'd out and recovered.
        fp, archive_file = tempfile.mkstemp(suffix='.zip')
        os.close(fp)
        try:
            parser = etl.create_args_parser()
            etl.main(parser.parse_args([
                'download', 'course', '/' + self.COURSE_NAME, 'localhost',
                '--archive_path', archive_file, '--force_overwrite',
                '--internal', '--disable_remote']))
            etl.main(parser.parse_args([
                'upload', 'course', '/' + other_course_name, 'localhost',
                '--archive_path', archive_file, '--force_overwrite',
                '--internal', '--disable_remote']))
        finally:
            os.unlink(archive_file)

        # Verify contents of course.
        course = courses.Course(handler=None, app_context=other_course_context)
        lessons = course.get_lessons(unit.unit_id)
        self.assertEquals(num_lessons, len(lessons))
        for lesson in lessons:
            self.assertEquals(lesson.objectives, LOREM_IPSUM)

    def test_large_volume_of_random_bytes_is_sharded(self):
        r = random.Random()
        r.seed(0)
        orig_data = ''.join(
            [chr(r.randrange(256))
             for x in xrange(int(vfs._MAX_VFS_SHARD_SIZE + 1))])
        namespace = 'ns_foo'
        fs = vfs.DatastoreBackedFileSystem(namespace, '/')
        filename = '/foo'
        fs.put(filename, StringIO.StringIO(orig_data))

        # fs.put() clears cache, so this will do a direct read.
        actual = fs.get(filename).read()
        self.assertEquals(orig_data, actual)

        # And again, this time from cache.
        actual = fs.get(filename).read()
        self.assertEquals(orig_data, actual)

        # Verify that sharded items exist with appropriate sizes.
        file_key_names = vfs.DatastoreBackedFileSystem._generate_file_key_names(
            filename, vfs._MAX_VFS_SHARD_SIZE + 1)
        self.assertEquals(
            2, len(file_key_names),
            'Verify attempting to store a too-large file makes multiple shards')

        with common_utils.Namespace(namespace):
            shard_0 = vfs.FileDataEntity.get_by_key_name(file_key_names[0])
            self.assertEquals(vfs._MAX_VFS_SHARD_SIZE, len(shard_0.data))

            shard_1 = vfs.FileDataEntity.get_by_key_name(file_key_names[1])
            self.assertEquals(1, len(shard_1.data))

    def test_illegal_file_name(self):
        namespace = 'ns_foo'
        fs = vfs.DatastoreBackedFileSystem(namespace, '/')
        with self.assertRaises(ValueError):
            fs.put('/name:shard:123', StringIO.StringIO('file contents'))

    def test_too_large_file_is_rejected(self):
        unit = self.course.add_unit()
        num_lessons = (
            (vfs._MAX_VFS_NUM_SHARDS * vfs._MAX_VFS_SHARD_SIZE) /
            len(LOREM_IPSUM))
        for unused in range(num_lessons):
            lesson = self.course.add_lesson(unit)
            lesson.objectives = LOREM_IPSUM
        with self.assertRaises(ValueError):
            self.course.save()

    def test_large_but_not_too_large_file_is_not_rejected(self):
        unit = self.course.add_unit()
        num_lessons = (
            ((vfs._MAX_VFS_NUM_SHARDS - 1) * vfs._MAX_VFS_SHARD_SIZE) /
            len(LOREM_IPSUM))
        for unused in range(num_lessons):
            lesson = self.course.add_lesson(unit)
            lesson.objectives = LOREM_IPSUM

        # Here, call.  Expect no ValueError from VFS, and no complaint
        # from AppEngine about cross-group transaction having too many
        # entities involved.
        self.course.save()
