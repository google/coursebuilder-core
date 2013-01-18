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

"""Main package for Course Builder, which handles URL routing."""
import webapp2

# The following import is needed in order to add third-party libraries.
import appengine_config  # pylint: disable-msg=unused-import
from controllers import assessments
from controllers import servings
from controllers import sites
from controllers import utils
from modules.announcements import announcements
from google.appengine.ext.zipserve import make_zip_handler


# FIXME: set to 'False' before going live
debug = True

urls = [
    ('/', servings.CourseHandler),
    ('/activity', servings.ActivityHandler),
    ('/announcements', announcements.AnnouncementsHandler),
    ('/answer', assessments.AnswerHandler),
    ('/assessment', servings.AssessmentHandler),
    ('/course', servings.CourseHandler),
    ('/forum', servings.ForumHandler),
    ('/preview', servings.PreviewHandler),
    ('/register', utils.RegisterHandler),
    ('/student/editstudent', utils.StudentEditStudentHandler),
    ('/student/home', utils.StudentProfileHandler),
    ('/student/unenroll', utils.StudentUnenrollHandler),
    ('/unit', servings.UnitHandler)]

sites.ApplicationRequestHandler.bind(urls)

inputex_handler = (
    '/static/inputex-3.1.0/(.*)', make_zip_handler('lib/inputex-3.1.0.zip'))

app_handler = (r'(.*)', sites.ApplicationRequestHandler)

webapp2_i18n_config = {'translations_path': 'modules/i18n/resources/locale'}

app = webapp2.WSGIApplication(
    [inputex_handler, app_handler],
    config={'webapp2_extras.i18n': webapp2_i18n_config}, debug=debug)
