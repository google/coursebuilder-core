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
from models import custom_modules
from models import roles
from models.models import RoleDAO
from common import menus

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
        'add_role', 'edit_role', 'edit_custom_unit',
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

    # A list of template locations to be included in dashboard pages
    ADDITIONAL_DIRS = []

    # Dictionary that maps external permissions to their descriptions
    _external_permissions = {}
    # Dictionary that maps actions to permissions
    _action_to_permission = {}

    default_action = None
    _custom_get_actions = {}
    _custom_post_actions = {}

    # Create top level menu groups which other modules can register against.
    # I would do this in "register", but other modules register first.
    actions_to_menu_items = {}
    root_menu_group = menus.MenuGroup('dashboard', 'Dashboard')

    @classmethod
    def add_nav_mapping(cls, name, title, **kwargs):
        """Create a top level nav item."""
        group = cls.root_menu_group.get_child(name)
        if group is None:
            menu_cls = menus.MenuItem if kwargs.get('href') else menus.MenuGroup
            menu_cls(name, title, group=cls.root_menu_group, **kwargs)

    @classmethod
    def get_nav_title(cls, action):
        item = cls.actions_to_menu_items.get(action)
        if item:
            return item.group.title + " > " + item.title
        else:
            return None

    @classmethod
    def has_action_permission(cls, app_context, action):
        return roles.Roles.is_user_allowed(
            app_context, custom_module,
            cls._action_to_permission.get('get_%s' % action, ''))

    @classmethod
    def add_sub_nav_mapping(
            cls, group_name, item_name, title, action=None, contents=None,
            can_view=None, href=None, **kwargs):
        """Create a second level nav item.

        Args:
            group_name: Name of an existing top level nav item to use as the
                parent
            item_name: A unique key for this item
            title: Human-readable label
            action: A unique operation ID for
            contents: A handler which will be added as a custom get-action on
                DashboardHandler

        """

        group = cls.root_menu_group.get_child(group_name)
        if group is None:
            logging.critical('The group %s does not exist', group_name)
            return

        item = group.get_child(item_name)
        if item:
            logging.critical(
                'There is already a sub-menu item named "%s" registered in '
                'group %s.', item_name, group_name)
            return

        if contents:
            action = action or group_name + '_' + item_name

        if action and not href:
            href = "dashboard?action={}".format(action)

        def combined_can_view(app_context):
            if action and not cls.has_action_permission(
                    app_context, action):
                return False

            if can_view and not can_view(app_context):
                return False

            return True

        item = menus.MenuItem(
            item_name, title, action=action, group=group,
            can_view=combined_can_view, href=href, **kwargs)
        cls.actions_to_menu_items[action] = item

        if contents:
            cls.add_custom_get_action(action, handler=contents)

    @classmethod
    def add_custom_get_action(cls, action, handler=None, in_action=None,
                              overwrite=False):
        if not action:
            logging.critical('Action not specified. Ignoring.')
            return

        if not handler:
            logging.critical(
                'For action : %s handler can not be null.', action)
            return

        if ((action in cls._custom_get_actions or action in cls.get_actions)
            and not overwrite):
            logging.critical(
                'action : %s already exists. Ignoring the custom get action.',
                action)
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
            logging.critical(
                'action : %s already exists. Ignoring the custom get action.',
                action)
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
        return self.has_action_permission(self.app_context, action)

    def can_edit(self):
        """Checks if current user has editing rights."""
        return roles.Roles.is_course_admin(self.app_context)

    def default_action_for_current_permissions(self):
        """Set the default or first active navigation tab as default action."""
        item = self.root_menu_group.first_visible_item(self.app_context)
        if item:
            return item.action

    def get(self):
        """Enforces rights to all GET operations."""
        action = self.request.get('action')
        if not action:
            self.default_action = self.default_action_for_current_permissions()
            action = self.default_action

        if not self.can_view(action):
            self.redirect(self.app_context.get_slug())
            return

        if action in self._custom_get_actions:
            result = self._custom_get_actions[action][0](self)
            if result is None:
                return

            # The following code handles pages for actions that do not write out
            # their responses.

            template_values = {
                'page_title': self.format_title(self.get_nav_title(action)),
            }
            if isinstance(result, dict):
                template_values.update(result)
            else:
                template_values['main_content'] = result

            self.render_page(template_values)
            return


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

    def render_page(self, template_values, in_action=None):
        """Renders a page using provided template values."""
        template_values['header_title'] = template_values['page_title']
        template_values['page_headers'] = [
            hook(self) for hook in self.PAGE_HEADER_HOOKS]
        template_values['course_title'] = self.app_context.get_title()

        current_action = (in_action or self.request.get('action')
            or self.default_action_for_current_permissions())
        current_menu_item = self.actions_to_menu_items.get(current_action)
        template_values['root_menu_group'] = self.root_menu_group
        template_values['current_menu_item'] = current_menu_item
        template_values['app_context'] = self.app_context
        template_values['course_app_contexts'] = get_visible_courses()
        template_values['current_course'] = self.get_course()

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
        template_values['extra_css_href_list'] = self.EXTRA_CSS_HREF_LIST
        template_values['extra_js_href_list'] = self.EXTRA_JS_HREF_LIST
        if not template_values.get('sections'):
            template_values['sections'] = []

        self.response.write(
            self.get_template('view.html', []).render(template_values))

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
            output = safe_dom.Element('div', className='gcb-message').add_text(
                '< none >')

        return output

    def _render_roles_view(self):
        """Renders course roles view."""
        actions = [{
            'id': 'add_role',
            'caption': 'Add Role',
            'href': self.get_action_url('add_role')}]
        sections = [{
                'description': messages.ROLES_DESCRIPTION,
                'actions': actions,
                'pre': self._render_roles_list()
        }]
        template_values = {
            'page_title': self.format_title('Roles'),
            'sections': sections,
        }
        return template_values

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
        return cls.root_menu_group.can_view(app_context, exclude_links=True)

    @classmethod
    def generate_dashboard_link(cls, app_context):
        if cls.current_user_has_access(app_context):
            return [('dashboard', 'Dashboard')]
        return []


def make_help_menu(root_group):
    anyone_can_view = lambda x: True

    group = menus.MenuGroup('help', 'Help', group=root_group, placement=6000)

    menus.MenuItem(
        'documentation', 'Documentation',
        href='https://www.google.com/edu/openonline/tech/index.html',
        can_view=anyone_can_view, group=group, placement=1000, target='_blank')

    menus.MenuItem(
        'videos', 'Demo videos',
        href='https://www.youtube.com/playlist?list=PLFB_aGY5EfxeltJfJZwkjqDLAW'
        'dMfSpES',
        can_view=anyone_can_view, group=group, placement=2000, target='_blank')

    menus.MenuItem(
        'showcase', 'Showcase courses',
        href='https://www.google.com/edu/openonline/index.html',
        can_view=anyone_can_view, group=group, placement=3000, target='_blank')

    menus.MenuItem(
        'forum', 'Support forum',
        href=(
            'https://groups.google.com/forum/?fromgroups#!categories/'
            'course-builder-forum/general-troubleshooting'),
        can_view=anyone_can_view, group=group, placement=4000, target='_blank')


def get_visible_courses():
    result = []
    for app_context in sorted(sites.get_all_courses()):
        with Namespace(app_context.namespace):
            if DashboardHandler.current_user_has_access(app_context):
                result.append(app_context)
    return result


def register_module():
    """Registers this module in the registry."""

    DashboardHandler.add_nav_mapping('edit', 'Create', placement=1000)
    DashboardHandler.add_nav_mapping('style', 'Style', placement=2000)
    DashboardHandler.add_nav_mapping('publish', 'Publish', placement=3000)
    DashboardHandler.add_nav_mapping('analytics', 'Manage', placement=4000)
    DashboardHandler.add_nav_mapping('settings', 'Settings', placement=5000)

    make_help_menu(DashboardHandler.root_menu_group)

    # pylint: disable=protected-access
    DashboardHandler.add_sub_nav_mapping(
        'edit', 'roles', 'Roles', action='edit_roles',
        contents=DashboardHandler._render_roles_view, placement=8000)
    # pylint: enable=protected-access

    def on_module_enabled():
        roles.Roles.register_permissions(
            custom_module, DashboardHandler.permissions_callback)
        ApplicationHandler.RIGHT_LINKS.append(
            DashboardHandler.generate_dashboard_link)

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
