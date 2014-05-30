# Copyright 2014 Google Inc. All Rights Reserved.
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

"""Module providing public analytics interfaces."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import os
import re
import sys
import jinja2

import appengine_config
from controllers import sites
from controllers import utils as controllers_utils
from models.analytics import display
from models.analytics import utils as analytics_utils
from models import data_sources

by_name = {}


class Visualization(object):

    def __init__(self, name, title, html_template_name,
                 data_source_classes=None):
        """Establish a new visualization.

        Args:
            name: Valid Javascript identifier to be used for this visualization
                when generating scripts via templates.

            title: Section title for visualization on the
                Dashboard -> Analytics page.

            html_template_name: Name of a file which contains a Jinja template
                which will be used to generate a chart or graph for the
                visualization.  This can be specified as a path relative to
                the CB installation root
                (e.g. 'modules/my_new_module/my_visualization.html'), or
                relative to any of the data sources or generators used for the
                visualization (meaning you can just use the name of the HTML
                file without any path components if it's in the same
                directory).

            data_source_classes: An optional array of data source classes.
                This should contain only classes inheriting from
                data_sources.base_types._DataSource.
        Raises:
            ValueError: when any of
            - name is already registered as an visualization
            - name is not a valid JavaScript identifier.
            - a data source class is not registered with the data_sources
              module.
        """


        if name and not re.match('^[_0-9a-z]+$', name):
            raise ValueError(
                'name "%s" must contain only lowercase letters, ' % name +
                'numbers or underscore characters')
        if name in by_name:
            raise ValueError(
                'Visualization %s is already registered' % name)
        data_source_classes = data_source_classes or []
        for data_source_class in data_source_classes:
            if not data_sources.Registry.is_registered(data_source_class):
                raise ValueError(
                    'All data source classes used in visualizations must be '
                    'registered in models.data_sources.Registry; '
                    '"%s" is not registered.' % data_source_class.__name__)

        self._name = name
        self._title = title
        self._template_name = html_template_name
        self._data_source_classes = data_source_classes
        by_name[name] = self

    @property
    def name(self):
        return self._name

    @property
    def title(self):
        return self._title

    @property
    def template_name(self):
        return self._template_name

    @property
    def generator_classes(self):
        ret = set()
        for source_class in self.data_source_classes:
          ret.update(source_class.required_generators())
        return ret

    @property
    def data_source_classes(self):
        return set(self._data_source_classes)

    @property
    def rest_data_source_classes(self):
        return set([c for c in self._data_source_classes
                    if issubclass(c, data_sources.AbstractRestDataSource)])


class _TemplateRenderer(object):
    """Insulate display code from knowing about handlers and Jinja.

    This abstraction makes unit testing simpler, as well as decouples
    the display code from being directly dependent on web-request
    handler types.
    """

    def __init__(self, handler):
        self._handler = handler

    def render(self, visualization, template_name, template_values):
        return jinja2.utils.Markup(
            self._handler.get_template(
                template_name,
                analytics_utils._get_template_dir_names(visualization)
            ).render(template_values, autoescape=True))

    def get_base_href(self):
        return controllers_utils.ApplicationHandler.get_base_href(self._handler)

    def get_current_url(self):
        return self._handler.request.url


def generate_display_html(handler, xsrf_creator, visualizations):
    """Generate sections of HTML representing each visualization.

    This generates multiple small HTML sections which are intended for
    inclusion as-is into a larger display (specifically, the dashboard
    page showing visualizations).  The HTML will likely contain JavaScript
    elements that induce callbacks from the page to the REST service
    providing JSON data.

    Args:
        handler: Must be derived from controllers.utils.ApplicationHandler.
            Used to load HTML templates and to establish page context
            for learning the course to which to restrict data loading.
        xsrf_creator: Thing which can create XSRF tokens by exposing
            a create_token(token_name) method.  Normally, set this
            to common.crypto.XsrfTokenManager.  Unit tests use a
            bogus creator to avoid DB requirement.
    Returns:
        An array of HTML sections.  This will consist of SafeDom elements
        and the result of HTML template expansion.
    """

    return display._generate_display_html(
        _TemplateRenderer(handler), xsrf_creator, handler.app_context,
        visualizations)


class AnalyticsHandler(controllers_utils.ReflectiveRequestHandler,
                       controllers_utils.ApplicationHandler):

    default_action = 'run_visualization'
    get_actions = []
    post_actions = ['run_visualizations', 'cancel_visualizations']

    def _get_generator_classes(self):
        return analytics_utils._generators_for_visualizations(
            [by_name[name] for name in self.request.get_all('visualization')])

    def post_run_visualizations(self):
        for generator_class in self._get_generator_classes():
            generator_class(self.app_context).submit()
        self.redirect(str(self.request.get('r')))

    def post_cancel_visualizations(self):
        for generator_class in self._get_generator_classes():
            generator_class(self.app_context).cancel()
        self.redirect(str(self.request.get('r')))


def get_namespaced_handlers():
    return [('/analytics', AnalyticsHandler)]


def get_global_handlers():
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

    # Restrict files served from full zip package to minimum needed
    return [
        ('/static/crossfilter-1.3.7/(crossfilter-1.3.7/crossfilter.min.js)',
         crossfilter_handler),
        ('/static/d3-3.4.3/(d3.min.js)', d3_handler),
        ('/static/dc.js-1.6.0/(dc.js-1.6.0/dc.js)', dc_handler),
        ('/static/dc.js-1.6.0/(dc.js-1.6.0/dc.min.js)', dc_handler),
        ('/static/dc.js-1.6.0/(dc.js-1.6.0/dc.min.js.map)', dc_handler),
        ('/static/dc.js-1.6.0/(dc.js-1.6.0/dc.css)', dc_handler),
    ]
