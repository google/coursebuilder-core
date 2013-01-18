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

"""Manages mapping of users to roles and roles to privileges."""

__author__ = 'Pavel Simakov (psimakov@google.com)'


import config
from google.appengine.api import users


GCB_ADMIN_LIST = config.ConfigProperty(
    'gcb_admin_list', str, (
        'A new line separated list of email addresses of administrative users. '
        'Regular expressions are not supported, exact match only.'),
    '', multiline=True)

KEY_COURSE = 'course'
KEY_ADMIN_USER_EMAILS = 'admin_user_emails'


class Roles(object):
    """A class that provides information about user roles."""

    @classmethod
    def is_direct_super_admin(cls):
        """Checks if current user is a super admin, without delegation."""
        return users.is_current_user_admin()

    @classmethod
    def is_super_admin(cls):
        """Checks if current user is a super admin, possibly via delegation."""
        if cls.is_direct_super_admin():
            return True

        user = users.get_current_user()
        if user and user.email() in GCB_ADMIN_LIST.value:
            return True
        return False

    @classmethod
    def is_course_admin(cls, app_context):
        """Checks if a user is a course admin, possibly via delegation."""
        if cls.is_super_admin():
            return True

        if KEY_COURSE in app_context.get_environ():
            environ = app_context.get_environ()[KEY_COURSE]
            if KEY_ADMIN_USER_EMAILS in environ:
                allowed = environ[KEY_ADMIN_USER_EMAILS]
                user = users.get_current_user()
                if user and '[%s]' % user.email() in allowed:
                    return True

        return False

