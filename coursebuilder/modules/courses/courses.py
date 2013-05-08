# Copyright 2012 Google Inc. All Rights Reserved.
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

"""Courses module."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

from controllers import assessments
from controllers import lessons
from controllers import utils
from models import content
from models import custom_modules
from tools import verify


custom_module = None


def register_module():
    """Registers this module in the registry."""

    # provide parser to verify
    verify.parse_content = content.parse_string_in_scope

    # setup routes
    courses_routes = [
        ('/', lessons.CourseHandler),
        ('/activity', lessons.ActivityHandler),
        ('/answer', assessments.AnswerHandler),
        ('/assessment', lessons.AssessmentHandler),
        ('/course', lessons.CourseHandler),
        ('/forum', utils.ForumHandler),
        ('/preview', utils.PreviewHandler),
        ('/register', utils.RegisterHandler),
        ('/review', lessons.ReviewHandler),
        ('/reviewdashboard', lessons.ReviewDashboardHandler),
        ('/student/editstudent', utils.StudentEditStudentHandler),
        ('/student/home', utils.StudentProfileHandler),
        ('/student/unenroll', utils.StudentUnenrollHandler),
        ('/unit', lessons.UnitHandler)]

    global custom_module
    custom_module = custom_modules.Module(
        'Course',
        'A set of pages for delivering an online course.',
        [], courses_routes)
    return custom_module
