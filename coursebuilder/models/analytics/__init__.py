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
          ret.update(analytics_utils._get_required_generators(source_class))
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
