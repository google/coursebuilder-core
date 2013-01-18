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

import datetime
import json
import urllib
from controllers.utils import BaseHandler
from models.models import Student
import models.transforms as transforms
from modules.oeditor.oeditor import ObjectEditor
from google.appengine.api import users
from google.appengine.ext import db


ANNOUNCEMENT_ENTITY_SCHEMA = {
    'id': 'Announcement Entity',
    'description': 'Announcement',
    'type': 'object',
    'properties': {
        'title': {'type': 'string', 'optional': True},
        'date': {'type': 'date', 'optional': True},
        'html': {'type': 'text', 'optional': True},
        'is_draft': {'type': 'boolean'}
        }
    }

# add inputex specific annotations
ANNOUNCEMENT_ENTITY_SCHEMA['properties']['date']['_inputex'] = {
    '_type': 'datepicker', 'dateFormat': 'Y/m/d', 'valueFormat': 'Y/m/d'
    }

SAMPLE_ANNOUNCEMENT_1 = {
    'edit_url': None,
    'title': 'Example Announcement',
    'date': datetime.date(2012, 10, 6),
    'is_draft': False,
    'html': """
        <br>Certificates will be e-mailed to qualifying participants by
        Friday, October 12.
        <br>
        <br>Do you want to check your assessment scores? Visit the
        <a href="student/home">"My profile"</a> page!</p>
        """}

SAMPLE_ANNOUNCEMENT_2 = {
    'edit_url': None,
    'title': 'Welcome to Class 6 and the Post-class Assessment',
    'date': datetime.date(2012, 10, 5),
    'is_draft': True,
    'html': """
        <br>Welcome to the final class! <a href="class?class=6"> Class 6</a>
        focuses on combining the skills you have learned throughout the class
        to maximize the effectiveness of your searches.
        <br>
        <br><b>Customize Your Experience</b>
        <br>You can customize your experience in several ways:
        <ul>
          <li>You can watch the videos multiple times for a deeper understanding
          of each lesson. </li>
          <li>You can read the text version for each lesson. Click the button
          above the video to access it.</li>
          <li>Lesson activities are designed for multiple levels of experience.
          The first question checks your recall of the material in the video;
          the second question lets you verify your mastery of the lesson; the
          third question is an opportunity to apply your skills and share your
          experiences in the class forums. You can answer some or all of the
          questions depending on your familiarity and interest in the topic.
          Activities are not graded and do not affect your final grade. </li>
          <li>We'll also post extra challenges in the forums for people who seek
          additional opportunities to practice and test their new skills!</li>
        </ul>

        <br><b>Forum</b>
        <br>Apply your skills, share with others, and connect with your peers
        and course staff in the <a href="forum">forum.</a> Discuss your favorite
        search tips and troubleshoot technical issues. We'll also post bonus
        videos and challenges there!

        <p> </p>
        <p>For an optimal learning experience, please plan to use the most
        recent version of your browser, as well as a desktop, laptop or a tablet
        computer instead of your mobile phone.</p>
        """}


def init_sample_announcements(announcements):
    """Loads sample data into a database."""
    items = []
    for item in announcements:
        entity = AnnouncementEntity()
        transforms.dict_to_entity(entity, item)
        entity.put()
        items.append(entity)
    return items


class AnnouncementsRights(object):
    """Manages view/edit rights for announcements."""

    @classmethod
    def can_view(cls):
        return True

    @classmethod
    def can_edit(cls):
        return users.is_current_user_admin()

    @classmethod
    def can_delete(cls):
        return cls.can_edit()

    @classmethod
    def can_add(cls):
        return cls.can_edit()


class AnnouncementsHandler(BaseHandler):
    """Handler for announcements."""

    default_action = 'list'
    get_actions = [default_action, 'edit']
    post_actions = ['add', 'delete']

    @classmethod
    def get_child_routes(cls):
        """Add child handlers for REST."""
        return [('/rest/announcements/item', ItemRESTHandler)]

    def get_edit_action_url(self, key):
        args = {'action': 'edit', 'key': key}
        return self.canonicalize_url(
            '/announcements?%s' % urllib.urlencode(args))

    def get_delete_action_url(self, key):
        args = {'action': 'delete', 'key': key}
        return self.canonicalize_url(
            '/announcements?%s' % urllib.urlencode(args))

    def apply_rights(self, items):
        """Filter out items that current user can't see."""
        if AnnouncementsRights.can_edit():
            return items

        allowed = []
        for item in items:
            if not item.is_draft:
                allowed.append(item)

        return allowed

    def get(self):
        """Handles GET."""
        action = self.request.get('action')
        if not action:
            action = AnnouncementsHandler.default_action

        if not action in AnnouncementsHandler.get_actions:
            self.error(404)
            return

        handler = getattr(self, 'get_%s' % action)
        if not handler:
            self.error(404)
            return

        return handler()

    def post(self):
        """Handles POST."""
        action = self.request.get('action')
        if not action or not action in AnnouncementsHandler.post_actions:
            self.error(404)
            return

        handler = getattr(self, 'post_%s' % action)
        if not handler:
            self.error(404)
            return

        return handler()

    def get_list(self):
        """Shows a list of announcements."""
        user = self.personalize_page_and_get_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))
            return

        student = Student.get_enrolled_student_by_email(user.email())
        if not student:
            self.redirect('/preview')
            return

        # TODO(psimakov): cache this page and invalidate the cache on update
        items = AnnouncementEntity.all().order('-date').fetch(1000)
        if not items:
            items = init_sample_announcements(
                [SAMPLE_ANNOUNCEMENT_1, SAMPLE_ANNOUNCEMENT_2])

        items = self.apply_rights(items)

        args = {}
        args['children'] = items

        if AnnouncementsRights.can_edit():
            # add 'edit' actions
            for item in items:
                item.edit_action = self.get_edit_action_url(item.key())
                item.delete_action = self.get_delete_action_url(item.key())

            # add 'add' action
            args['add_action'] = self.canonicalize_url(
                '/announcements?action=add')

        self.template_value['announcements'] = args
        self.template_value['navbar'] = {'announcements': True}
        self.render('announcements.html')

    def get_edit(self):
        """Shows an editor for an announcement."""
        if not AnnouncementsRights.can_edit():
            self.error(401)
            return

        key = self.request.get('key')
        rest_url = self.canonicalize_url('/rest/announcements/item')
        form_html = ObjectEditor.get_html_for(
            self, ANNOUNCEMENT_ENTITY_SCHEMA, key, rest_url)
        self.template_value['navbar'] = {'announcements': True}
        self.template_value['content'] = form_html
        self.render('bare.html')

    def post_delete(self):
        """Deletes an announcement."""
        if not AnnouncementsRights.can_delete():
            self.error(401)
            return

        key = self.request.get('key')
        entity = AnnouncementEntity.get(key)
        if entity:
            entity.delete()
        self.redirect('/announcements')

    def post_add(self):
        """Adds a new announcement and redirects to an editor for it."""
        if not AnnouncementsRights.can_add():
            self.error(401)
            return

        entity = AnnouncementEntity()
        entity.title = 'Sample Announcement'
        entity.date = datetime.datetime.now().date()
        entity.html = 'Here is my announcement!'
        entity.is_draft = True
        entity.put()
        self.redirect(self.get_edit_action_url(entity.key()))


def send_json_response(handler, status_code, message, payload_dict=None):
    """Formats and sends out a JSON REST response envelope and body."""
    response = {}
    response['status'] = status_code
    response['message'] = message
    if payload_dict:
        response['payload'] = json.dumps(payload_dict)
    handler.response.write(json.dumps(response))


class ItemRESTHandler(BaseHandler):
    """Provides REST API for an announcement."""

    def get(self):
        """Handles REST GET verb and returns an object as JSON payload."""
        key = self.request.get('key')
        try:
            entity = AnnouncementEntity.get(key)
        except db.BadKeyError:
            entity = None

        if not entity:
            send_json_response(self, 404, 'Object not found.', {'key': key})
        else:
            json_payload = transforms.dict_to_json(transforms.entity_to_dict(
                entity), ANNOUNCEMENT_ENTITY_SCHEMA)
            send_json_response(self, 200, 'Success.', json_payload)

    def put(self):
        """Handles REST PUT verb with JSON payload."""
        request = json.loads(self.request.get('request'))
        key = request.get('key')

        if not AnnouncementsRights.can_edit():
            send_json_response(self, 401, 'Access denied.', {'key': key})
            return

        entity = AnnouncementEntity.get(key)
        if not entity:
            send_json_response(self, 404, 'Object not found.', {'key': key})
            return

        payload = request.get('payload')
        transforms.dict_to_entity(entity, transforms.json_to_dict(
            json.loads(payload), ANNOUNCEMENT_ENTITY_SCHEMA))
        entity.put()

        send_json_response(self, 200, 'Saved.')


class AnnouncementEntity(db.Model):
    """A class that represents a persistent database entity of announcement."""
    title = db.StringProperty()
    date = db.DateProperty()
    html = db.TextProperty()
    is_draft = db.BooleanProperty()
