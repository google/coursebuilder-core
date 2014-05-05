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

from controllers import utils as controllers_utils
from models.analytics import display
from models.analytics import utils as analytics_utils
from models.analytics import registry

# Expose publicly-available types.
Registry = registry._Registry

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
                # (Package protected) pylint: disable-msg=protected-access
                analytics_utils._get_template_dir_names(analytic)
            ).render(template_values, autoescape=True))

    def get_base_href(self):
        return controllers_utils.ApplicationHandler.get_base_href(self._handler)


def generate_display_html(handler, xsrf_creator):
    """Generate sections of HTML representing each analytic.

    This generates multiple small HTML sections which are intended for
    inclusion as-is into a larger display (specifically, the dashboard
    page showing analytics).  The HTML will likely contain JavaScript
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

    # (Package protected) pylint: disable-msg=protected-access
    return display._generate_display_html(
        _TemplateRenderer(handler), xsrf_creator, handler.app_context)
