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

import messages

import appengine_config
from common import jinja_utils
from common import safe_dom
from common import tags
from controllers import sites
from controllers.utils import ApplicationHandler
from controllers.utils import ReflectiveRequestHandler
import models
from models import config
from models import counters
from models import courses
from models import custom_modules
from models import roles
from models.config import ConfigProperty
import modules.admin.config
from modules.admin.config import ConfigPropertyEditor

from google.appengine.api import users
import google.appengine.api.app_identity as app

DIRECT_CODE_EXECUTION_UI_ENABLED = False

# A time this module was initialized.
BEGINNING_OF_TIME = time.time()

DELEGATED_ACCESS_IS_NOT_ALLOWED = """
You must be an actual admin user to continue.
Users with the delegated admin rights are not allowed."""


def escape(text):
    """Escapes HTML in text."""
    if text:
        return cgi.escape(text)
    return text


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


class WelcomeHandler(object):

    def _redirect(self, app_context, url):
        self.app_context = app_context
        self.redirect(url)

    def get_welcome(self):
        template_values = {}
        template_values['version'] = os.environ['GCB_PRODUCT_VERSION']
        template_values['course_count'] = len(sites.get_all_courses())
        template_values['add_first_xsrf'] = self.create_xsrf_token(
            'add_first_course')
        template_values['explore_sample_xsrf'] = self.create_xsrf_token(
            'explore_sample')
        self.response.write(
            self.get_template('welcome.html', []).render(template_values))

    def _make_new_course(self, uid, title):
        """Make a new course entry."""
        errors = []
        admin_email = users.get_current_user().email()
        entry = sites.add_new_course_entry(
            uid, title, admin_email, errors)
        if errors:
            raise Exception(errors)
        app_context = sites.get_all_courses(entry)[0]
        new_course = models.courses.Course(None, app_context=app_context)
        new_course.init_new_course_settings(title, admin_email)
        return app_context

    def _copy_sample_course(self, uid):
        """Make a fresh copy of sample course."""
        src_app_context = sites.get_all_courses('course:/:/:')[0]
        dst_app_context = self._make_new_course(
            uid, src_app_context.get_title())
        errors = []
        dst_course = courses.Course(None, dst_app_context)
        dst_course.import_from(src_app_context, errors)
        dst_course.save()
        if errors:
            raise Exception(errors)
        return dst_app_context

    def post_explore_sample(self):
        """Navigate to or import sample course."""
        uid = 'sample'
        course = sites.get_course_index(
            ).get_app_context_for_namespace('ns_%s' % uid)
        if course:
            self._redirect(course, '/dashboard')
            return
        course = self._copy_sample_course(uid)
        self._redirect(course, '/dashboard')

    def post_add_first_course(self):
        """Adds first course to the deployment."""
        uid = 'first'
        course = sites.get_course_index().get_course_for_path('/%s' % uid)
        if course:
            self._redirect(course, '/dashboard')
            return
        course = self._make_new_course(uid, 'My First Course')
        self._redirect(course, '/dashboard')


class AdminHandler(
    ApplicationHandler, ReflectiveRequestHandler, ConfigPropertyEditor,
    WelcomeHandler):
    """Handles all pages and actions required for administration of site."""

    default_action = 'courses'

    @property
    def get_actions(self):
        actions = [
            self.default_action, 'settings', 'deployment', 'perf',
            'config_edit', 'add_course', 'welcome']
        if DIRECT_CODE_EXECUTION_UI_ENABLED:
            actions.append('console')
        return actions

    @property
    def post_actions(self):
        actions = [
            'config_reset', 'config_override', 'explore_sample',
            'add_first_course']
        if DIRECT_CODE_EXECUTION_UI_ENABLED:
            actions.append('console_run')
        return actions

    def can_view(self):
        """Checks if current user has viewing rights."""
        action = self.request.get('action')
        if action in ['add_course', 'add_first_course']:
            return modules.admin.config.CoursesPropertyRights.can_add()
        return roles.Roles.is_super_admin()

    def can_edit(self):
        """Checks if current user has editing rights."""
        return self.can_view()

    def get(self):
        """Enforces rights to all GET operations."""
        action = self.request.get('action')

        if action in self.get_actions:
            destination = '/admin?action=%s' % action
        else:
            destination = '/admin'

        user = users.get_current_user()
        if not user:
            self.redirect(users.create_login_url(destination), normalize=False)
            return
        if not self.can_view():
            if appengine_config.PRODUCTION_MODE:
                self.error(403)
            else:
                self.redirect(
                    users.create_login_url(destination), normalize=False)
            return
        if not sites.get_all_courses() and not action:
            self.redirect('/admin?action=welcome', normalize=False)
            return

        # Force reload of properties. It's expensive, but admin deserves it!
        config.Registry.get_overrides(force_update=True)

        return super(AdminHandler, self).get()

    def post(self):
        """Enforces rights to all POST operations."""
        if not self.can_edit():
            self.redirect('/', normalize=False)
            return
        return super(AdminHandler, self).post()

    def get_template(self, template_name, dirs):
        """Sets up an environment and Gets jinja template."""
        return jinja_utils.get_template(
            template_name, dirs + [os.path.dirname(__file__)])

    def _get_user_nav(self):
        current_action = self.request.get('action')
        nav_mappings = [
            ('welcome', 'Welcome'),
            ('courses', 'Courses'),
            ('settings', 'Settings'),
            ('perf', 'Metrics'),
            ('deployment', 'Deployment')]
        if DIRECT_CODE_EXECUTION_UI_ENABLED:
            nav_mappings.append(('console', 'Console'))
        nav = safe_dom.NodeList()
        for action, title in nav_mappings:
            if action == current_action:
                elt = safe_dom.Element(
                    'a', href='/admin?action=%s' % action,
                    className='selected')
            else:
                elt = safe_dom.Element('a', href='/admin?action=%s' % action)
            elt.add_text(title)
            nav.append(elt).append(safe_dom.Text(' '))

        if appengine_config.gcb_appstats_enabled():
            nav.append(safe_dom.Element(
                'a', target='_blank', href='/admin/stats/'
            ).add_text('Appstats')).append(safe_dom.Text(' '))

        if appengine_config.PRODUCTION_MODE:
            app_id = app.get_application_id()
            nav.append(safe_dom.Element(
                'a', target='_blank',
                href=(
                    'https://appengine.google.com/'
                    'dashboard?app_id=s~%s' % app_id)
            ).add_text('Google App Engine'))
        else:
            nav.append(safe_dom.Element(
                'a', target='_blank', href='http://localhost:8000/'
            ).add_text('Google App Engine')).append(safe_dom.Text(' '))

        nav.append(safe_dom.Element(
            'a', target='_blank',
            href='https://code.google.com/p/course-builder/wiki/AdminPage'
        ).add_text('Help'))

        nav.append(safe_dom.Element(
            'a',
            href=(
                'https://groups.google.com/forum/'
                '?fromgroups#!forum/course-builder-announce'),
            target='_blank'
        ).add_text('News'))

        return nav

    def render_page(self, template_values):
        """Renders a page using provided template values."""

        template_values['top_nav'] = self._get_user_nav()
        template_values['user_nav'] = safe_dom.NodeList().append(
            safe_dom.Text('%s | ' % users.get_current_user().email())
        ).append(
            safe_dom.Element(
                'a', href=users.create_logout_url(self.request.uri)
            ).add_text('Logout')
        )
        template_values[
            'page_footer'] = 'Created on: %s' % datetime.datetime.now()

        self.response.write(
            self.get_template('view.html', []).render(template_values))

    def render_dict(self, source_dict, title):
        """Renders a dictionary ordered by keys."""
        keys = sorted(source_dict.keys())

        content = safe_dom.NodeList()
        content.append(safe_dom.Element('h3').add_text(title))
        ol = safe_dom.Element('ol')
        content.append(ol)
        for key in keys:
            value = source_dict[key]
            if isinstance(value, ConfigProperty):
                value = value.value
            ol.add_child(
                safe_dom.Element('li').add_text('%s: %s' % (key, value)))
        return content

    def format_title(self, text):
        """Formats standard title."""
        return safe_dom.NodeList().append(
            safe_dom.Text('Course Builder ')
        ).append(
            safe_dom.Entity('&gt;')
        ).append(
            safe_dom.Text(' Admin ')
        ).append(
            safe_dom.Entity('&gt;')
        ).append(
            safe_dom.Text(' %s' % text))

    def get_perf(self):
        """Shows server performance counters page."""
        template_values = {}
        template_values['page_title'] = self.format_title('Metrics')
        template_values['page_description'] = messages.METRICS_DESCRIPTION

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
            global_value = all_counters[name].global_value
            if not global_value:
                global_value = 'NA'
            perf_counters[name] = '%s / %s' % (
                all_counters[name].value, global_value)

        template_values['main_content'] = self.render_dict(
            perf_counters, 'In-process Performance Counters (local/global)')
        self.render_page(template_values)

    def _make_routes_dom(self, parent_element, routes, caption):
        """Renders routes as DOM."""
        if routes:
            # sort routes
            all_routes = []
            for route in routes:
                if route:
                    all_routes.append(str(route))

            # render as DOM
            ul = safe_dom.Element('ul')
            parent_element.add_child(ul)

            ul.add_child(safe_dom.Element('li').add_text(caption))
            ul2 = safe_dom.Element('ul')
            ul.add_child(ul2)
            for route in sorted(all_routes):
                if route:
                    ul2.add_child(safe_dom.Element('li').add_text(route))

    def get_deployment(self):
        """Shows server environment and deployment information page."""
        template_values = {}
        template_values['page_title'] = self.format_title('Deployment')
        template_values['page_description'] = messages.DEPLOYMENT_DESCRIPTION

        # modules
        module_content = safe_dom.NodeList()
        module_content.append(
            safe_dom.Element('h3').add_text('Modules'))
        ol = safe_dom.Element('ol')
        module_content.append(ol)
        for name in sorted(custom_modules.Registry.registered_modules.keys()):
            enabled_text = ''
            if name not in custom_modules.Registry.enabled_module_names:
                enabled_text = ' (disabled)'

            li = safe_dom.Element('li').add_text('%s%s' % (name, enabled_text))
            ol.add_child(li)

            amodule = custom_modules.Registry.registered_modules.get(name)
            self._make_routes_dom(
                li, amodule.global_routes, 'Global Routes')
            self._make_routes_dom(
                li, amodule.namespaced_routes, 'Namespaced Routes')

        # Custom tags.
        tag_content = safe_dom.NodeList()
        tag_content.append(
            safe_dom.Element('h3').add_text('Custom Tags'))
        ol = safe_dom.Element('ol')
        tag_content.append(ol)
        tag_bindings = tags.get_tag_bindings()
        for name in sorted(tag_bindings.keys()):
            clazz = tag_bindings.get(name)
            tag = clazz()
            vendor = tag.vendor()
            ol.add_child(safe_dom.Element('li').add_text(
                '%s: %s: %s' % (name, tag.__class__.__name__, vendor)))

        # Yaml file content.
        yaml_content = safe_dom.NodeList()
        yaml_content.append(
            safe_dom.Element('h3').add_text('Contents of ').add_child(
                safe_dom.Element('code').add_text('app.yaml')))
        ol = safe_dom.Element('ol')
        yaml_content.append(ol)
        yaml_lines = open(os.path.join(os.path.dirname(
            __file__), '../../app.yaml'), 'r').readlines()
        for line in yaml_lines:
            ol.add_child(safe_dom.Element('li').add_text(line))

        # Application identity.
        app_id = app.get_application_id()
        app_dict = {}
        app_dict['application_id'] = escape(app_id)
        app_dict['default_ver_hostname'] = escape(
            app.get_default_version_hostname())

        template_values['main_content'] = safe_dom.NodeList().append(
            self.render_dict(app_dict, 'About the Application')
        ).append(
            module_content
        ).append(
            tag_content
        ).append(
            yaml_content
        ).append(
            self.render_dict(os.environ, 'Server Environment Variables'))

        self.render_page(template_values)

    def get_settings(self):
        """Shows configuration properties information page."""
        template_values = {}
        template_values['page_title'] = self.format_title('Settings')
        template_values['page_description'] = messages.SETTINGS_DESCRIPTION

        content = safe_dom.NodeList()
        table = safe_dom.Element('table', className='gcb-config').add_child(
            safe_dom.Element('tr').add_child(
                safe_dom.Element('th').add_text('Name')
            ).add_child(
                safe_dom.Element('th').add_text('Current Value')
            ).add_child(
                safe_dom.Element('th').add_text('Actions')
            ).add_child(
                safe_dom.Element('th').add_text('Description')
            ))
        content.append(
            safe_dom.Element('h3').add_text('All Settings')
        ).append(table)

        def get_style_for(value, value_type):
            """Formats CSS style for given value."""
            style = ''
            if not value or value_type in [int, long, bool]:
                style = 'text-align: center;'
            return style

        def get_action_html(caption, args, onclick=None, idName=None):
            """Formats actions <a> link."""
            a = safe_dom.Element(
                'a', href='/admin?%s' % urllib.urlencode(args),
                className='gcb-button'
            ).add_text(caption)
            if onclick:
                a.add_attribute(onclick=onclick)
            if idName:
                a.add_attribute(id=idName)
            return a

        def get_actions(name, override):
            """Creates actions appropriate to an item."""
            if override:
                return get_action_html('Edit', {
                    'action': 'config_edit', 'name': name}, idName=name)
            else:
                return safe_dom.Element(
                    'form',
                    action='/admin?%s' % urllib.urlencode(
                        {'action': 'config_override', 'name': name}),
                    method='POST'
                ).add_child(
                    safe_dom.Element(
                        'input', type='hidden', name='xsrf_token',
                        value=self.create_xsrf_token('config_override'))
                ).add_child(
                    safe_dom.Element(
                        'button', className='gcb-button', type='submit', id=name
                    ).add_text('Override'))

        def get_doc_string(item, default_value):
            """Formats an item documentation string for display."""
            doc_string = item.doc_string
            if not doc_string:
                doc_string = 'No documentation available.'
            if isinstance(doc_string, safe_dom.NodeList) or isinstance(
                    doc_string, safe_dom.Node):
                return safe_dom.NodeList().append(doc_string).append(
                    safe_dom.Text(' Default: \'%s\'.' % default_value))
            doc_string = ' %s Default: \'%s\'.' % (doc_string, default_value)
            return safe_dom.Text(doc_string)

        def get_lines(value):
            """Convert \\n line breaks into <br> and escape the lines."""
            escaped_value = safe_dom.NodeList()
            for line in str(value).split('\n'):
                escaped_value.append(
                    safe_dom.Text(line)).append(safe_dom.Element('br'))
            return escaped_value

        # get fresh properties and their overrides
        unused_overrides = config.Registry.get_overrides(force_update=True)
        registered = config.Registry.registered.copy()
        db_overrides = config.Registry.db_overrides.copy()
        names_with_draft = config.Registry.names_with_draft.copy()

        count = 0
        for name in sorted(registered.keys()):
            count += 1
            item = registered[name]
            has_environ_value, unused_environ_value = item.get_environ_value()

            # figure out what kind of override this is
            class_current = ''
            if has_environ_value:
                class_current = 'gcb-env-diff'
            if item.name in db_overrides:
                class_current = 'gcb-db-diff'
            if item.name in names_with_draft:
                class_current = 'gcb-db-draft'

            # figure out default and current value
            default_value = item.default_value
            value = item.value
            if default_value:
                default_value = str(default_value)
            if value:
                value = str(value)

            style_current = get_style_for(value, item.value_type)

            tr = safe_dom.Element('tr')
            table.add_child(tr)

            tr.add_child(
                safe_dom.Element(
                    'td', style='white-space: nowrap;').add_text(item.name))

            td_value = safe_dom.Element('td').add_child(get_lines(value))
            if style_current:
                td_value.add_attribute(style=style_current)
            if class_current:
                td_value.add_attribute(className=class_current)
            tr.add_child(td_value)

            tr.add_child(
                safe_dom.Element(
                    'td', style='white-space: nowrap;', align='center'
                ).add_child(get_actions(
                    name, name in db_overrides or name in names_with_draft)))

            tr.add_child(
                safe_dom.Element(
                    'td').add_child(get_doc_string(item, default_value)))

        table.add_child(
            safe_dom.Element('tr').add_child(
                safe_dom.Element(
                    'td', colspan='4', align='right'
                ).add_text('Total: %s item(s)' % count)))

        content.append(
            safe_dom.Element('p').add_child(
                safe_dom.Element('strong').add_text('Legend')
            ).add_text(':').add_text("""
                For each property, the value shown corresponds to, in
                descending order of priority:
            """).add_child(
                safe_dom.Element('span', className='gcb-db-diff').add_child(
                    safe_dom.Entity('&nbsp;')
                ).add_text(
                    '[ the value override set via this page ]'
                ).add_child(safe_dom.Entity('&nbsp;'))
            ).add_text(', ').add_child(
                safe_dom.Element('span', className='gcb-db-draft').add_child(
                    safe_dom.Entity('&nbsp;')
                ).add_text(
                    '[ the default value with pending value override ]'
                ).add_child(safe_dom.Entity('&nbsp;'))
            ).add_text(', ').add_child(
                safe_dom.Element('span', className='gcb-env-diff').add_child(
                    safe_dom.Entity('&nbsp;')
                ).add_text(
                    '[ the environment value in app.yaml ]'
                ).add_child(safe_dom.Entity('&nbsp;'))
            ).add_text(', ').add_text("""
                and the [ default value ] in the Course Builder codebase.
            """))

        template_values['main_content'] = content
        self.render_page(template_values)

    def get_courses(self):
        """Shows a list of all courses available on this site."""
        template_values = {}
        template_values['page_title'] = self.format_title('Courses')
        template_values['page_description'] = messages.COURSES_DESCRIPTION

        content = safe_dom.NodeList()
        content.append(
            safe_dom.Element(
                'a', id='add_course', className='gcb-button gcb-pull-right',
                role='button', href='admin?action=add_course'
            ).add_text('Add Course')
        ).append(
            safe_dom.Element('div', style='clear: both; padding-top: 2px;')
        ).append(
            safe_dom.Element('h3').add_text('All Courses')
        )
        table = safe_dom.Element('table')
        content.append(table)
        table.add_child(
            safe_dom.Element('tr').add_child(
                safe_dom.Element('th').add_text('Course Title')
            ).add_child(
                safe_dom.Element('th').add_text('Context Path')
            ).add_child(
                safe_dom.Element('th').add_text('Content Location')
            ).add_child(
                safe_dom.Element('th').add_text('Student Data Location')
            )
        )
        count = 0
        for course in sorted(
            sites.get_all_courses(),
            key=lambda course: course.get_title().lower()):
            count += 1
            error = safe_dom.Text('')
            slug = course.get_slug()
            name = course.get_title()

            if course.fs.is_read_write():
                location = 'namespace: %s' % course.get_namespace_name()
            else:
                location = 'disk: %s' % sites.abspath(
                    course.get_home_folder(), '/')

            if slug == '/':
                link = '/dashboard'
            else:
                link = '%s/dashboard' % slug
            link = safe_dom.Element('a', href=link).add_text(name)

            table.add_child(
                safe_dom.Element('tr').add_child(
                    safe_dom.Element('td').add_child(link).add_child(error)
                ).add_child(
                    safe_dom.Element('td').add_text(slug)
                ).add_child(
                    safe_dom.Element('td').add_text(location)
                ).add_child(
                    safe_dom.Element('td').add_text(
                        'namespace: %s' % course.get_namespace_name())
                ))

        table.add_child(
            safe_dom.Element('tr').add_child(
                safe_dom.Element('td', colspan='4', align='right').add_text(
                    'Total: %s item(s)' % count)))
        template_values['main_content'] = content

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

        content = safe_dom.NodeList()
        content.append(
            safe_dom.Element('p').add_child(
                safe_dom.Element('i').add_child(
                    safe_dom.Element('strong').add_text('WARNING!')
                ).add_text("""
 The Interactive Console has the same
access to the application's environment and services as a .py file
inside the application itself. Be careful, because this means writes
to your data store will be executed for real!""")
            )
        ).append(
            safe_dom.Element('p').add_child(
                safe_dom.Element('strong').add_text("""
Input your Python code below and press "Run Program" to execute.""")
            )
        ).append(
            safe_dom.Element(
                'form', action='/admin?action=console_run', method='POST'
            ).add_child(
                safe_dom.Element(
                    'input', type='hidden', name='xsrf_token',
                    value=self.create_xsrf_token('console_run'))
            ).add_child(
                safe_dom.Element(
                    'textarea', style='width: 95%; height: 200px;',
                    name='code')
            ).add_child(
                safe_dom.Element('p', align='center').add_child(
                    safe_dom.Element(
                        'button', className='gcb-button', type='submit'
                    ).add_text('Run Program')
                )
            )
        )

        template_values['main_content'] = content
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
        content = safe_dom.NodeList()
        content.append(
            safe_dom.Element('h3').add_text('Submitted Python Code'))
        ol = safe_dom.Element('ol')
        content.append(ol)
        for line in code.split('\n'):
            ol.add_child(safe_dom.Element('li').add_text(line))

        content.append(
            safe_dom.Element('h3').add_text('Execution Results')
        ).append(
            safe_dom.Element('ol').add_child(
                safe_dom.Element('li').add_text('Status: %s' % status)
            ).add_child(
                safe_dom.Element('li').add_text('Duration (sec): %s' % duration)
            )
        ).append(
            safe_dom.Element('h3').add_text('Program Output')
        ).append(
            safe_dom.Element('blockquote').add_child(
                safe_dom.Element('pre').add_text(output))
        )

        template_values['main_content'] = content
        self.render_page(template_values)


custom_module = None


def register_module():
    """Registers this module in the registry."""

    admin_handlers = [
        ('/admin', AdminHandler),
        ('/rest/config/item', (
            modules.admin.config.ConfigPropertyItemRESTHandler)),
        ('/rest/courses/item', modules.admin.config.CoursesItemRESTHandler)]

    global custom_module
    custom_module = custom_modules.Module(
        'Site Admin',
        'A set of pages for Course Builder site administrator.',
        admin_handlers, [])
    return custom_module
