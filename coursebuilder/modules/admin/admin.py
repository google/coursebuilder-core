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

"""Site administration functionality."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import cgi
import datetime
import os
import time
import urllib
from controllers import sites
from controllers.utils import ReflectiveRequestHandler
import jinja2
from models import config
from models import counters
from models.config import ConfigProperty
from models.models import PRODUCTION_MODE
import webapp2
from google.appengine.api import users
import google.appengine.api.app_identity as app


# A time this module was initialized.
BEGINNING_OF_TIME = time.time()

GCB_ADMIN_LIST = ConfigProperty('gcb_admin_list', str, (
    'A new line separated list of email addresses of administrative users. '
    'Regular expressions are not supported, exact match only.'), '')


class AdminHandler(webapp2.RequestHandler, ReflectiveRequestHandler):
    """Handles all pages and actions required for administration of site."""

    default_action = 'courses'
    get_actions = [
        default_action, 'settings', 'deployment', 'perf', 'config_edit',
        'config_reset', 'config_override']
    post_actions = []

    def can_view(self):
        """Checks if current user has viewing rights."""
        user = users.get_current_user()
        if user and users.is_current_user_admin():
            return True
        if user and user.email() in GCB_ADMIN_LIST.value:
            return True
        return False

    def get(self):
        """Enforces rights to all GET operations."""
        if not self.can_view():
            self.redirect('/')
            return
        return super(AdminHandler, self).get()

    def render_page(self, template_values):
        """Renders a page using provided template values."""

        if PRODUCTION_MODE:
            app_id = app.get_application_id()
            console_link = """
                <a target="_blank"
                  href="https://appengine.google.com/dashboard?&'
                  app_id=s~%s">
                  Production Dashboard
                </a>
                """ % app_id
        else:
            console_link = """
                <a target="_blank" href="/_ah/admin">Development Console</a>
                """

        template_values['top_nav'] = """
          <a href="/admin">Courses</a>
          <a href="/admin?action=settings">Settings</a>
          <a href="/admin?action=perf">Metrics</a>
          <a href="/admin?action=deployment">Deployment</a>
          %s
          """ % console_link
        template_values['user_nav'] = '%s | <a href="%s">Logout</a>' % (
            users.get_current_user().email(), users.create_logout_url('/'))
        template_values[
            'page_footer'] = 'Created on: %s' % datetime.datetime.now()

        jinja_environment = jinja2.Environment(
            loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))
        self.response.write(jinja_environment.get_template(
            'admin.html').render(template_values))

    def render_dict(self, source_dict, title):
        """Renders a dictionary ordered by keys."""
        keys = sorted(source_dict.keys())

        content = []
        content.append('<h3>%s</h3>' % title)
        content.append('<ol>')
        for key in keys:
            value = source_dict[key]
            if isinstance(value, ConfigProperty):
                value = value.value
            content.append(
                '<li>%s: %s</li>' % (cgi.escape(key), cgi.escape(str(value))))
        content.append('</ol>')
        return '\n'.join(content)

    def get_perf(self):
        """Shows server performance counters page."""
        template_values = {}
        template_values['page_title'] = 'Course Builder - Metrics'

        perf_counters = {}

        # built in counters
        perf_counters['gcb-admin-uptime-sec'] = long(
            time.time() - BEGINNING_OF_TIME)

        # config counters
        config.Registry.get_overrides()
        perf_counters['gcb-config-age-sec'] = (
            long(time.time()) - config.Registry.last_update_time)
        perf_counters['gcb-config-update-time-sec'] = (
            config.Registry.last_update_time)
        perf_counters['gcb-config-update-index'] = config.Registry.update_index

        # add all registered counters
        all_counters = counters.Registry.registered.copy()
        for name in all_counters.keys():
            perf_counters[name] = all_counters[name].value

        template_values['main_content'] = self.render_dict(
            perf_counters, 'In-process Performance Counters')
        self.render_page(template_values)

    def get_deployment(self):
        """Shows server environment and deployment information page."""
        template_values = {}
        template_values['page_title'] = 'Course Builder - Deployment'

        # Yaml file content.
        yaml_content = []
        yaml_content.append('<h3>Application <code>app.yaml</code></h3>')
        yaml_content.append('<ul><pre>')
        yaml_lines = open(os.path.join(os.path.dirname(
            __file__), '../../app.yaml'), 'r').readlines()
        for line in yaml_lines:
            yaml_content.append('%s<br/>' % cgi.escape(line))
        yaml_content.append('</pre></ul>')
        yaml_content = ''.join(yaml_content)

        # Application identity.
        app_id = app.get_application_id()
        app_dict = {}
        app_dict['application_id'] = app_id
        app_dict['default_ver_hostname'] = app.get_default_version_hostname()

        template_values['main_content'] = self.render_dict(
            app_dict, 'Application Identity') + yaml_content + self.render_dict(
                os.environ, 'Server Environment Variables')

        self.render_page(template_values)

    def get_settings(self):
        """Shows configuration properties information page."""
        template_values = {}
        template_values['page_title'] = 'Course Builder - Settings'

        content = []
        content.append("""
            <style>
              table.gcb-config td.gcb-diff {
                  background-color: #A0FFA0;
              }
            </style>
            """)
        content.append('<h3>All Settings</h3>')
        content.append('<table class="gcb-config">')
        content.append("""
            <tr>
            <th>Name</th>
            <th>Default Value</th>
            <th>Current Value</th>
            <th>Actions</th>
            <th>Description</th>
            </tr>
            """)

        def get_action_html(caption, args):
            """Formats actions <a> link."""
            return '<a class="gcb-button" href="/admin?%s">%s</a>' % (
                urllib.urlencode(args), cgi.escape(caption))

        def get_style_for(value, value_type):
            """Formats CSS style for given value."""
            style = ''
            if not value or value_type in [int, long, bool]:
                style = 'style="text-align: center;"'
            return style

        config.Registry.get_overrides(True)
        registered = config.Registry.registered.copy()

        count = 0
        for name in sorted(registered.keys()):
            count += 1
            item = registered[name]
            actions = []

            doc_string = item.doc_string
            if doc_string:
                doc_string = cgi.escape(doc_string)

            default_value = item.default_value
            value = item.value
            override = default_value != value

            if default_value:
                default_value = cgi.escape(str(default_value))
            if value:
                value = cgi.escape(str(value))

            if override:
                actions.append(get_action_html('Edit', {
                    'action': 'config_edit', 'name': name}))
                actions.append(get_action_html('Reset', {
                    'action': 'config_reset', 'name': name}))
            else:
                actions.append(get_action_html('Override', {
                    'action': 'config_override', 'name': name}))

            style_default = get_style_for(item.default_value, item.value_type)
            style_current = get_style_for(value, item.value_type)
            class_current = ''
            if item.value != item.default_value:
                class_current = 'class="gcb-diff"'

            content.append("""
                <tr>
                <td style='white-space: nowrap;'>%s</td>
                <td %s>%s</td>
                <td %s %s>%s</td>
                <td align='center'>%s</td>
                <td>%s</td>
                </tr>
                """ % (
                    item.name, style_default, item.default_value,
                    class_current, style_current, value, ''.join(actions),
                    item.doc_string))

        content.append("""
            <tr><td colspan="5" align="right">Total: %s item(s)</td></tr>
            """ % count)

        content.append('</table>')

        template_values['main_content'] = ''.join(content)

        self.render_page(template_values)

    def get_courses(self):
        """Shows a list of all courses available on this site."""
        template_values = {}
        template_values['page_title'] = 'Course Builder - Courses'

        content = []
        content.append('<h3>All Courses</h3>')
        content.append('<table>')
        content.append("""
            <tr>
              <th>Course Title</th>
              <th>Context Path</th>
              <th>Content Location</th>
              <th>Datastore Namespace</th>
            </tr>
            """)
        courses = sites.get_all_courses()
        count = 0
        for course in courses:
            count += 1
            slug = course.get_slug()
            location = sites.abspath(course.get_home_folder(), '/')
            try:
                name = cgi.escape(course.get_environ()['course']['title'])
            except Exception as e:  # pylint: disable-msg=broad-except
                name = 'Error in course.yaml:<br/>%s' % cgi.escape(str(e))

            link = '<a href="%s">%s</a>' % (slug, name)

            content.append("""
                <tr>
                  <td>%s</td>
                  <td>%s</td>
                  <td>%s</td>
                  <td>%s</td>
                </tr>
                """ % (link, slug, location, course.get_namespace_name()))

        content.append("""
            <tr><td colspan="4" align="right">Total: %s item(s)</td></tr>
            """ % count)
        content.append('</table>')

        template_values['main_content'] = ''.join(content)

        self.render_page(template_values)

    def get_config_edit(self):
        """Handles 'edit' property action."""
        # TODO(psimakov): incomplete
        self.redirect('/admin?action=settings')

    def get_config_reset(self):
        """Handles 'reset' property action."""
        # TODO(psimakov): incomplete
        self.redirect('/admin?action=settings')

    def get_config_override(self):
        """Handles 'override' property action."""
        # TODO(psimakov): incomplete
        self.redirect('/admin?action=settings')
