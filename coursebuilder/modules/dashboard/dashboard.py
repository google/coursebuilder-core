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

"""Classes and methods to create and manage Courses."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import collections
import datetime
import logging
import os
import urllib

import appengine_config
from filer import AssetItemRESTHandler
from filer import FileManagerAndEditor
from filer import FilesItemRESTHandler
from filer import TextAssetRESTHandler
from label_editor import LabelManagerAndEditor
from label_editor import LabelRestHandler
import messages
from question_editor import GiftQuestionRESTHandler
from question_editor import McQuestionRESTHandler
from question_editor import QuestionManagerAndEditor
from question_editor import SaQuestionRESTHandler
from question_group_editor import QuestionGroupManagerAndEditor
from question_group_editor import QuestionGroupRESTHandler
from role_editor import RoleManagerAndEditor
from role_editor import RoleRESTHandler
from unit_lesson_editor import AssessmentRESTHandler
from unit_lesson_editor import ImportCourseRESTHandler
from unit_lesson_editor import LessonRESTHandler
from unit_lesson_editor import LinkRESTHandler
from unit_lesson_editor import UnitLessonEditor
from unit_lesson_editor import UnitLessonTitleRESTHandler
from unit_lesson_editor import UnitRESTHandler

import utils as dashboard_utils

from common import crypto
from common import jinja_utils
from common import safe_dom
from common import tags
from common import users
from common.utils import Namespace
from controllers import sites
from controllers.utils import ApplicationHandler
from controllers.utils import CourseHandler
from controllers.utils import ReflectiveRequestHandler
from models import config
from models import courses
from models import custom_modules
from models import roles
from models.models import RoleDAO
from modules.dashboard import tabs
from modules.oeditor import oeditor

from google.appengine.api import app_identity

custom_module = None


class DashboardHandler(
    CourseHandler, FileManagerAndEditor,
    LabelManagerAndEditor, QuestionGroupManagerAndEditor,
    QuestionManagerAndEditor, ReflectiveRequestHandler, RoleManagerAndEditor,
    UnitLessonEditor):
    """Handles all pages and actions required for managing a course."""

    # This dictionary allows the dashboard module to optionally nominate a
    # specific sub-tab within each major tab group as the default sub-tab to
    # open when first navigating to that major tab.  The default may be
    # explicitly specified here so that sub-tab registrations from other
    # modules do not inadvertently take over the first position due to order
    # of module registration.
    default_subtab_action = collections.defaultdict(lambda: None)
    get_actions = [
        'edit_settings', 'edit_unit_lesson',
        'edit_unit', 'edit_link', 'edit_lesson', 'edit_assessment',
        'manage_asset', 'manage_text_asset', 'import_course',
        'add_mc_question', 'add_sa_question',
        'edit_question', 'add_question_group', 'edit_question_group',
        'add_label', 'edit_label', 'question_preview',
        'roles', 'add_role', 'edit_role', 'edit_custom_unit',
        'import_gift_questions', 'in_place_lesson_editor']
    # Requests to these handlers automatically go through an XSRF token check
    # that is implemented in ReflectiveRequestHandler.
    post_actions = [
        'create_or_edit_settings', 'add_unit',
        'add_link', 'add_assessment', 'add_lesson',
        'set_draft_status',
        'add_to_question_group',
        'clone_question', 'add_custom_unit']
    child_routes = [
            (AssessmentRESTHandler.URI, AssessmentRESTHandler),
            (AssetItemRESTHandler.URI, AssetItemRESTHandler),
            (FilesItemRESTHandler.URI, FilesItemRESTHandler),
            (ImportCourseRESTHandler.URI, ImportCourseRESTHandler),
            (LabelRestHandler.URI, LabelRestHandler),
            (LessonRESTHandler.URI, LessonRESTHandler),
            (LinkRESTHandler.URI, LinkRESTHandler),
            (UnitLessonTitleRESTHandler.URI, UnitLessonTitleRESTHandler),
            (UnitRESTHandler.URI, UnitRESTHandler),
            (McQuestionRESTHandler.URI, McQuestionRESTHandler),
            (GiftQuestionRESTHandler.URI, GiftQuestionRESTHandler),
            (SaQuestionRESTHandler.URI, SaQuestionRESTHandler),
            (TextAssetRESTHandler.URI, TextAssetRESTHandler),
            (QuestionGroupRESTHandler.URI, QuestionGroupRESTHandler),
            (RoleRESTHandler.URI, RoleRESTHandler)]

    # List of functions which are used to generate content displayed at the top
    # of every dashboard page. Use this with caution, as it is extremely
    # invasive of the UX. Each function receives the handler as arg and returns
    # an object to be inserted into a Jinja template (e.g. a string, a safe_dom
    # Node or NodeList, or a jinja2.Markup).
    PAGE_HEADER_HOOKS = []

    # A list of hrefs for extra CSS files to be included in dashboard pages.
    # Files listed here by URL will be available on every Dashboard page.
    EXTRA_CSS_HREF_LIST = []

    # A list of hrefs for extra JS files to be included in dashboard pages.
    # Files listed here by URL will be available on every Dashboard page.
    EXTRA_JS_HREF_LIST = []

    # Dictionary that maps external permissions to their descriptions
    _external_permissions = {}
    # Dictionary that maps actions to permissions
    _action_to_permission = {}

    _custom_nav_mappings = collections.OrderedDict()
    _custom_get_actions = {}
    _default_get_action = None
    _custom_post_actions = {}

    @classmethod
    def add_nav_mapping(cls, action, nav_title):
        """Add a Nav mapping for Dashboard."""
        cls._custom_nav_mappings[action] = nav_title

    @classmethod
    def get_nav_mappings(cls):
        return cls._custom_nav_mappings.items()

    @classmethod
    def get_nav_title(cls, action):
        if action in cls._custom_nav_mappings:
            return cls._custom_nav_mappings[action]
        return None

    @classmethod
    def add_custom_get_action(cls, action, handler=None, in_action=None,
                              overwrite=False, is_default=False):
        if not action:
            logging.critical('Action not specified. Ignoring.')
            return

        if is_default:
            if cls._default_get_action:
                raise ValueError(
                    'Cannnot make action "%s" the default - %s already is.' %
                    (action, cls._default_get_action))
            cls._default_get_action = action

        if not handler:
            tab_list = tabs.Registry.get_tab_group(action)
            if not tab_list:
                logging.critical('For action : ' + action +
                    ' handler can not be null.')
                return

        if ((action in cls._custom_get_actions or action in cls.get_actions)
            and not overwrite):
            logging.critical('action : ' + action +
                             ' already exists. Ignoring the custom get action.')
            return

        cls._custom_get_actions[action] = (handler, in_action)

    @classmethod
    def remove_custom_get_action(cls, action):
        if action in cls._custom_get_actions:
            cls._custom_get_actions.pop(action)

    @classmethod
    def add_custom_post_action(cls, action, handler, overwrite=False):
        if not handler or not action:
            logging.critical('Action or handler can not be null.')
            return

        if ((action in cls._custom_post_actions or action in cls.post_actions)
            and not overwrite):
            logging.critical('action : ' + action +
                             ' already exists. Ignoring the custom get action.')
            return

        cls._custom_post_actions[action] = handler

    @classmethod
    def remove_custom_post_action(cls, action):
        if action in cls._custom_post_actions:
            cls._custom_post_actions.pop(action)

    @classmethod
    def get_child_routes(cls):
        """Add child handlers for REST."""
        return cls.child_routes

    def can_view(self, action):
        """Checks if current user has viewing rights."""
        return roles.Roles.is_user_allowed(
            self.app_context, custom_module,
            self._action_to_permission.get('get_%s' % action, '')
        )

    def can_edit(self):
        """Checks if current user has editing rights."""
        return roles.Roles.is_course_admin(self.app_context)

    def get_default_tab_action(self):
        return self._default_get_action

    def _default_action_for_current_permissions(self):
        """Set the default or first active navigation tab as default action."""
        action = self.get_default_tab_action()
        if self.can_view(action):
            return action
        for nav in self.get_nav_mappings():
            if self.can_view(nav[0]):
                return nav[0]

        return ''

    def get(self):
        """Enforces rights to all GET operations."""
        action = self.request.get('action')
        if not action:
            self.default_action = self._default_action_for_current_permissions()
            action = self.default_action

        if not self.can_view(action):
            self.redirect(self.app_context.get_slug())
            return

        if action in self._custom_get_actions:
            return self._custom_get_handler(action)

        # Force reload of properties. It is expensive, but admin deserves it!
        config.Registry.get_overrides(force_update=True)
        return super(DashboardHandler, self).get()

    def post(self):
        """Enforces rights to all POST operations."""
        if not self.can_edit():
            self.redirect(self.app_context.get_slug())
            return
        action = self.request.get('action')
        if action in self._custom_post_actions:
            # Each POST request must have valid XSRF token.
            xsrf_token = self.request.get('xsrf_token')
            if not crypto.XsrfTokenManager.is_xsrf_token_valid(
                xsrf_token, action):
                self.error(403)
                return
            self.custom_post_handler()
            return

        return super(DashboardHandler, self).post()

    def get_template(self, template_name, dirs):
        """Sets up an environment and Gets jinja template."""
        return jinja_utils.get_template(
            template_name, dirs + [os.path.dirname(__file__)], handler=self)

    def get_alerts(self):
        alerts = []
        if not self.app_context.is_editable_fs():
            alerts.append('Read-only course.')
        if not self.app_context.now_available:
            alerts.append('The course is not publicly available.')
        return '\n'.join(alerts)

    def _get_top_nav(self, in_action, in_tab):
        current_action = in_action or self.request.get(
            'action') or self.default_action
        nav_bars = []
        nav = safe_dom.NodeList()
        for action, title in self.get_nav_mappings():
            if not self.can_view(action):
                continue
            class_name = 'selected' if action == current_action else ''
            action_href = 'dashboard?action=%s' % action
            nav.append(safe_dom.Element(
                'a', href=action_href, className=class_name).add_text(
                    title))

        if roles.Roles.is_super_admin():
            nav.append(safe_dom.Element(
                'a', href='admin?action=admin',
                className=('selected' if current_action == 'admin' else '')
            ).add_text('Site Admin'))

        nav.append(safe_dom.Element(
            'a',
            href='https://code.google.com/p/course-builder/wiki/Dashboard',
            target='_blank'
        ).add_text('Help'))

        nav.append(safe_dom.Element(
            'a',
            href=(
                'https://groups.google.com/forum/?fromgroups#!categories/'
                'course-builder-forum/general-troubleshooting'),
            target='_blank'
        ).add_text('Support'))
        nav_bars.append(nav)

        tab_group = tabs.Registry.get_tab_group(current_action)
        if tab_group:
            if current_action == 'assets':
                exclude_tabs = []
                course = self.get_course()
                if courses.has_only_new_style_assessments(course):
                    exclude_tabs.append('Assessments')
                if courses.has_only_new_style_activities(course):
                    exclude_tabs.append('Activities')
                    tab_group = [
                        t for t in tab_group if t.title not in exclude_tabs]
            tab_name = (in_tab or self.request.get('tab') or
                        self.default_subtab_action[current_action]
                        or tab_group[0].name)
            sub_nav = safe_dom.NodeList()
            for tab in tab_group:
                href = tab.href or 'dashboard?action=%s&tab=%s' % (
                        current_action, tab.name)
                target = tab.target or '_self'
                sub_nav.append(
                    safe_dom.A(
                        href,
                        className=('selected' if tab.name == tab_name else ''),
                        target=target)
                    .add_text(tab.title))
            nav_bars.append(sub_nav)
        return nav_bars

    def render_page(self, template_values, in_action=None, in_tab=None):
        """Renders a page using provided template values."""
        template_values['header_title'] = template_values['page_title']
        template_values['page_headers'] = [
            hook(self) for hook in self.PAGE_HEADER_HOOKS]
        template_values['course_picker'] = self.get_course_picker()
        template_values['course_title'] = self.app_context.get_title()
        template_values['top_nav'] = self._get_top_nav(in_action, in_tab)
        template_values['gcb_course_base'] = self.get_base_href(self)
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
        template_values['application_id'] = app_identity.get_application_id()
        template_values['application_version'] = (
            os.environ['CURRENT_VERSION_ID'])
        template_values['can_highlight_code'] = oeditor.CAN_HIGHLIGHT_CODE.value
        template_values['extra_css_href_list'] = self.EXTRA_CSS_HREF_LIST
        template_values['extra_js_href_list'] = self.EXTRA_JS_HREF_LIST
        if not template_values.get('sections'):
            template_values['sections'] = []

        self.response.write(
            self.get_template('view.html', []).render(template_values))

    def get_course_picker(self, destination=None):
        destination = destination or '/dashboard'
        action = self.request.get('action') or self._default_get_action

        # disable picker if we are on the well known page; we dont want picked
        # on pages where edits or creation of new object can get triggered
        safe_action = action and action in [
            a for a, _ in self.get_nav_mappings()] + ['admin']

        tab = self.request.get('tab')
        if action in self.get_actions:
            tab_group = tabs.Registry.get_tab_group(action)
            if tab_group and tab in tab_group:
                tab = '&tab=%s' % tab
            else:
                tab = ''
            destination = '%s?action=%s%s' % (destination, action, tab)

        current_course = sites.get_course_for_current_request()
        options = []
        for course in sorted(sites.get_all_courses()):
            with Namespace(course.namespace):
                if self.current_user_has_access(course):
                    url = (
                        course.canonicalize_url(destination) if safe_action
                        else 'javascript:void(0)')
                    title = '%s (%s)' % (course.get_title(), course.get_slug())
                    option = safe_dom.Element('li')
                    link = safe_dom.A(url).add_text(title)
                    if current_course == course:
                        link.set_attribute('class', 'selected')
                    option.add_child(link)
                    options.append((course.get_title(), option))

        picker_class_name = 'hidden'
        if not safe_action:
            picker_class_name += ' disabled'

        picker = safe_dom.Element(
            'ol', id='gcb-course-picker-menu', className=picker_class_name)

        for title, option in sorted(
            options, key=lambda item: item[0].lower()):
            picker.append(option)
        return picker

    def format_title(self, text):
        """Formats standard title with or without course picker."""
        ret = safe_dom.NodeList()
        cb_text = 'Course Builder '
        ret.append(safe_dom.Text(cb_text))
        ret.append(safe_dom.Entity('&gt;'))
        ret.append(safe_dom.Text(' %s ' % self.app_context.get_title()))
        ret.append(safe_dom.Entity('&gt;'))
        dashboard_text = ' Dashboard '
        ret.append(safe_dom.Text(dashboard_text))
        ret.append(safe_dom.Entity('&gt;'))
        ret.append(safe_dom.Text(' %s' % text))
        return ret

    def get_question_preview(self):
        template_values = {}
        template_values['gcb_course_base'] = self.get_base_href(self)
        template_values['question'] = tags.html_to_safe_dom(
            '<question quid="%s">' % self.request.get('quid'), self)
        self.response.write(self.get_template(
            'question_preview.html', []).render(template_values))

    def _custom_get_handler(self, action):
        """Renders Enabled Custom Units view."""
        in_action = self._custom_get_actions[action][1]
        tab = tabs.Registry.get_tab(action, self.request.get('tab'))
        if not tab:
            tab_list = tabs.Registry.get_tab_group(action)
            if not tab_list:
                self._custom_get_actions[action][0](self)
                return
            tab = tab_list[0]

        template_values = {
            'page_title': self.format_title(
                '%s > %s' % (action.title(), tab.title)),
            }

        tab_result = tab.contents(self)
        if isinstance(tab_result, dict):
            template_values.update(tab_result)
        else:
            template_values['main_content'] = tab_result

        self.render_page(template_values, in_action=in_action)

    def custom_post_handler(self):
        """Edit Custom Unit Settings view."""
        action = self.request.get('action')
        self._custom_post_actions[action](self)

    def get_action_url(self, action, key=None, extra_args=None, fragment=None):
        args = {'action': action}
        if key:
            args['key'] = key
        if extra_args:
            args.update(extra_args)
        url = '/dashboard?%s' % urllib.urlencode(args)
        if fragment:
            url += '#' + fragment
        return self.canonicalize_url(url)

    def _render_roles_list(self):
        """Render roles list to HTML."""
        all_roles = RoleDAO.get_all()
        if all_roles:
            output = safe_dom.Element('ul')
            for role in sorted(all_roles, key=lambda r: r.name):
                li = safe_dom.Element('li')
                output.add_child(li)
                li.add_text(role.name).add_child(
                    dashboard_utils.create_edit_button(
                    'dashboard?action=edit_role&key=%s' % (role.id)
                ))
        else:
            output = safe_dom.Element('blockquote').add_text('< none >')

        return output

    def get_roles(self):
        """Renders course roles view."""
        actions = [{
            'id': 'add_role',
            'caption': 'Add Role',
            'href': self.get_action_url('add_role')}]
        sections = [{
                'title': 'Roles',
                'description': messages.ROLES_DESCRIPTION,
                'actions': actions,
                'pre': self._render_roles_list()
        }]
        template_values = {
            'page_title': self.format_title('Roles'),
            'sections': sections,
        }
        self.render_page(template_values)

    @classmethod
    def map_action_to_permission(cls, action, permission):
        """Maps an action to a permission.

        Map a GET or POST action that goes through the dashboard to a
        permission to control which users have access. GET actions start with
        'get_' while post actions start with 'post_'.

        Example:
            The i18n module maps both the actions 'get_i18n_dashboard' and
            'get_i18_console' to the permission 'access_i18n_dashboard'.
            Users who have a role assigned with this permission are then allowed
            to perform these actions and thus access the translation tools.

        Args:
            action: a string specifying the action to map.
            permission: a string specifying to which permission the action maps.
        """
        cls._action_to_permission[action] = permission

    @classmethod
    def unmap_action_to_permission(cls, action):
        del cls._action_to_permission[action]

    @classmethod
    def add_external_permission(cls, permission_name, permission_description):
        """Adds extra permissions that will be registered by the Dashboard."""
        cls._external_permissions[permission_name] = permission_description

    @classmethod
    def remove_external_permission(cls, permission_name):
        del cls._external_permissions[permission_name]

    @classmethod
    def permissions_callback(cls, unused_app_context):
        return cls._external_permissions.iteritems()

    @classmethod
    def current_user_has_access(cls, app_context):
        for action, _ in cls.get_nav_mappings():
            if roles.Roles.is_user_allowed(
                app_context, custom_module,
                cls._action_to_permission.get('get_%s' % action, '')
            ):
                return True
        return False

    @classmethod
    def generate_dashboard_link(cls, app_context):
        if cls.current_user_has_access(app_context):
            return [('dashboard', 'Dashboard')]
        return []


def register_module():
    """Registers this module in the registry."""

    def on_module_enabled():
        roles.Roles.register_permissions(
            custom_module, DashboardHandler.permissions_callback)
        ApplicationHandler.RIGHT_LINKS.append(
            DashboardHandler.generate_dashboard_link)
        DashboardHandler.add_nav_mapping('roles', 'Roles')
        DashboardHandler.add_nav_mapping('settings', 'Settings')
        DashboardHandler.add_custom_get_action('settings')

    global_routes = [
        (
            dashboard_utils.RESOURCES_PATH +'/material-design-icons/(.*)',
            sites.make_zip_handler(os.path.join(
                appengine_config.BUNDLE_ROOT, 'lib',
                'material-design-iconic-font-1.1.1.zip'))),
        (dashboard_utils.RESOURCES_PATH +'/js/.*', tags.JQueryHandler),
        (dashboard_utils.RESOURCES_PATH + '/.*', tags.ResourcesHandler)]

    dashboard_handlers = [
        ('/dashboard', DashboardHandler),
    ]
    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Course Dashboard',
        'A set of pages for managing Course Builder course.',
        global_routes, dashboard_handlers,
        notify_module_enabled=on_module_enabled)
    return custom_module
