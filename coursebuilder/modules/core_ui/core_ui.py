# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Module to hold shared client-side (JavaScript) UI."""

__author__ = 'John Orr (jorr@google.com)'

import os

import appengine_config
from common import jinja_utils
from controllers import sites
from controllers import utils
from models import custom_modules

custom_module = None


# TODO(jorr): Bring IifeHandler and JQueryHandler in here.


class StyleGuideHandler(utils.ApplicationHandler):
    _TEMPLATES = os.path.join(
        appengine_config.BUNDLE_ROOT, 'modules', 'core_ui', 'templates',
        'style_guide')

    def get(self):
        if appengine_config.PRODUCTION_MODE:
            self.error(404)
            return
        self.response.write(jinja_utils.get_template(
            'style_guide.html', [self._TEMPLATES]).render())


def register_module():
    # https://github.com/dc-js
    #
    # "Multi-Dimensional charting built to work natively with
    # crossfilter rendered with d3.js"
    dc_handler = sites.make_zip_handler(os.path.join(
        appengine_config.BUNDLE_ROOT, 'lib', 'dc.js-1.6.0.zip'))

    # https://github.com/square/crossfilter
    #
    # "Crossfilter is a JavaScript library for exploring large
    # multivariate datasets in the browser. Crossfilter supports
    # extremely fast (<30ms) interaction with coordinated views, even
    # with datasets containing a million or more records; we built it
    # to power analytics for Square Register, allowing merchants to
    # slice and dice their payment history fluidly."
    crossfilter_handler = sites.make_zip_handler(os.path.join(
        appengine_config.BUNDLE_ROOT, 'lib', 'crossfilter-1.3.7.zip'))

    # http://d3js.org/
    #
    # "D3.js is a JavaScript library for manipulating documents based
    # on data. D3 helps you bring data to life using HTML, SVG and
    # CSS. D3's emphasis on web standards gives you the full
    # capabilities of modern browsers without tying yourself to a
    # proprietary framework, combining powerful visualization
    # components and a data-driven approach to DOM manipulation."
    d3_handler = sites.make_zip_handler(os.path.join(
        appengine_config.BUNDLE_ROOT, 'lib', 'd3-3.4.3.zip'))

    underscore_js_handler = sites.make_zip_handler(os.path.join(
        appengine_config.BUNDLE_ROOT, 'lib', 'underscore-1.4.3.zip'))

    dep_graph_handler = sites.make_zip_handler(os.path.join(
        appengine_config.BUNDLE_ROOT, 'lib', 'dependo-0.1.4.zip'))

    global_routes = [
        ('/modules/core_ui/style_guide/style_guide.html', StyleGuideHandler),
        ('/static/codemirror/(.*)', sites.make_zip_handler(os.path.join(
            appengine_config.BUNDLE_ROOT, 'lib/codemirror-4.5.0.zip'))),
        ('/static/crossfilter-1.3.7/(crossfilter-1.3.7/crossfilter.min.js)',
         crossfilter_handler),
        ('/static/d3-3.4.3/(d3.min.js)', d3_handler),
        ('/static/dc.js-1.6.0/(dc.js-1.6.0/dc.js)', dc_handler),
        ('/static/dc.js-1.6.0/(dc.js-1.6.0/dc.min.js)', dc_handler),
        ('/static/dc.js-1.6.0/(dc.js-1.6.0/dc.min.js.map)', dc_handler),
        ('/static/dc.js-1.6.0/(dc.js-1.6.0/dc.css)', dc_handler),
        ('/static/material-design-icons/(.*)',
            sites.make_zip_handler(os.path.join(
                appengine_config.BUNDLE_ROOT, 'lib',
                'material-design-iconic-font-1.1.1.zip'))),
        ('/static/underscore-1.4.3/(underscore.min.js)', underscore_js_handler),
        ('/static/dependo-0.1.4/(.*)', dep_graph_handler),
    ]
    namespaced_routes = []

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Core UI',
        'Shared client-side UI',
        global_routes,
        namespaced_routes)

    return custom_module
