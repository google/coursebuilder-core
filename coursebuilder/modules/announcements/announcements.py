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

"""Handlers that manages Announcements."""

__author__ = 'Saifu Angto (saifu@google.com)'

from controllers.utils import BaseHandler
from models.models import Student
from google.appengine.api import users


class AnnouncementsHandler(BaseHandler):
    """Handler for announcements."""

    def get(self):
        """Handles GET requests."""
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        student = Student.get_enrolled_student_by_email(user.email())
        if not student:
            self.redirect('/preview')
            return

        self.template_value['navbar'] = {'announcements': True}
        self.render('announcements.html')
