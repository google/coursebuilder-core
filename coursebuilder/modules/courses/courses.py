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
from controllers import utils
from models import content
from models import resources_display
from models import custom_modules
from models import roles
from models import student_labels
from modules.courses import admin_preferences_editor
from modules.courses import assets
from modules.courses import availability
from modules.courses import availability_cron
from modules.courses import constants
from modules.courses import graphql
from modules.courses import lessons
from modules.courses import outline
from modules.courses import roles as course_roles
from modules.courses import settings
from modules.courses import unit_lesson_editor
from tools import verify


custom_module = None


def register_module():
    """Registers this module in the registry."""

    permissions = []

    def permissions_callback(unused_application_context):
        return permissions

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

        outline.on_module_enabled(custom_module)
        assets.on_module_enabled()
        admin_preferences_editor.on_module_enabled()
        availability.on_module_enabled(custom_module, permissions)
        course_roles.on_module_enabled(custom_module, permissions)
        graphql.notify_module_enabled()
        lessons.on_module_enabled(custom_module)
        settings.on_module_enabled(custom_module, permissions)
        unit_lesson_editor.on_module_enabled(custom_module, permissions)

        roles.Roles.register_permissions(custom_module, permissions_callback)

    # provide parser to verify
    verify.parse_content = content.parse_string_in_scope

    global_handlers = [
        (availability_cron.StartAvailabilityJobs.URL,
         availability_cron.StartAvailabilityJobs),
    ]

    # setup routes
    courses_routes = [
        ('/forum', utils.ForumHandler),
        ('/register', utils.RegisterHandler),
        ('/rest/locale', utils.StudentLocaleRESTHandler),
        ('/student/editstudent', utils.StudentEditStudentHandler),
        ('/student/settracks', utils.StudentSetTracksHandler),
        ('/student/home', utils.StudentProfileHandler),
        ('/student/unenroll', utils.StudentUnenrollHandler),
        ]
    courses_routes += admin_preferences_editor.get_namespaced_handlers()
    courses_routes += availability.get_namespaced_handlers()
    courses_routes += settings.get_namespaced_handlers()
    courses_routes += unit_lesson_editor.get_namespaced_handlers()
    courses_routes += student_labels.get_namespaced_handlers()
    courses_routes += lessons.get_namespaced_handlers()

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        constants.MODULE_NAME,
        'A set of pages for delivering an online course.',
        global_handlers, courses_routes,
        notify_module_enabled=on_module_enabled)
    return custom_module
