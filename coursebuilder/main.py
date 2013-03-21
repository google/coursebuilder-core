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
import os
import webapp2

# The following import is needed in order to add third-party libraries.
import appengine_config  # pylint: disable-msg=unused-import
from controllers import assessments
from controllers import lessons
from controllers import sites
from controllers import utils
from modules.admin import admin
from modules.admin import config
from modules.announcements import announcements
from modules.dashboard import dashboard

urls = [
    ('/', lessons.CourseHandler),
    ('/activity', lessons.ActivityHandler),
    ('/announcements', announcements.AnnouncementsHandler),
    ('/answer', assessments.AnswerHandler),
    ('/assessment', lessons.AssessmentHandler),
    ('/course', lessons.CourseHandler),
    ('/forum', utils.ForumHandler),
    ('/dashboard', dashboard.DashboardHandler),
    ('/preview', utils.PreviewHandler),
    ('/register', utils.RegisterHandler),
    ('/student/editstudent', utils.StudentEditStudentHandler),
    ('/student/home', utils.StudentProfileHandler),
    ('/student/unenroll', utils.StudentUnenrollHandler),
    ('/unit', lessons.UnitHandler)]

sites.ApplicationRequestHandler.bind(urls)

yui_handlers = [
    ('/static/inputex-3.1.0/(.*)', sites.make_zip_handler(
        os.path.join(appengine_config.BUNDLE_ROOT, 'lib/inputex-3.1.0.zip'))),
    ('/static/yui_3.6.0/(.*)', sites.make_zip_handler(
        os.path.join(appengine_config.BUNDLE_ROOT, 'lib/yui_3.6.0.zip'))),
    ('/static/2in3/(.*)', sites.make_zip_handler(
        os.path.join(appengine_config.BUNDLE_ROOT, 'lib/yui_2in3-2.9.0.zip')))]

if appengine_config.BUNDLE_LIB_FILES:
    yui_handlers += [
        ('/static/combo/inputex', sites.make_css_combo_zip_handler(
            os.path.join(appengine_config.BUNDLE_ROOT, 'lib/inputex-3.1.0.zip'),
            '/static/inputex-3.1.0/')),
        ('/static/combo/yui', sites.make_css_combo_zip_handler(
            os.path.join(appengine_config.BUNDLE_ROOT, 'lib/yui_3.6.0.zip'),
            '/yui/')),
        ('/static/combo/2in3', sites.make_css_combo_zip_handler(
            os.path.join(
                appengine_config.BUNDLE_ROOT, 'lib/yui_2in3-2.9.0.zip'),
            '/static/2in3/'))]

admin_handlers = [
    ('/admin', admin.AdminHandler),
    ('/rest/config/item', config.ConfigPropertyItemRESTHandler),
    ('/rest/courses/item', config.CoursesItemRESTHandler)]

app_handler = (r'(.*)', sites.ApplicationRequestHandler)

webapp2_i18n_config = {'translations_path': os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules/i18n/resources/locale')}

debug = not appengine_config.PRODUCTION_MODE

app = webapp2.WSGIApplication(
    admin_handlers + yui_handlers + [app_handler],
    config={'webapp2_extras.i18n': webapp2_i18n_config},
    debug=debug)
