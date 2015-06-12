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

"""Courses module."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

from common import resource
from controllers import assessments
from controllers import lessons
from controllers import utils
from models import content
from models import resources_display
from models import custom_modules
from models import student_labels
from modules.courses import admin_preferences_editor
from modules.courses import assets
from modules.courses import outline
from modules.courses import settings
from tools import verify

custom_module = None


def register_module():
    """Registers this module in the registry."""

    def on_module_enabled():
        resource.Registry.register(resources_display.ResourceCourseSettings)
        resource.Registry.register(resources_display.ResourceUnit)
        resource.Registry.register(resources_display.ResourceAssessment)
        resource.Registry.register(resources_display.ResourceLink)
        resource.Registry.register(resources_display.ResourceLesson)
        resource.Registry.register(resources_display.ResourceSAQuestion)
        resource.Registry.register(resources_display.ResourceMCQuestion)
        resource.Registry.register(resources_display.ResourceQuestionGroup)
        resource.Registry.register(utils.ResourceHtmlHook)

        outline.on_module_enabled()
        assets.on_module_enabled()
        admin_preferences_editor.on_module_enabled()
        settings.on_module_enabled()

    # provide parser to verify
    verify.parse_content = content.parse_string_in_scope

    # setup routes
    courses_routes = [
        ('/', lessons.CourseHandler),
        ('/activity', lessons.UnitHandler),
        ('/answer', assessments.AnswerHandler),
        ('/assessment', lessons.AssessmentHandler),
        ('/course', lessons.CourseHandler),
        ('/forum', utils.ForumHandler),
        ('/preview', utils.PreviewHandler),
        ('/register', utils.RegisterHandler),
        ('/rest/locale', utils.StudentLocaleRESTHandler),
        ('/review', lessons.ReviewHandler),
        ('/reviewdashboard', lessons.ReviewDashboardHandler),
        ('/student/editstudent', utils.StudentEditStudentHandler),
        ('/student/settracks', utils.StudentSetTracksHandler),
        ('/student/home', utils.StudentProfileHandler),
        ('/student/unenroll', utils.StudentUnenrollHandler),
        ('/unit', lessons.UnitHandler),
        (settings.CourseSettingsRESTHandler.URI,
         settings.CourseSettingsRESTHandler),
        (settings.HtmlHookRESTHandler.URI, settings.HtmlHookRESTHandler),
        (admin_preferences_editor.AdminPreferencesRESTHandler.URI,
         admin_preferences_editor.AdminPreferencesRESTHandler),
    ]
    courses_routes += student_labels.get_namespaced_handlers()

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Course',
        'A set of pages for delivering an online course.',
        [], courses_routes,
        notify_module_enabled=on_module_enabled)
    return custom_module
