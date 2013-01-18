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


class Roles(object):
    """A class that provides information about user roles."""

    @classmethod
    def is_super_admin(cls):
        """Checks if current user is a super admin."""
        user = users.get_current_user()
        if user and users.is_current_user_admin():
            return True
        if user and user.email() in GCB_ADMIN_LIST.value:
            return True
        return False
