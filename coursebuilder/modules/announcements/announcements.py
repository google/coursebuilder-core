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
from google.appengine.ext import db


SAMPLE_ANNOUNCEMENT_1 = {
    'edit_url': None,
    'title': 'Example Announcement',
    'date': 'Oct 6, 2012',
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
    'date': 'Oct 5, 2012',
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


class AnnouncementsHandler(BaseHandler):
    """Handler for announcements."""

    @classmethod
    def getChildRoutes(cls):
        """Add child handler for REST."""
        return [('/rest/item', ItemRESTHandler)]

    def initSampleAnnouncements(self, announcements):
        """Loads sample data into a database."""
        items = []
        for item in announcements:
            entity = AnnouncementEntity()
            entity.from_dict(item)
            entity.put()
            items.append(entity)
        return items

    def canSeeDraftAnnouncements(self):
        return users.is_current_user_admin()

    def applyRights(self, items):
        """Filter out items that current user can't see."""
        if self.canSeeDraftAnnouncements():
            return items

        allowed = []
        for item in items:
            if not item.is_draft:
                allowed.append(item)

        return allowed

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

        # TODO(psimakov): cache this page and invalidate the cache on update
        items = AnnouncementEntity.all().order('-date').fetch(1000)
        if not items:
            items = self.initSampleAnnouncements(
                [SAMPLE_ANNOUNCEMENT_1, SAMPLE_ANNOUNCEMENT_2])

        items = self.applyRights(items)

        self.template_value['announcements'] = {}
        self.template_value['announcements']['children'] = items
        self.template_value['announcements']['add_url'] = None

        self.template_value['navbar'] = {'announcements': True}
        self.render('announcements.html')


class ItemRESTHandler(BaseHandler):
    """Provides REST API for an announcement."""
    # TODO(psimakov): complete this handler
    pass


class AnnouncementEntity(db.Model):
    """A class that represents a persistent database entity of announcement."""

    title = db.StringProperty()
    date = db.StringProperty()
    html = db.TextProperty()
    is_draft = db.BooleanProperty()

    def from_dict(self, source_dict):
        """Sets this object attributes from a dictionary of values."""
        for key, value in source_dict.items():
            setattr(self, key, value)
