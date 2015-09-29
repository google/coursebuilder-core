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

"""Module providing limited permissions for individual runs of courses."""

__author__ = 'Mike Gainer (mgainer@google.com)'

from models import courses
from models import custom_modules
from models import models
from models import permissions
from models import resources_display
from models import roles
from modules.courses import constants
from modules.courses import courses as modules_courses

MODULE_NAME = 'Runs'
TA_PERMISSION_NAME = 'teaching_assistant'
TA_ROLE_NAME = 'Teaching Assistant'
IS_RUN = 'is_run'

custom_module = None


def maybe_create_teaching_assistant_role():
    # TODO(mgainer): Hook this up to code that creates a run.
    for role in models.RoleDAO.get_all():
        if (role.name == TA_ROLE_NAME and
            role.permissions.get(MODULE_NAME, []) == [TA_ROLE_NAME]):
            return

    role_dto = models.RoleDTO(None, {
        'name': TA_ROLE_NAME,
        'permissions': {
            MODULE_NAME: [
                TA_PERMISSION_NAME],
            modules_courses.MODULE_NAME: [
                constants.COURSE_OUTLINE_REORDER_PERMISSION],
            },
        'description': ('Limited permissions to modify short-running '
                        'courses copied from master versions.  This '
                        'includes re-setting assignment due dates to '
                        'match the term of the run, and similar items.'),
        'users': []})
    roles.RoleDAO.save(role_dto)


def permissions_callback(app_context):
    return [roles.Permission(
        TA_PERMISSION_NAME,
        'Limited permissions to modify settings on short-running courses.')
    ]


def notify_module_enabled():

    # Roles configuration
    roles.Roles.register_permissions(custom_module, permissions_callback)

    # Roles with TA permission can edit course availability, start/end dates.
    permissions.SchemaPermissionRegistry.add(
        constants.SCOPE_COURSE_SETTINGS,
        permissions.SimpleSchemaPermission(
            custom_module, TA_PERMISSION_NAME, editable_list=[
                'course/course:now_available',
                'course/course:browsable',
                ]))

    # Roles with TA permission can edit unit availability, start/end dates.
    permissions.SchemaPermissionRegistry.add(
        constants.SCOPE_UNIT,
        permissions.SimpleSchemaPermission(
            custom_module, TA_PERMISSION_NAME,
            readable_list=[
                'type',
                'title',
                'description',
                ],
            editable_list=[
                'is_draft',
                'shown_when_unavailable',
                ]))
    permissions.SchemaPermissionRegistry.add(
        constants.SCOPE_LINK,
        permissions.SimpleSchemaPermission(
            custom_module, TA_PERMISSION_NAME,
            readable_list=[
                'type',
                'title',
                'description',
                ],
            editable_list=[
                'is_draft',
                'shown_when_unavailable',
                ]))
    permissions.SchemaPermissionRegistry.add(
        constants.SCOPE_ASSESSMENT,
        permissions.SimpleSchemaPermission(
            custom_module, TA_PERMISSION_NAME,
            readable_list=[
                'type',
                'title',
                'description',
                ],
            editable_list=[
                'assessment/is_draft',
                'assessment/shown_when_unavailable',
                'assessment/%s' % resources_display.workflow_key(
                    courses.SINGLE_SUBMISSION_KEY),
                'assessment/%s' % resources_display.workflow_key(
                    courses.SUBMISSION_DUE_DATE_KEY),
                'assessment/%s' % resources_display.workflow_key(
                    courses.SHOW_FEEDBACK_KEY),
                'assessment/%s' % resources_display.workflow_key(
                    courses.SHOW_SCORE_KEY),
                'assessment/%s' % resources_display.workflow_key(
                    courses.GRADER_KEY),
                'review_opts/%s' % resources_display.workflow_key(
                    courses.MATCHER_KEY),
                'assessment/%s' % resources_display.workflow_key(
                    courses.REVIEW_DUE_DATE_KEY),
                'assessment/%s' % resources_display.workflow_key(
                    courses.REVIEW_MIN_COUNT_KEY),
                'assessment/%s' % resources_display.workflow_key(
                    courses.REVIEW_WINDOW_MINS_KEY),
                ]))


def register_module():
    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        MODULE_NAME,
        'Reduced editing privileges for short-lived runs of courses cloned '
        'from a master version.',
        [],
        [],
        notify_module_enabled=notify_module_enabled)
    return custom_module
