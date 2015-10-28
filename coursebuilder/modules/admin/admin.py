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
import uuid

import appengine_config
from common import crypto
from common import jinja_utils
from common import safe_dom
from common import tags
from common import users
from common import utils as common_utils
from controllers import sites
from controllers.utils import ApplicationHandler
from controllers.utils import ReflectiveRequestHandler
from models import config
from models import counters
from models import courses
from models import custom_modules
from models import entities
from models import roles
from models.config import ConfigProperty
import modules.admin.config
from modules.admin.config import ConfigPropertyEditor
from modules.admin.config import CourseDeleteHandler
from modules.dashboard import dashboard
from modules.dashboard import utils as dashboard_utils
from common import menus

import google.appengine.api.app_identity as app
from google.appengine.ext import db

TEMPLATE_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'admin', 'templates')

DIRECT_CODE_EXECUTION_UI_ENABLED = False
GLOBAL_SITE_SETTINGS_LINK_ENABLED = False

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

    # Enable other modules to put global warnings on the welcome page.  This
    # is useful when you want to ask for permission from the installation
    # administrator, and you want to be absolutely certain the administrator
    # has seen the request.  Items appended here must be callable, taking
    # no parameters.  The return value will be inserted onto the welcome.html
    # page; see the loop adding 'item_form_content' to the page.
    WELCOME_FORM_HOOKS = []

    # Items on this list are called back when the welcome page has been
    # submitted.  These should receive the page handler object as an argument.
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
        common_utils.run_hooks(self.POST_HOOKS, self)
        self.redirect('/modules/admin')

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
        welcome_form_content = []
        for hook in self.WELCOME_FORM_HOOKS:
            welcome_form_content.append(hook())
        template_values['welcome_form_content'] = welcome_form_content
        if not appengine_config.PRODUCTION_MODE:
            template_values['page_uuid'] = str(uuid.uuid1())
        self.response.write(
            self.get_template('welcome.html').render(template_values))


def can_view_admin_action(action):
    if action == 'add_course':
        return modules.admin.config.CoursesPropertyRights.can_add()
    if action in ['console', 'console_run']:
        if not DIRECT_CODE_EXECUTION_UI_ENABLED:
            return False
    if action in ['deployment']:
        # Visibility for this action is enforced in the dashboard.
        # Additional elements are hidden by the action handler
        return dashboard.DashboardHandler.can_view(action)
    return roles.Roles.is_super_admin()


def admin_action_can_view(action):
    def can_view(app_context):
        return can_view_admin_action(action)
    return can_view


class BaseAdminHandler(ConfigPropertyEditor):
    """Base class holding methods required for administration of site."""

    # The URL used in relative addresses of this handler
    LINK_URL = 'admin'

    default_action = 'courses'
    get_actions = ['courses', 'config_edit', 'settings', 'deployment',
        'console']
    post_actions = ['config_override', 'config_reset', 'console_run']

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
    def install_courses_menu_item(cls):
        menu_item = menus.MenuItem(
            'courses', 'Courses', action='courses',
            can_view=admin_action_can_view('courses'),
            href="{}?action=courses".format(cls.LINK_URL))

        dashboard.DashboardHandler.register_courses_menu_item(menu_item)

    @classmethod
    def install_menu(cls):

        def bind(group_name, item_name, label, action=None, can_view=None,
                contents=None, href=None, **kwargs):
            if href:
                target = '_blank'
            else:
                target = None
                href = "{}?action={}".format(cls.LINK_URL, action)

            def combined_can_view(app_context):
                if can_view and not can_view(app_context):
                    return False

                if action:
                    return can_view_admin_action(action)

                return True

            no_app_context = True

            # The Site settings page can be used in the global admin (no app
            # context) and in fact it is still reachable by guessing its URL,
            # since many tests depend on its existence. However, product has
            # requested that it appear greyed out in the global admin so that
            # only Courses and Help are available there.
            if action == 'settings' and not GLOBAL_SITE_SETTINGS_LINK_ENABLED:
                no_app_context = False

            dashboard.DashboardHandler.add_sub_nav_mapping(
                group_name, item_name, label, action=action,
                can_view=combined_can_view, contents=contents, href=href,
                no_app_context=no_app_context, target=target, **kwargs)

        cls.install_courses_menu_item()

        bind('settings', 'site', 'Advanced site settings', action='settings',
            contents=cls.get_settings, sub_group_name='advanced')

        bind('help', 'welcome', 'Welcome', action='welcome',
            href='/admin/welcome', is_external=True, placement=1000)

        bind('help', 'deployment', 'About', action='deployment',
            contents=cls.get_deployment,
            sub_group_name='advanced')

        bind('analytics', 'console', 'Console', action='console',
            contents=cls.get_console, sub_group_name='advanced')

        def can_view_appstats(app_context):
            return appengine_config.gcb_appstats_enabled()

        bind('analytics', 'stats', 'Appstats', can_view=can_view_appstats,
            href='/admin/stats/', sub_group_name='advanced')

    @classmethod
    def can_view(cls, action):
        """Checks if current user has viewing rights."""
        # Overrides method in DashboardHandler
        return can_view_admin_action(action)

    @classmethod
    def can_edit(cls, action):
        """Checks if current user has editing rights."""
        return cls.can_view(action)

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

    def _render_perf(self):
        """Shows server performance counters page."""
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
        return self.render_dict(
            perf_counters, 'In-process Performance Counters (local/global)')

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

    def _render_modules(self):
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
        return module_content

    def _render_custom_tags(self):
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
        return tag_content

    def _render_yamls(self):
        yaml_content = safe_dom.NodeList()
        for _yaml in ['app.yaml', 'custom.yaml', 'static.yaml']:
            yaml_content.append(
                safe_dom.Element('h3').add_text('Contents of ').add_child(
                    safe_dom.Element('code').add_text(_yaml)))
            ol = safe_dom.Element('ol')
            yaml_content.append(ol)
            pre = safe_dom.Element('pre')
            ol.append(pre)
            yaml_lines = open(os.path.join(os.path.dirname(
                __file__), '../../%s' % _yaml), 'r').readlines()
            for line in yaml_lines:
                pre.add_text(line)
        return yaml_content

    def _render_db_entity_types(self):
        entity_content = safe_dom.NodeList()
        entity_content.append(
            safe_dom.Element('h3').add_text('Database Entities'))
        entity_content.append(self._describe_db_types())
        entity_content.append(safe_dom.Element('p'))
        return entity_content

    def _render_application_identity(self):
        # Application identity and users service information.
        app_id = app.get_application_id()
        app_dict = {}
        app_dict['application_id'] = escape(app_id)
        app_dict['default_ver_hostname'] = escape(
            app.get_default_version_hostname())
        app_dict['users_service_name'] = escape(
            users.UsersServiceManager.get().get_service_name())
        return self.render_dict(app_dict, 'About the Application')

    def _render_sys_path(self):
        # sys.path information.
        sys_path_content = safe_dom.NodeList()
        sys_path_content.append(
            safe_dom.Element('h3').add_text('sys.path')
        )
        ol = safe_dom.Element('ol')
        sys_path_content.append(ol)
        for path in sys.path:
            ol.add_child(safe_dom.Element('li').add_text(path))
        return sys_path_content

    def get_deployment(self):
        """Shows server environment and deployment information page."""
        template_values = {}
        template_values['page_title'] = self.format_title('Deployment')
        template_values['main_content'] = content = safe_dom.NodeList()

        if roles.Roles.is_super_admin():
            content.append(
                self._render_application_identity()
            )

        content.append(self._render_about_courses())

        if roles.Roles.is_super_admin():
            content.append(
                self._render_modules()
            ).append(
                self._render_db_entity_types()
            ).append(
                self._render_custom_tags()
            ).append(
                self._render_yamls()
            ).append(
                self.render_dict(os.environ, 'Server Environment Variables')
            ).append(
                self._render_sys_path()
            ).append(
                self._render_perf()
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

    def _render_about_courses(self):
        courses_list = (
            courses.Course(None, app_context=app_context)
            for app_context in dashboard.get_visible_courses())

        def list_files(app_context):
            return dashboard_utils.list_files(app_context, '/data/')

        def get_filesystem_type(app_context):
            return app_context.fs.impl.__class__.__name__

        def get_home_folder(app_context):
            return sites.abspath(app_context.get_home_folder(), '/')

        return safe_dom.Template(
            self.get_template('course_infos.html'), courses=courses_list,
            get_filesystem_type=get_filesystem_type,
            get_home_folder=get_home_folder, list_files=list_files)

    def get_settings(self):
        """Shows configuration properties information page."""
        template_values = {}
        template_values['page_title'] = self.format_title('Settings')

        content = safe_dom.NodeList()
        content.append(safe_dom.Element(
            'link', rel='stylesheet',
            href='/modules/admin/_static/css/admin.css'))
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
            if item.deprecated:
                continue

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
                For each setting, the value shown corresponds to, in descending
                order of priority:
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
                Default values that are blank are indicated by angle brackets
                and the word "none" (<none>). Other default values that are
                descriptive in nature are represented with the angle brackets
                and the description within them.
            """))

        template_values['main_content'] = content
        self.render_page(template_values)

    def get_courses(self):
        """Shows a list of all courses available on this site."""

        if hasattr(self, 'app_context'):
            this_namespace = self.app_context.get_namespace_name()
        else:
            this_namespace = None  # GlobalAdminHandler

        all_courses = []
        for course in sorted(sites.get_all_courses(),
                             key=lambda course: course.get_title().lower()):
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

            is_selected_course = (course.get_namespace_name() == this_namespace)

            all_courses.append({
                'link': link,
                'name': name,
                'slug': slug,
                'is_selected_course': is_selected_course,
                'now_available': course.now_available
                })

        delete_course_xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            CourseDeleteHandler.XSRF_ACTION)
        add_course_xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
                modules.admin.config.CoursesItemRESTHandler.XSRF_ACTION)
        template_values = {
            'page_title': self.format_title('Courses'),
            'main_content': self.render_template_to_html(
                {
                    'add_course_link': '%s?action=add_course' % self.LINK_URL,
                    'delete_course_link': CourseDeleteHandler.URI,
                    'delete_course_xsrf_token': delete_course_xsrf_token,
                    'add_course_xsrf_token':add_course_xsrf_token,
                    'courses': all_courses,
                    'email': users.get_current_user().email(),
                },
                'courses.html', [TEMPLATE_DIR]
            )
        }
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

    def default_action_for_current_permissions(self):
        """Set the default or first active navigation tab as default action."""
        return 'courses'


class AdminHandler(BaseAdminHandler, dashboard.DashboardHandler):
    """Handler to present admin settings in namespaced context."""

    # The binding URL for this handler
    URL = '/admin'

    def format_title(self, text):
        return super(AdminHandler, self).format_title(
            'Admin > %s' % text)

    def get_template(self, template_name, dirs=None):
        return super(AdminHandler, self).get_template(
            template_name, [TEMPLATE_DIR] + (dirs or []))

    def get_course_picker(self, destination=None, in_action=None):
        return super(AdminHandler, self).get_course_picker(
            destination='/admin', in_action=in_action)


class GlobalAdminHandler(
        BaseAdminHandler, ApplicationHandler, ReflectiveRequestHandler):
    """Handler to present admin settings in global context."""

    # The binding URL for this handler
    BASE_URL = '/modules/'
    URL = BASE_URL + BaseAdminHandler.LINK_URL

    # List of functions which are used to generate content displayed at the top
    # of every dashboard page. Use this with caution, as it is extremely
    # invasive of the UX. Each function receives the handler as arg and returns
    # an object to be inserted into a Jinja template (e.g. a string, a safe_dom
    # Node or NodeList, or a jinja2.Markup).
    PAGE_HEADER_HOOKS = []

    default_action = 'courses'

    actions_to_menu_items = dashboard.DashboardHandler.actions_to_menu_items
    root_menu_group = dashboard.DashboardHandler.root_menu_group

    def format_title(self, text):
        return 'Course Builder > Admin > %s' % text

    @classmethod
    def disable(cls):
        super(GlobalAdminHandler, cls).disable()

    def get(self):
        action = self.request.get('action')

        if action:
            destination = '%s?action=%s' % (self.URL, action)
        else:
            destination = self.URL

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
        if not self.can_edit(self.request.get('action')):
            self.redirect('/', normalize=False)
            return
        return super(GlobalAdminHandler, self).post()

    def get_template(self, template_name, dirs=None):
        """Sets up an environment and Gets jinja template."""
        return jinja_utils.get_template(
            template_name, (dirs or []) + [dashboard.TEMPLATE_DIR],
            handler=self)

    def render_page(self, template_values, in_action=None):
        page_title = template_values['page_title']
        template_values['header_title'] = page_title
        template_values['page_headers'] = [
            hook(self) for hook in self.PAGE_HEADER_HOOKS]
        template_values['breadcrumbs'] = page_title

        # menu
        current_action = (in_action or self.request.get('action')
            or self.default_action_for_current_permissions())
        template_values['current_menu_item'] = self.actions_to_menu_items\
            .get(current_action)
        template_values['courses_menu_item'] = self.actions_to_menu_items.get(
            'courses')
        template_values['root_menu_group'] = self.root_menu_group

        template_values['course_app_contexts'] = dashboard.get_visible_courses()
        template_values['gcb_course_base'] = self.BASE_URL
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
        if not appengine_config.PRODUCTION_MODE:
            template_values['page_uuid'] = str(uuid.uuid1())

        self.response.write(
            self.get_template('view.html').render(template_values))

    def get_course(self):
        return None


def notify_module_enabled():
    # The same menu is shared between its subclasses
    BaseAdminHandler.install_menu()


custom_module = None


def register_module():
    """Registers this module in the registry."""

    global_handlers = [
        (GlobalAdminHandler.URL, GlobalAdminHandler),
        ('/admin/welcome', WelcomeHandler),
        ('/rest/config/item', (
            modules.admin.config.ConfigPropertyItemRESTHandler)),
        ('/rest/courses/item', modules.admin.config.CoursesItemRESTHandler)]

    namespaced_handlers = [(AdminHandler.URL, AdminHandler),
                           (CourseDeleteHandler.URI, CourseDeleteHandler)]

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Site admin',
        'A set of pages for Course Builder site administrator.',
        global_handlers, namespaced_handlers,
        notify_module_enabled=notify_module_enabled)
    return custom_module
