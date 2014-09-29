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
from models import roles
from tools import verify


All_LOCALES_PERMISSION = 'can_pick_all_locales'
All_LOCALES_DESCRIPTION = 'Can pick all locales, including unavailable ones.'

SEE_DRAFTS_PERMISSION = 'can_see_draft_content'
SEE_DRAFTS_DESCRIPTION = 'Can see lessons and assessments with draft status.'


custom_module = None


def can_pick_all_locales(app_context):
    return roles.Roles.is_user_allowed(
        app_context, custom_module, All_LOCALES_PERMISSION)


def can_see_drafts(app_context):
    return roles.Roles.is_user_allowed(
        app_context, custom_module, SEE_DRAFTS_PERMISSION)


def register_module():
    """Registers this module in the registry."""

    def on_module_enabled():
        roles.Roles.register_permissions(
            custom_module, permissions_callback)

    def on_module_disabled():
        roles.Roles.unregister_permissions(custom_module)

    def permissions_callback(unused_app_context):
        return [
            roles.Permission(All_LOCALES_PERMISSION, All_LOCALES_DESCRIPTION),
            roles.Permission(SEE_DRAFTS_PERMISSION, SEE_DRAFTS_DESCRIPTION)
        ]

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
        ('/unit', lessons.UnitHandler)]

    global custom_module
    custom_module = custom_modules.Module(
        'Course',
        'A set of pages for delivering an online course.',
        [], courses_routes,
        notify_module_enabled=on_module_enabled,
        notify_module_disabled=on_module_disabled)
    return custom_module
