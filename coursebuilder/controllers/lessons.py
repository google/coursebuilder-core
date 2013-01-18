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

"""Handlers for generating various frontend pages."""

__author__ = 'Saifu Angto (saifu@google.com)'


from models.models import Unit
from utils import BaseHandler
from google.appengine.api import users


class CourseHandler(BaseHandler):
    """Handler for generating course page."""

    def get(self):
        user = self.personalizePageAndGetUser()
        if user:
            self.templateValue['units'] = Unit.get_units()
            self.templateValue['navbar'] = {'course': True}
            self.render('course.html')
        else:
            self.redirect('/preview')


class UnitHandler(BaseHandler):
    """Handler for generating unit page."""

    def get(self):
        """Handles GET requests."""
        # Set template values for user
        user = self.personalizePageAndGetUser()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        # Extract incoming args
        c = self.request.get('unit')
        if not c:
            unit_id = 1
        else:
            unit_id = int(c)
        self.templateValue['unit_id'] = unit_id

        l = self.request.get('lesson')
        if not l:
            lesson_id = 1
        else:
            lesson_id = int(l)
        self.templateValue['lesson_id'] = lesson_id

        # Set template values for a unit and its lesson entities
        for unit in Unit.get_units():
            if unit.unit_id == str(unit_id):
                self.templateValue['units'] = unit

        lessons = Unit.get_lessons(unit_id)
        self.templateValue['lessons'] = lessons

        # Set template values for nav bar
        self.templateValue['navbar'] = {'course': True}

        # Set template values for back and next nav buttons
        if lesson_id == 1:
            self.templateValue['back_button_url'] = ''
        elif lessons[lesson_id - 2].activity:
            self.templateValue['back_button_url'] = (
                '/activity?unit=%s&lesson=%s' % (unit_id, lesson_id - 1))
        else:
            self.templateValue['back_button_url'] = (
                '/unit?unit=%s&lesson=%s' % (unit_id, lesson_id - 1))

        if lessons[lesson_id - 1].activity:
            self.templateValue['next_button_url'] = (
                '/activity?unit=%s&lesson=%s' % (unit_id, lesson_id))
        elif lesson_id == lessons.count():
            self.templateValue['next_button_url'] = ''
        else:
            self.templateValue['next_button_url'] = (
                '/unit?unit=%s&lesson=%s' % (unit_id, lesson_id + 1))

        self.render('unit.html')


class ActivityHandler(BaseHandler):
    """Handler for generating activity page."""

    def get(self):
        """Handles GET requests."""
        # Set template values for user
        user = self.personalizePageAndGetUser()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        # Extract incoming args
        c = self.request.get('unit')
        if not c:
            unit_id = 1
        else:
            unit_id = int(c)

        self.templateValue['unit_id'] = unit_id
        l = self.request.get('lesson')
        if not l:
            lesson_id = 1
        else:
            lesson_id = int(l)
        self.templateValue['lesson_id'] = lesson_id

        # Set template values for a unit and its lesson entities
        for unit in Unit.get_units():
            if unit.unit_id == str(unit_id):
                self.templateValue['units'] = unit

        lessons = Unit.get_lessons(unit_id)
        self.templateValue['lessons'] = lessons

        # Set template values for nav-x bar
        self.templateValue['navbar'] = {'course': True}

        # Set template values for back and next nav buttons
        self.templateValue['back_button_url'] = (
            '/unit?unit=%s&lesson=%s' % (unit_id, lesson_id))
        if lesson_id == lessons.count():
            self.templateValue['next_button_url'] = ''
        else:
            self.templateValue['next_button_url'] = (
                '/unit?unit=%s&lesson=%s' % (unit_id, lesson_id + 1))

        self.render('activity.html')


class AssessmentHandler(BaseHandler):
    """Handler for generating assessment page."""

    def get(self):
        """Handles GET requests."""
        # Set template values for user
        user = self.personalizePageAndGetUser()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        # Extract incoming args
        n = self.request.get('name')
        if not n:
            n = 'Pre'
        self.templateValue['name'] = n
        self.templateValue['navbar'] = {'course': True}
        self.render('assessment.html')
