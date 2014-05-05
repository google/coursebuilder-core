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
from models import analytics
from models import custom_modules
from models import data_sources
from models import student_labels

# Import, register, & enable modules named in app.yaml's GCB_REGISTERED_MODULES.
appengine_config.import_and_enable_modules()

# Collect routes (URL-matching regexes -> handler classes) for modules.
global_routes, namespaced_routes = custom_modules.Registry.get_all_routes()

# Collect routes from core components; these are always present.
global_routes.extend(analytics.get_global_handlers())
namespaced_routes.extend(analytics.get_namespaced_handlers())
namespaced_routes.extend(data_sources.get_namespaced_handlers())
namespaced_routes.extend(student_labels.get_namespaced_handlers())

# Configure routes available at '/%namespace%/' context paths
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
    debug=not appengine_config.PRODUCTION_MODE)
