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

import datetime
from google.appengine.ext import db

class Student(db.Model):
  """Student profile."""
  enrolled_date = db.DateTimeProperty(auto_now_add=True)
  precourse_answer = db.TextProperty()
  midterm_answer = db.TextProperty()
  final_answer = db.TextProperty()
  precourse_score = db.IntegerProperty()
  midterm_score = db.IntegerProperty()
  final_score = db.IntegerProperty()
  overall_score = db.IntegerProperty()
  name = db.StringProperty()

class Unit(db.Model):
  """Unit metadata."""
  id = db.IntegerProperty()
  type = db.StringProperty()
  unit_id = db.StringProperty()
  title = db.StringProperty()
  release_date = db.StringProperty()
  now_available = db.BooleanProperty()

class Lesson(db.Model):
  """Lesson metadata."""
  unit_id = db.IntegerProperty()
  id = db.IntegerProperty()
  title = db.StringProperty()
  objectives = db.TextProperty()
  video = db.TextProperty()
  notes = db.TextProperty()
  activity = db.StringProperty()
  activity_title = db.StringProperty()
