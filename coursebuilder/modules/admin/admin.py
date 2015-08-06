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

"""Site administration functionality."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import cgi
import cStringIO
import datetime
import os
import sys
import time
import urllib

import appengine_config
from common import jinja_utils
from common import safe_dom
from common import tags
from common import users
from common import utils as common_utils
from controllers import sites
from controllers.utils import ApplicationHandler
from controllers.utils import ReflectiveRequestHandler
import models
from models import config
from models import counters
from models import courses
from models import custom_modules
from models import entities
from models import roles
from models.config import ConfigProperty
import modules.admin.config
from modules.admin.config import ConfigPropertyEditor
from modules.dashboard import dashboard
from common import menus

import google.appengine.api.app_identity as app
from google.appengine.ext import db

RESOURCES_PATH = '/modules/admin/resources'

TEMPLATE_DIR = os.path.join(appengine_config.BUNDLE_ROOT, 'modules', 'admin')

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
            exec(compiled_code, globals())  # pylint: disable=exec-used
        except Exception as e:  # pylint: disable=broad-except
            results_io.write('Error: %s' % e)
            return results_io.getvalue(), False
    finally:
        sys.stdout = save_stdout
    return results_io.getvalue(), True


class WelcomeHandler(ApplicationHandler, ReflectiveRequestHandler):
    default_action = 'welcome'
    get_actions = [default_action]
    post_actions = ['explore_sample', 'add_first_course', 'configure_settings']

    # Enable other modules to make changes to sample course import.
    # Each member must be a function of the form:
    #     callback(course, errors)
    COPY_SAMPLE_COURSE_HOOKS = []

    # Enable other modules to put global warnings on the welcome page.  This
    # is useful when you want to ask for permission from the installation
    # administrator, and you want to be absolutely certain the administrator
    # has seen the request.  Items appended here must be callable, taking
    # no parameters.  The return value will be inserted onto the welcome.html
    # page; see the loop adding 'item_form_content' to the page.
    WELCOME_FORM_HOOKS = []

    # Items on this list are called back when the welcome page has been
    # submitted.  These should take two parameters: the course just created
    # and the page handler object.
    POST_HOOKS = []

    def get_template(self, template_name):
        return jinja_utils.get_template(template_name, [TEMPLATE_DIR])

    def can_view(self):
        """Checks if current user has viewing rights."""
        action = self.request.get('action')
        if action == 'add_first_course':
            return modules.admin.config.CoursesPropertyRights.can_add()
        return roles.Roles.is_super_admin()

    def can_edit(self):
        """Checks if current user has editing rights."""
        return self.can_view()

    def get(self):
        user = users.get_current_user()
        if not user:
            self.redirect(
                users.create_login_url('/admin/welcome'), normalize=False)
            return
        if not self.can_view():
            return
        super(WelcomeHandler, self).get()

    def post(self):
        if not self.can_edit():
            return
        app_context = super(WelcomeHandler, self).post()
        common_utils.run_hooks(self.POST_HOOKS, app_context, self)

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
        template_values['configure_settings_xsrf'] = self.create_xsrf_token(
            'configure_settings')
        template_values['global_admin_url'] = GlobalAdminHandler.LINK_URL
        welcome_form_content = []
        for hook in self.WELCOME_FORM_HOOKS:
            welcome_form_content.append(hook())
        template_values['welcome_form_content'] = welcome_form_content
        self.response.write(
            self.get_template('welcome.html').render(template_values))

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
        dst_app_context = self._make_new_course(uid, '%s (%s)' % (
            src_app_context.get_title(), os.environ['GCB_PRODUCT_VERSION']))
        errors = []
        dst_course = courses.Course(None, dst_app_context)
        dst_course.import_from(src_app_context, errors)
        dst_course.save()
        if not errors:
            common_utils.run_hooks(
                self.COPY_SAMPLE_COURSE_HOOKS, dst_app_context, errors)
        if errors:
            raise Exception(errors)
        return dst_app_context

    def post_explore_sample(self):
        """Navigate to or import sample course."""
        course = None
        for uid in ['sample', 'sample_%s' % os.environ[
            'GCB_PRODUCT_VERSION'].replace('.', '_')]:
            course = sites.get_course_index(
                ).get_app_context_for_namespace('ns_%s' % uid)
            if not course:
                course = self._copy_sample_course(uid)
                break
        assert course is not None
        self._redirect(course, '/dashboard')
        return course

    def post_add_first_course(self):
        """Adds first course to the deployment."""
        uid = 'first'
        course = sites.get_course_index().get_course_for_path('/%s' % uid)
        if course:
            self._redirect(course, '/dashboard')
            return course
        course = self._make_new_course(uid, 'My First Course')
        self._redirect(course, '/dashboard')
        return course

    def post_configure_settings(self):
        self.redirect('/admin/global')


def can_view_admin_action(action):
    if action == 'add_course':
        return modules.admin.config.CoursesPropertyRights.can_add()
    return roles.Roles.is_super_admin()


class BaseAdminHandler(ConfigPropertyEditor):
    """Base class holding methods required for administration of site."""

    default_action = 'courses'

    class AbstractDbTypeDescriber(object):

        @classmethod
        def title(cls):
            """Return title text for table describing DB entity types."""
            raise NotImplementedError()

        @classmethod
        def describe(cls, entity_type):
            """Return SafeDom element describing entity."""
            raise NotImplementedError()

    class ModuleDescriber(AbstractDbTypeDescriber):

        @classmethod
        def title(cls):
            return "Module"

        @classmethod
        def describe(cls, entity_type):
            return safe_dom.Text(entity_type.__module__)

    class NameDescriber(AbstractDbTypeDescriber):

        @classmethod
        def title(cls):
            return "Name"

        @classmethod
        def describe(cls, entity_type):
            return safe_dom.Text(entity_type.kind())

    class HasSafeKeyDescriber(AbstractDbTypeDescriber):

        @classmethod
        def title(cls):
            return 'Has safe_key()'

        @classmethod
        def describe(cls, entity_type):
            if hasattr(entity_type, 'safe_key'):
                safe_key = getattr(entity_type, 'safe_key')
                if callable(safe_key):
                    if safe_key.im_func != entities.BaseEntity.safe_key.im_func:
                        return safe_dom.Element(
                            'div', alt='checked', title='checked',
                            classname='icon md md-check')
            return None

    class HasBlacklistDescriber(AbstractDbTypeDescriber):

        @classmethod
        def title(cls):
            return 'Has BLACKLIST'

        @classmethod
        def describe(cls, entity_type):
            if hasattr(entity_type, '_PROPERTY_EXPORT_BLACKLIST'):
                blacklist = getattr(entity_type, '_PROPERTY_EXPORT_BLACKLIST')
                if isinstance(blacklist, list) and blacklist:
                    return safe_dom.Element(
                        'div', alt='checked', title='checked',
                        classname='icon md md-check')
            return None


    DB_TYPE_DESCRIBERS = [
        ModuleDescriber,
        NameDescriber,
        HasSafeKeyDescriber,
        HasBlacklistDescriber,
    ]
    DB_TYPE_MODULE_EXCLUDES = set([
        'google.appengine.ext.blobstore.blobstore',
        'google.appengine.ext.db',
        'google.appengine.ext.db.metadata',
        'google.appengine.ext.deferred.deferred',
        'mapreduce.lib.pipeline.models',
        'mapreduce.model',
        'mapreduce.shuffler',
        'oauth2client.appengine',
    ])

    @classmethod
    def make_site_menu(cls, root_menu_group, placement):

        group = menus.MenuGroup(
            'admin', 'Site admin', group=root_menu_group, placement=placement)

        def bind(key, label, handler, href=None):
            if href:
                target = '_blank'
            else:
                target = None
                href = "{}?action={}".format(cls.LINK_URL, key)

            def can_view(app_context):
                return can_view_admin_action(key)

            menu_item = menus.MenuItem(
                key, label, action=key, can_view=can_view, group=group,
                href=href, target=target)

            if handler:
                cls.get_actions.append(key)
                cls.actions_to_menu_items[key] = menu_item

        bind('courses', 'Courses', cls.get_courses)
        bind('settings', 'Site settings', cls.get_settings)
        bind('perf', 'Metrics', cls.get_perf)
        bind('deployment', 'Deployment', cls.get_deployment)

        if DIRECT_CODE_EXECUTION_UI_ENABLED:
            bind('console', 'Console', cls.get_console)

        if appengine_config.gcb_appstats_enabled():
            bind('stats', 'Appstats', None, href='/admin/stats/')

        if appengine_config.PRODUCTION_MODE:
            app_id = app.get_application_id()
            href = (
                'https://appengine.google.com/'
                'dashboard?app_id=s~%s' % app_id)
            bind('gae', 'Google App Engine', None, href=href)
        else:
            bind(
                 'gae', 'Google App Engine', None,
                 href='http://localhost:8000/')
        bind('welcome', 'Welcome', None, href='/admin/welcome')
        bind(
             'help', 'Site help', None,
             href='https://code.google.com/p/course-builder/wiki/AdminPage')
        bind(
             'news', 'News', None,
             href=(
                'https://groups.google.com/forum/'
                '?fromgroups#!forum/course-builder-announce'))

    @classmethod
    def bind_get_actions(cls):
        cls.get_actions.append('add_course')
        cls.get_actions.append('config_edit')

    @classmethod
    def bind_post_actions(cls):
        cls.post_actions.append('config_override')
        cls.post_actions.append('config_reset')

        if DIRECT_CODE_EXECUTION_UI_ENABLED:
            cls.post_actions.append('console_run')

    def can_view(self, action):
        """Checks if current user has viewing rights."""
        # Overrides method in DashboardHandler
        return can_view_admin_action(action)

    def can_edit(self):
        """Checks if current user has editing rights."""
        # Overrides method in DashboardHandler
        action = self.request.get('action')
        return self.can_view(action)

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

        # Describe DB entity types
        entity_content = safe_dom.NodeList()
        entity_content.append(
            safe_dom.Element('h3').add_text('Database Entities'))
        entity_content.append(self._describe_db_types())
        entity_content.append(safe_dom.Element('p'))

        # Application identity and users service information.
        app_id = app.get_application_id()
        app_dict = {}
        app_dict['application_id'] = escape(app_id)
        app_dict['default_ver_hostname'] = escape(
            app.get_default_version_hostname())
        app_dict['users_service_name'] = escape(
            users.UsersServiceManager.get().get_service_name())

        # sys.path information.
        sys_path_content = safe_dom.NodeList()
        sys_path_content.append(
            safe_dom.Element('h3').add_text('sys.path')
        )
        ol = safe_dom.Element('ol')
        sys_path_content.append(ol)
        for path in sys.path:
            ol.add_child(safe_dom.Element('li').add_text(path))

        template_values['main_content'] = safe_dom.NodeList().append(
            self.render_dict(app_dict, 'About the Application')
        ).append(
            module_content
        ).append(
            entity_content
        ).append(
            tag_content
        ).append(
            yaml_content
        ).append(
            self.render_dict(os.environ, 'Server Environment Variables')
        ).append(
            sys_path_content
        )
        self.render_page(template_values)

    def _recurse_subclasses(self, entity_type, entity_types):
        for subclass in entity_type.__subclasses__():
            if subclass.__module__ not in self.DB_TYPE_MODULE_EXCLUDES:
                entity_types.append(subclass)
            self._recurse_subclasses(subclass, entity_types)

    def _describe_db_types(self):
        table = safe_dom.Element('table')
        thead = safe_dom.Element('thead')
        table.add_child(thead)
        tr = safe_dom.Element('tr')
        thead.add_child(tr)
        for describer in self.DB_TYPE_DESCRIBERS:
            th = safe_dom.Element('th')
            th.add_text(describer.title())
            tr.add_child(th)

        entity_types = []
        self._recurse_subclasses(db.Model, entity_types)
        entity_types.sort(key=lambda et: (et.__module__, et.__name__))
        tbody = safe_dom.Element('tbody')
        table.add_child(tbody)
        for entity_type in entity_types:
            tr = safe_dom.Element('tr')
            tbody.add_child(tr)
            for describer in self.DB_TYPE_DESCRIBERS:
                td = safe_dom.Element('td')
                tr.add_child(td)
                content = describer.describe(entity_type)
                if content:
                    td.add_child(content)

        return table

    def get_settings(self):
        """Shows configuration properties information page."""
        template_values = {}
        template_values['page_title'] = self.format_title('Settings')

        content = safe_dom.NodeList()
        content.append(safe_dom.Element(
            'link', rel='stylesheet',
            href='/modules/admin/resources/css/admin.css'))
        table = safe_dom.Element('table', className='gcb-config').add_child(
            safe_dom.Element('tr').add_child(
                safe_dom.Element('th').add_text('Setting')
            ).add_child(
                safe_dom.Element('th').add_text('Current Value')
            ).add_child(
                safe_dom.Element('th').add_text('Actions')
            ).add_child(
                safe_dom.Element('th').add_text('Description')
            ))
        content.append(table)

        def get_style_for(value, value_type):
            """Formats CSS style for given value."""
            style = ''
            if not value or value_type in [int, long, bool]:
                style = 'text-align: center;'
            return style

        def get_action_html(caption, args, onclick=None, idName=None):
            """Formats actions <a> link."""
            a = safe_dom.Element(
                'a', href='%s?%s' % (
                    self.LINK_URL, urllib.urlencode(args)),
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
                    action='%s?%s' % (
                        self.LINK_URL,
                        urllib.urlencode(
                            {'action': 'config_override', 'name': name})),
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
            if isinstance(doc_string, safe_dom.SafeDom):
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
                    'td', style='white-space: nowrap;',
                    title=item.name).add_text(item.label))

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

        content = safe_dom.NodeList()
        content.append(
            safe_dom.Element('div', className='gcb-button-toolbar'
            ).append(
                safe_dom.Element(
                    'a', id='add_course', className='gcb-button',
                    role='button', href='%s?action=add_course' % self.LINK_URL
                ).add_text('Add Course')
            )
        ).append(
            safe_dom.Element('div', style='clear: both; padding-top: 2px;')
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

        self.render_page(template_values, in_action='courses')

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
                'form',
                action='%s?action=console_run' % self.LINK_URL,
                method='POST'
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
            safe_dom.Element('div', className='gcb-message').add_child(
                safe_dom.Element('pre').add_text(output))
        )

        template_values['main_content'] = content
        self.render_page(template_values, in_action='console')

    @classmethod
    def enable(cls):
        cls.bind_get_actions()
        cls.bind_post_actions()
        cls.make_menu()

    @classmethod
    def disable(cls):
        cls.post_actions = []
        cls.get_actions = []

    def default_action_for_current_permissions(self):
        """Set the default or first active navigation tab as default action."""
        item = self.root_menu_group.get_child(
            'admin').first_visible_item(self.app_context)
        if item:
            return item.action
        else:
            return None


class AdminHandler(BaseAdminHandler, dashboard.DashboardHandler):
    """Handler to present admin settings in namespaced context."""

    # The binding URL for this handler
    URL = '/admin'

    # The URL used in relative addreses of this handler
    LINK_URL = 'admin'

    # Isolate this class's actions list from its parents
    get_actions = []
    post_actions = []

    def format_title(self, text):
        return super(AdminHandler, self).format_title(
            'Admin > %s' % text)

    def get_template(self, template_name, dirs):
        return super(AdminHandler, self).get_template(
            template_name, [TEMPLATE_DIR] + dirs)

    def get_course_picker(self, destination=None, in_action=None):
        return super(AdminHandler, self).get_course_picker(
            destination='/admin', in_action=in_action)

    @classmethod
    def make_menu(cls):
        cls.make_site_menu(
            dashboard.DashboardHandler.root_menu_group, placement=7000)

    @classmethod
    def disable(cls):
        super(AdminHandler, cls).disable()
        group = dashboard.DashboardHandler.root_menu_group
        group.remove_child(group.get_child('admin'))


class GlobalAdminHandler(
        BaseAdminHandler, ApplicationHandler, ReflectiveRequestHandler):
    """Handler to present admin settings in global context."""

    # The binding URL for this handler
    URL = '/admin/global'

    # The URL used in relative addreses of this handler
    LINK_URL = '/admin/global'

    # List of functions which are used to generate content displayed at the top
    # of every dashboard page. Use this with caution, as it is extremely
    # invasive of the UX. Each function receives the handler as arg and returns
    # an object to be inserted into a Jinja template (e.g. a string, a safe_dom
    # Node or NodeList, or a jinja2.Markup).
    PAGE_HEADER_HOOKS = []

    # Isolate this class's actions list from its parents
    get_actions = []
    post_actions = []

    actions_to_menu_items = {}
    root_menu_group = menus.MenuGroup('admin', 'Global Admin')

    def format_title(self, text):
        return 'Course Builder > Admin > %s' % text

    @classmethod
    def make_menu(cls):
        cls.make_site_menu(cls.root_menu_group, placement=1000)
        dashboard.make_help_menu(cls.root_menu_group)

    @classmethod
    def disable(cls):
        super(GlobalAdminHandler, cls).disable()
        cls.root_menu_group.remove_all()
        cls.actions_to_menu_items = {}

    def get(self):
        action = self.request.get('action')

        if action:
            destination = '%s?action=%s' % (self.LINK_URL, action)
        else:
            destination = self.LINK_URL

        user = users.get_current_user()
        if not user:
            self.redirect(users.create_login_url(destination), normalize=False)
            return
        if not can_view_admin_action(action):
            if appengine_config.PRODUCTION_MODE:
                self.error(403)
            else:
                self.redirect(
                    users.create_login_url(destination), normalize=False)
            return

        # Force reload of properties. It's expensive, but admin deserves it!
        config.Registry.get_overrides(force_update=True)

        super(GlobalAdminHandler, self).get()

    def post(self):
        if not self.can_edit():
            self.redirect('/', normalize=False)
            return
        return super(GlobalAdminHandler, self).post()

    def get_template(self, template_name, dirs):
        """Sets up an environment and Gets jinja template."""
        dashboard_template_dir = os.path.join(
            appengine_config.BUNDLE_ROOT, 'modules', 'dashboard')
        return jinja_utils.get_template(
            template_name, dirs + [dashboard_template_dir], handler=self)

    def render_page(self, template_values, in_action=None):
        page_title = template_values['page_title']
        template_values['header_title'] = page_title
        template_values['page_headers'] = [
            hook(self) for hook in self.PAGE_HEADER_HOOKS]
        template_values['breadcrumbs'] = page_title

        current_action = (in_action or self.request.get('action')
            or self.default_action_for_current_permissions())
        current_menu_item = self.actions_to_menu_items.get(current_action)
        template_values['root_menu_group'] = self.root_menu_group
        template_values['current_menu_item'] = current_menu_item
        template_values['is_global_admin'] = True
        template_values['course_app_contexts'] = dashboard.get_visible_courses()

        template_values['gcb_course_base'] = '/'
        template_values['user_nav'] = safe_dom.NodeList().append(
            safe_dom.Text('%s | ' % users.get_current_user().email())
        ).append(
            safe_dom.Element(
                'a', href=users.create_logout_url(self.request.uri)
            ).add_text('Logout'))
        template_values[
            'page_footer'] = 'Page created on: %s' % datetime.datetime.now()
        template_values['coursebuilder_version'] = (
            os.environ['GCB_PRODUCT_VERSION'])
        template_values['application_id'] = app.get_application_id()
        template_values['application_version'] = (
            os.environ['CURRENT_VERSION_ID'])
        if not template_values.get('sections'):
            template_values['sections'] = []

        self.response.write(
            self.get_template('view.html', []).render(template_values))


def notify_module_enabled():
    AdminHandler.enable()
    GlobalAdminHandler.enable()


def notify_module_disabled():
    AdminHandler.disable()
    GlobalAdminHandler.disable()


custom_module = None


def register_module():
    """Registers this module in the registry."""

    global_handlers = [
        (GlobalAdminHandler.URL, GlobalAdminHandler),
        ('/admin/welcome', WelcomeHandler),
        ('/rest/config/item', (
            modules.admin.config.ConfigPropertyItemRESTHandler)),
        ('/rest/courses/item', modules.admin.config.CoursesItemRESTHandler),
        (os.path.join(RESOURCES_PATH, '.*'), tags.ResourcesHandler)]

    namespaced_handlers = [(AdminHandler.URL, AdminHandler)]

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Site admin',
        'A set of pages for Course Builder site administrator.',
        global_handlers, namespaced_handlers,
        notify_module_enabled=notify_module_enabled,
        notify_module_disabled=notify_module_disabled)
    return custom_module
