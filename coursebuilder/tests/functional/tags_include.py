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

"""Verify operation of <gcb-include> custom tag."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import os
import StringIO

import appengine_config
from models import courses
from tests.functional import actions

COURSE_NAME = 'test_course'
COURSE_TITLE = 'Test Course'
ADMIN_EMAIL = 'test@example.com'
PRE_INCLUDE = 'XXX'
POST_INCLUDE = 'YYY'
HTML_DIR = os.path.join(appengine_config.BUNDLE_ROOT, 'assets/html')
HTML_FILE = 'test.html'
HTML_PATH = os.path.join(HTML_DIR, HTML_FILE)
GCB_INCLUDE = (PRE_INCLUDE +
               '<gcb-include path="/assets/html/%s" ' +
               'instanceid="uODxjWHTxxIC"></gcb-include>' +
               POST_INCLUDE)
LESSON_URL = '/test_course/unit?unit=1&lesson=2'


class TagsInclude(actions.TestBase):

    def setUp(self):
        super(TagsInclude, self).setUp()

        self.context = actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL,
                                                 COURSE_TITLE)
        self.course = courses.Course(None, self.context)
        self.unit = self.course.add_unit()
        self.unit.title = 'The Unit'
        self.unit.now_available = True
        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.title = 'The Lesson'
        self.lesson.now_available = True
        self.lesson.objectives = GCB_INCLUDE % HTML_FILE
        self.course.save()

    def tearDown(self):
        self.context.fs.delete(HTML_PATH)

    def _set_content(self, content):
        self.context.fs.put(HTML_PATH, StringIO.StringIO(content))

    def _expect_content(self, expected, response):
        expected = '%s<div>%s</div>%s' % (PRE_INCLUDE, expected, POST_INCLUDE)
        self.assertIn(expected, response.body)

    def test_missing_file_gives_error(self):
        self.lesson.objectives = GCB_INCLUDE % 'no_such_file.html'
        self.course.save()
        response = self.get(LESSON_URL)
        self.assertIn('Invalid HTML tag: no_such_file.html', response.body)

    def test_file_from_actual_filesystem(self):
        # Note: This has the potential to cause a test flake: Adding an
        # actual file to the filesystem and then removing it may cause
        # ETL tests to complain - they saw the file, then failed to copy
        # it because it went away.
        simple_content = 'Fiery the angels fell'
        if not os.path.isdir(HTML_DIR):
            os.mkdir(HTML_DIR)
        with open(HTML_PATH, 'w') as fp:
            fp.write(simple_content)
        response = self.get(LESSON_URL)
        os.unlink(HTML_PATH)
        self._expect_content(simple_content, response)

    def test_simple(self):
        simple_content = 'Deep thunder rolled around their shores'
        self._set_content(simple_content)
        response = self.get(LESSON_URL)
        self._expect_content(simple_content, response)

    def test_content_containing_tags(self):
        content = '<h1>This is a test</h1><p>This is only a test.</p>'
        self._set_content(content)
        response = self.get(LESSON_URL)
        self._expect_content(content, response)

    def test_jinja_base_path(self):
        content = '{{ base_path }}'
        self._set_content(content)
        response = self.get(LESSON_URL)
        self._expect_content('assets/html', response)

    def test_jinja_course_base(self):
        content = '{{ gcb_course_base }}'
        self._set_content(content)
        response = self.get(LESSON_URL)
        self._expect_content('http://localhost/test_course/', response)

    def test_jinja_course_title(self):
        content = '{{ course_info.course.title }}'
        self._set_content(content)
        response = self.get(LESSON_URL)
        self._expect_content('Test Course', response)

    def test_inclusion(self):
        content = 'Hello, World!'
        sub_path = os.path.join(
            appengine_config.BUNDLE_ROOT, HTML_DIR, 'sub.html')
        self.context.fs.put(sub_path, StringIO.StringIO(content))

        self._set_content('{% include "sub.html" %}')
        try:
            response = self.get(LESSON_URL)
            self._expect_content(content, response)
        finally:
            self.context.fs.delete(sub_path)
