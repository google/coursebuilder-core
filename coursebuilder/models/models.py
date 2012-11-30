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
#
# @author: psimakov@google.com (Pavel Simakov)


import datetime, logging
from google.appengine.ext import db
from google.appengine.api import memcache


# amount of time to cache items for
DEFAULT_CACHE_TTL_SECS = 60 * 60


class Student(db.Model):
  """Student profile."""
  enrolled_date = db.DateTimeProperty(auto_now_add=True)

  name = db.StringProperty()
  is_enrolled = db.BooleanProperty()

  # each of the following is a string representation of a JSON dict
  answers = db.TextProperty()
  scores = db.TextProperty()

  def put(self):
    """Do the normal put() and also add the object to memcache."""
    super(Student, self).put()
    memcache.set(self.key().name(), self, DEFAULT_CACHE_TTL_SECS)

  def delete(self):
    """Do the normal delete() and also remove the object from memcache."""
    super(Student, self).delete()
    memcache.delete(self.key().name())

  @classmethod
  def get_by_email(cls, email):
    return Student.get_by_key_name(email.encode('utf8'))

  @classmethod
  def get_enrolled_student_by_email(cls, email):
    student = memcache.get(email)
    if not student:
      student = Student.get_by_email(email)
      if student:
        memcache.set(email, student, DEFAULT_CACHE_TTL_SECS)
    if student and student.is_enrolled:
      return student
    else:
      return None


class Unit(db.Model):
  """Unit metadata."""
  id = db.IntegerProperty()
  type = db.StringProperty()
  unit_id = db.StringProperty()
  title = db.StringProperty()
  release_date = db.StringProperty()
  now_available = db.BooleanProperty()

  @classmethod
  def get_units(cls):
    units = memcache.get('units')
    if units is None:
      units = Unit.all().order('id')
      memcache.set('units', units, DEFAULT_CACHE_TTL_SECS)
    return units

  @classmethod
  def get_lessons(cls, unit_id):
    lessons = memcache.get('lessons' + str(unit_id))
    if lessons is None:
      lessons = Lesson.all().filter('unit_id =', unit_id).order('id')
      memcache.set('lessons' + str(unit_id), lessons, DEFAULT_CACHE_TTL_SECS)
    return lessons


class Lesson(db.Model):
  """Lesson metadata."""
  unit_id = db.IntegerProperty()
  id = db.IntegerProperty()
  title = db.StringProperty()
  objectives = db.TextProperty()
  video = db.TextProperty()
  notes = db.TextProperty()
  slides = db.TextProperty()
  duration = db.StringProperty()
  activity = db.StringProperty()
  activity_title = db.StringProperty()

