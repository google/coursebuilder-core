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

import appengine_config, webapp2
from controllers import servings, sites, utils

# FIXME: set to 'False' before going live
debug = True

urls = [
  ('/', servings.CourseHandler),
  ('/activity', servings.ActivityHandler),
  ('/announcements', utils.AnnouncementsHandler),
  ('/answer', servings.AnswerHandler),
  ('/assessment', servings.AssessmentHandler),
  ('/course', servings.CourseHandler),
  ('/forum', servings.ForumHandler),
  ('/register', utils.RegisterHandler),
  ('/student/editstudent', utils.StudentEditStudentHandler),
  ('/student/home', utils.StudentProfileHandler),
  ('/student/unenroll', utils.StudentUnenrollHandler),
  ('/unit', servings.UnitHandler)]

sites.ApplicationRequestHandler.bind(urls)

app = webapp2.WSGIApplication(
    [(r'(.*)', sites.ApplicationRequestHandler)], debug=debug)
