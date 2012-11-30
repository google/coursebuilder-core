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

import os

import webapp2
import jinja2

from controllers import servings, lessons, utils

urls = [
  ('/', servings.CourseHandler),
  ('/register', utils.RegisterHandler),
  ('/course', servings.CourseHandler),
  ('/unit', servings.ClassHandler),
  ('/activity', servings.ActivityHandler),
  ('/assessment', servings.AssessmentHandler),
  ('/forum', servings.ForumHandler),
  ('/answer', servings.AnswerHandler),
  ('/announcements', utils.AnnouncementsHandler),
  ('/admin/home', utils.AdminHomeHandler),
  ('/student/home', utils.StudentProfileHandler),
  ('/student/editstudent', utils.StudentEditStudentHandler),
  ('/student/unenroll', utils.StudentUnenrollHandler),
  ('/admin/unenrollstudent', utils.AdminUnenrollHandler),
  ('/admin/editstudent', utils.AdminEditStudentHandler),
  ('/admin/coursepage', lessons.CourseHandler),
  ('/admin/unitpage', lessons.ClassHandler),
  ('/admin/activitypage', lessons.ActivityHandler),
  ('/admin/assessmentpage', lessons.AssessmentHandler),
  ('/admin/forumpage', utils.ForumHandler),
  ('/admin/answerpage', utils.AnswerHandler),
  ('/_ah/warmup', utils.WarmupHandler)
  ]

app = webapp2.WSGIApplication(urls, debug=True)
