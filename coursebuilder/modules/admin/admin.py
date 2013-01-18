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
import cStringIO
import datetime
import os
import sys
import time
import urllib
from appengine_config import PRODUCTION_MODE
from controllers import sites
from controllers.utils import ReflectiveRequestHandler
import jinja2
from models import config
from models import counters
from models import roles
from models.config import ConfigProperty
from modules.admin.config import ConfigPropertyEditor
import webapp2
from google.appengine.api import users
import google.appengine.api.app_identity as app


# A time this module was initialized.
BEGINNING_OF_TIME = time.time()

DELEGATED_ACCESS_IS_NOT_ALLOWED = """
You must be an actual admin user to continue.
Users with the delegated admin rights are not allowed."""


def evaluate_python_code(code):
    """Compiles and evaluates a Python script in a restricted environment."""

    code = code.replace('\r\n', '\n')

    save_stdout = sys.stdout
    results_io = cStringIO.StringIO()
    try:
        sys.stdout = results_io
        try:
            compiled_code = compile(code, '<string>', 'exec')
            exec(compiled_code, globals())  # pylint: disable-msg=exec-statement
        except Exception as e:              # pylint: disable-msg=broad-except
            results_io.write('Error: %s' % e)
            return results_io.getvalue(), False
    finally:
        sys.stdout = save_stdout
    return results_io.getvalue(), True


class AdminHandler(
    webapp2.RequestHandler, ReflectiveRequestHandler, ConfigPropertyEditor):
    """Handles all pages and actions required for administration of site."""

    default_action = 'courses'
    get_actions = [
        default_action, 'settings', 'deployment', 'perf', 'config_edit',
        'console']
    post_actions = ['config_reset', 'config_override', 'console_run']

    def can_view(self):
        """Checks if current user has viewing rights."""
        return roles.Roles.is_super_admin()

    def can_edit(self):
        """Checks if current user has editing rights."""
        return self.can_view()

    def get(self):
        """Enforces rights to all GET operations."""
        if not self.can_view():
            self.redirect('/')
            return
        return super(AdminHandler, self).get()

    def post(self):
        """Enforces rights to all POST operations."""
        if not self.can_edit():
            self.redirect('/')
            return
        return super(AdminHandler, self).post()

    def get_template(self, template_name, dirs):
        """Sets up an environment and Gets jinja template."""
        jinja_environment = jinja2.Environment(
            loader=jinja2.FileSystemLoader(dirs + [os.path.dirname(__file__)]))
        return jinja_environment.get_template(template_name)

    def render_page(self, template_values):
        """Renders a page using provided template values."""

        if PRODUCTION_MODE:
            app_id = app.get_application_id()
            console_link = """
                <a target="_blank"
                  href="https://appengine.google.com/dashboard?app_id=s~%s">
                  Google App Engine
                </a>
                """ % app_id
        else:
            console_link = """
                <a target="_blank" href="/_ah/admin">Google App Engine</a>
                """

        template_values['top_nav'] = """
          <a href="/admin">Courses</a>
          <a href="/admin?action=settings">Settings</a>
          <a href="/admin?action=perf">Metrics</a>
          <a href="/admin?action=deployment">Deployment</a>
          <a href="/admin?action=console">Console</a>
          %s
          """ % console_link
        template_values['user_nav'] = '%s | <a href="%s">Logout</a>' % (
            users.get_current_user().email(), users.create_logout_url('/'))
        template_values[
            'page_footer'] = 'Created on: %s' % datetime.datetime.now()

        self.response.write(
            self.get_template('view.html', []).render(template_values))

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

    def format_title(self, text):
        """Formats standard title."""
        return 'Course Builder &gt; Admin &gt; %s' % text

    def get_perf(self):
        """Shows server performance counters page."""
        template_values = {}
        template_values['page_title'] = self.format_title('Metrics')

        perf_counters = {}

        # built in counters
        perf_counters['gcb-admin-uptime-sec'] = long(
            time.time() - BEGINNING_OF_TIME)

        # config counters
        perf_counters['gcb-config-overrides'] = len(
            config.Registry.get_overrides())
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
        template_values['page_title'] = self.format_title('Deployment')

        # Yaml file content.
        yaml_content = []
        yaml_content.append('<h3>Contents of <code>app.yaml</code></h3>')
        yaml_content.append('<ol>')
        yaml_lines = open(os.path.join(os.path.dirname(
            __file__), '../../app.yaml'), 'r').readlines()
        for line in yaml_lines:
            yaml_content.append('<li>%s</li>' % cgi.escape(line))
        yaml_content.append('</ol>')
        yaml_content = ''.join(yaml_content)

        # Application identity.
        app_id = app.get_application_id()
        app_dict = {}
        app_dict['application_id'] = app_id
        app_dict['default_ver_hostname'] = app.get_default_version_hostname()

        template_values['main_content'] = self.render_dict(
            app_dict,
            'About the Application') + yaml_content + self.render_dict(
                os.environ, 'Server Environment Variables')

        self.render_page(template_values)

    def get_settings(self):
        """Shows configuration properties information page."""
        template_values = {}
        template_values['page_title'] = self.format_title('Settings')

        content = []
        content.append("""
            <style>
              span.gcb-db-diff, td.gcb-db-diff {
                  background-color: #A0FFA0;
              }
              span.gcb-env-diff, td.gcb-env-diff {
                  background-color: #A0A0FF;
              }
            </style>
            """)
        content.append('<h3>All Settings</h3>')
        content.append('<table class="gcb-config">')
        content.append("""
            <tr>
            <th>Name</th>
            <th>Current Value</th>
            <th>Actions</th>
            <th>Description</th>
            </tr>
            """)

        def get_style_for(value, value_type):
            """Formats CSS style for given value."""
            style = ''
            if not value or value_type in [int, long, bool]:
                style = 'style="text-align: center;"'
            return style

        def get_action_html(caption, args, onclick=None):
            """Formats actions <a> link."""
            handler = ''
            if onclick:
                handler = 'onclick="%s"' % onclick
            return '<a %s class="gcb-button" href="/admin?%s">%s</a>' % (
                handler, urllib.urlencode(args), cgi.escape(caption))

        def get_actions(name, override):
            """Creates actions appropriate to an item."""
            actions = []
            if override:
                actions.append(get_action_html('Edit', {
                    'action': 'config_edit', 'name': name}))
            else:
                actions.append("""
                    <form action='/admin?%s' method='POST'>
                    <input type="hidden" name="xsrf_token" value="%s">
                    <button class="gcb-button" type="submit">
                      Override
                    </button></form>""" % (
                        urllib.urlencode(
                            {'action': 'config_override', 'name': name}),
                        cgi.escape(self.create_xsrf_token('config_override'))
                    ))
            return ''.join(actions)

        def get_doc_string(item, default_value):
            """Formats an item documentation string for display."""
            doc_string = item.doc_string
            if doc_string:
                doc_string = cgi.escape(doc_string)
            else:
                doc_string = 'No documentation available.'
            doc_string = ' %s Default: "%s".' % (doc_string, default_value)
            return doc_string

        overrides = config.Registry.get_overrides(True)
        registered = config.Registry.registered.copy()

        count = 0
        for name in sorted(registered.keys()):
            count += 1
            item = registered[name]

            default_value = item.default_value
            has_environ_value, environ_value = item.get_environ_value()
            value = item.value

            class_current = 'class="gcb-db-diff"'
            if value == default_value:
                class_current = ''
            if has_environ_value and value == environ_value:
                class_current = 'class="gcb-env-diff"'

            if default_value:
                default_value = cgi.escape(str(default_value))
            if value:
                value = cgi.escape(str(value))

            style_current = get_style_for(value, item.value_type)

            content.append("""
                <tr>
                <td style='white-space: nowrap;'>%s</td>
                <td %s %s>%s</td>
                <td style='white-space: nowrap;' align='center'>%s</td>
                <td>%s</td>
                </tr>
                """ % (
                    item.name, class_current, style_current, value,
                    get_actions(name, name in overrides),
                    get_doc_string(item, default_value)))

        content.append("""
            <tr><td colspan="4" align="right">Total: %s item(s)</td></tr>
            """ % count)

        content.append('</table>')
        content.append("""
            <p><strong>Legend</strong>:
            For each property, the value shown corresponds to, in
            descending order of priority:
            <span class='gcb-db-diff'>
                &nbsp;[ the value set via this page ]&nbsp;</span>,
            <span class='gcb-env-diff'>
                &nbsp;[ the environment value in app.yaml ]&nbsp;</span>,
            and the [ default value ] in the Course Builder codebase.""")

        template_values['main_content'] = ''.join(content)

        self.render_page(template_values)

    def get_courses(self):
        """Shows a list of all courses available on this site."""
        template_values = {}
        template_values['page_title'] = self.format_title('Courses')

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
            error = ''
            slug = course.get_slug()
            location = sites.abspath(course.get_home_folder(), '/')
            try:
                name = cgi.escape(course.get_environ()['course']['title'])
            except Exception as e:  # pylint: disable-msg=broad-except
                name = 'UNKNOWN COURSE'
                error = (
                    '<p>Error in <strong>course.yaml</strong> file:<br/>'
                    '<pre>\n%s\n%s\n</pre></p>' % (
                        e.__class__.__name__, cgi.escape(str(e))))

            if slug == '/':
                link = '/dashboard'
            else:
                link = '%s/dashboard' % slug
            link = '<a href="%s">%s</a>' % (link, name)

            content.append("""
                <tr>
                  <td>%s%s</td>
                  <td>%s</td>
                  <td>%s</td>
                  <td>%s</td>
                </tr>
                """ % (
                    link, error, slug, location, course.get_namespace_name()))

        content.append("""
            <tr><td colspan="4" align="right">Total: %s item(s)</td></tr>
            """ % count)
        content.append('</table>')

        template_values['main_content'] = ''.join(content)

        self.render_page(template_values)

    def get_console(self):
        """Shows interactive Python console page."""
        template_values = {}
        template_values['page_title'] = self.format_title('Console')

        # Check rights.
        if not roles.Roles.is_direct_super_admin():
            template_values['main_content'] = DELEGATED_ACCESS_IS_NOT_ALLOWED
            self.render_page(template_values)
            return

        content = []
        content.append("""
            <p><i><strong>WARNING!</strong> The Interactive Console has the same
            access to the application's environment and services as a .py file
            inside the application itself. Be careful, because this means writes
            to your data store will be executed for real!</i></p>
            <p><strong>
              Input your Python code below and press "Run Program" to execute.
            </strong><p>
            <form action='/admin?action=console_run' method='POST'>
            <input type="hidden" name="xsrf_token" value="%s">
            <textarea
                style='width: 95%%; height: 200px;' name='code'></textarea>
            <p align='center'>
                <button class="gcb-button" type="submit">Run Program</button>
            </p>
            </form>""" % cgi.escape(self.create_xsrf_token('console_run')))

        template_values['main_content'] = ''.join(content)
        self.render_page(template_values)

    def post_console_run(self):
        """Executes dynamically submitted Python code."""
        template_values = {}
        template_values['page_title'] = self.format_title('Execution Results')

        # Check rights.
        if not roles.Roles.is_direct_super_admin():
            template_values['main_content'] = DELEGATED_ACCESS_IS_NOT_ALLOWED
            self.render_page(template_values)
            return

        # Execute code.
        code = self.request.get('code')
        time_before = time.time()
        output, results = evaluate_python_code(code)
        duration = long(time.time() - time_before)
        status = 'FAILURE'
        if results:
            status = 'SUCCESS'

        # Render results.
        content = []
        content.append('<h3>Submitted Python Code</h3>')
        content.append('<ol>')
        for line in code.split('\n'):
            content.append('<li>%s</li>' % cgi.escape(line))
        content.append('</ol>')

        content.append("""
            <h3>Execution Results</h3>
            <ol>
                <li>Status: %s</li>
                <li>Duration (sec): %s</li>
            </ol>
            """ % (status, duration))

        content.append('<h3>Program Output</h3>')
        content.append(
            '<blockquote><pre>%s</pre></blockquote>' % cgi.escape(
                output))

        template_values['main_content'] = ''.join(content)
        self.render_page(template_values)
