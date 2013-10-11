# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Course Builder web application entry point."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import os
import webapp2

# The following import is needed in order to add third-party libraries.
import appengine_config  # pylint: disable-msg=unused-import

from common import tags
from controllers import sites
from models import custom_modules
import modules.activity_tag.activity_tag
import modules.admin.admin
import modules.announcements.announcements
import modules.assessment_tags.questions
import modules.course_explorer.course_explorer
import modules.courses.courses
import modules.dashboard.dashboard
import modules.oauth2.oauth2
import modules.oeditor.oeditor
import modules.review.review
import modules.search.search
import modules.upload.upload

# use this flag to control debug only features
debug = not appengine_config.PRODUCTION_MODE

# init and enable most known modules
modules.activity_tag.activity_tag.register_module().enable()
modules.admin.admin.register_module().enable()
modules.announcements.announcements.register_module().enable()
modules.assessment_tags.questions.register_module().enable()
modules.course_explorer.course_explorer.register_module().enable()
modules.courses.courses.register_module().enable()
modules.dashboard.dashboard.register_module().enable()
modules.oeditor.oeditor.register_module().enable()
modules.review.review.register_module().enable()
modules.search.search.register_module().enable()
modules.upload.upload.register_module().enable()

# register modules that are not enabled by default.
modules.oauth2.oauth2.register_module()

# compute all possible routes
global_routes, namespaced_routes = custom_modules.Registry.get_all_routes()

# routes available at '/%namespace%/' context paths
sites.ApplicationRequestHandler.bind(namespaced_routes)
app_routes = [(r'(.*)', sites.ApplicationRequestHandler)]

# enable Appstats handlers if requested
appstats_routes = []
if appengine_config.gcb_appstats_enabled():
    # pylint: disable-msg=g-import-not-at-top
    import google.appengine.ext.appstats.ui as appstats_ui
    # pylint: enable-msg=g-import-not-at-top

    # add all Appstats URL's to /admin/stats basepath
    for path, handler in appstats_ui.URLMAP:
        assert '.*' == path[:2]
        appstats_routes.append(('/admin/stats/%s' % path[3:], handler))

# tag extension resource routes
extensions_routes = [(
    '/extensions/tags/.*/resources/.*', tags.ResourcesHandler)]

# i18n configuration for jinja2
webapp2_i18n_config = {'translations_path': os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules/i18n/resources/locale')}

# init application
app = webapp2.WSGIApplication(
    global_routes + extensions_routes + appstats_routes + app_routes,
    config={'webapp2_extras.i18n': webapp2_i18n_config},
    debug=debug)
