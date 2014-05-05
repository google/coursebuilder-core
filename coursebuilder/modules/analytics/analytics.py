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

import jinja2

from modules.analytics import display
from modules.analytics import utils

# Pull in base types from peer module so entire public interface to
# analytics is available from modules.analytics.analytics.  (We can't
# just have the classes in this file due to circular import problems.)
#
# pylint: disable-msg=unused-import
from modules.analytics.base_types import SynchronousQuery
from modules.analytics.registry import Registry


class _TemplateRenderer(object):
    """Insulate display code from knowing about handlers and Jinja.

    This abstraction makes unit testing simpler, as well as decouples
    the display code from being directly dependent on web-request
    handler types.
    """

    def __init__(self, handler):
        self._handler = handler

    def render(self, analytic, template_name, template_values):
        return jinja2.utils.Markup(
            self._handler.get_template(
                template_name,
                # Utils holds packagage-private functions common to analytics
                # pylint: disable-msg=protected-access
                utils._get_template_dir_names(analytic)
            ).render(template_values, autoescape=True))


def generate_display_html(handler, xsrf_creator):
    """Generate sections of HTML representing each analytic.

    This generates multiple small HTML sections which are intended for
    inclusion as-is into a larger display (specifically, the dashboard
    page showing analytics).  The HTML will likely contain JavaScript
    elements that induce callbacks from the page to the REST service
    providing JSON data feeds.

    Args:
        handler: Must be derived from controllers.utils.ApplicationHandler.
            Used to load HTML templates and to establish page context
            for learning the course to which to restrict data loading.
        xsrf_creator: Thing which can create XSRF tokens by exposing
            a create_token(token_name) method.  Normally, set this
            to controllers.utils.XsrfTokenManager.  Unit tests use a
            bogus creator to avoid DB requirement.
    Returns:
        An array of HTML sections.  This will consist of SafeDom elements
        and the result of HTML template expansion.
    """

    # Packagage-private access - safer to mark private and suppress lint.
    # pylint: disable-msg=protected-access
    return display._generate_display_html(
        _TemplateRenderer(handler), xsrf_creator, handler.app_context)
