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

"""Presents a friendly base class for dashboard handlers."""

__author__ = 'Nick Retallack (nretallack@google.com)'

from common import crypto
from common import jinja_utils
from modules.dashboard import dashboard


class AbstractDashboardHandler(dashboard.DashboardHandler):
    """Contains common patterns in dashboard handlers."""

    @property
    def TEMPLATE(self):
        """Name of a partial template this handler renders most often.

        It should be located in one of your TEMPLATE_DIRS.  It represents the
        main_content in view.html.

        This will be used when you call render_this.  If you do not call
        render_this, you don't need to populate this value.
        """
        return NotImplementedError('Subclasses must override this.')

    @property
    def TEMPLATE_DIRS(self):
        """List of places to find templates for the main_content."""
        return NotImplementedError('Subclasses must override this.')

    @property
    def ACTION(self):
        """A unique string to identify this operation.

         This is used for permissions and XSRF tokens.
         It's also used to identify menu items.
         """
        return NotImplementedError('Subclasses must override this.')

    @property
    def PAGE_TITLE(self):
        """This will be displayed in your browser's title bar."""
        return ''

    @property
    def IN_ACTION(self):
        """This determines which menu item should be active when someone visits
        your page."""
        return self.ACTION # subclasses may override this

    @property
    def EXTRA_CSS_URLS(self):
        """List of CSS files to add to the document's head."""
        return [] # subclasses may override this

    @property
    def EXTRA_JS_URLS(self):
        """List of JavaScript files to add to the document's head."""
        return [] # subclasses may override this

    @property
    def EXTRA_JS_HREF_LIST(self):
        """Backward compatibility with the existing dashboard."""
        return super(AbstractDashboardHandler, self
            ).EXTRA_JS_HREF_LIST + self.EXTRA_JS_URLS

    @property
    def EXTRA_CSS_HREF_LIST(self):
        """Backward compatibility with the existing dashboard."""
        return super(AbstractDashboardHandler, self
            ).EXTRA_CSS_HREF_LIST + self.EXTRA_CSS_URLS

    @property
    def action(self):
        """Backward compatibility with the existing dashboard."""
        return self.ACTION

    def render_this(self, **values):
        self.render_other(self.TEMPLATE, **values)

    def render_other(self, template, **values):
        self.render_content(jinja_utils.render_partial_template(
            template, self.TEMPLATE_DIRS, values, handler=self))

    def render_content(self, content):
        self.render_page({
            'page_title': self.PAGE_TITLE,
            'main_content': content,
        }, in_action=self.IN_ACTION)

    def get(self):
        # check permissions
        if not self.can_view(self.ACTION):
            self.redirect(self.app_context.get_slug(), abort=True)

    def post(self):
        # check for cross-site request forgery
        xsrf_token = self.request.headers.get('CSRF-Token', self.request.get(
            'xsrf_token_{}'.format(self.ACTION)))
        if not crypto.XsrfTokenManager.is_xsrf_token_valid(
                xsrf_token, self.ACTION):
            self.abort(403)

        # check permissions
        if not self.can_edit(self.ACTION):
            self.redirect(self.app_context.get_slug(), abort=True)

    @classmethod
    def add_to_menu(cls, group, item, title, **kwargs):
        cls.add_sub_nav_mapping(
            group, item, title,
            action=cls.ACTION,
            href=cls.URL,
            **kwargs
        )
