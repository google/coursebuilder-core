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
import uuid

import appengine_config
from filer import AssetItemRESTHandler
from filer import FileManagerAndEditor
from filer import FilesItemRESTHandler
from filer import TextAssetRESTHandler
from label_editor import LabelManagerAndEditor, TrackManagerAndEditor
from label_editor import LabelRestHandler, TrackRestHandler
import messages
from question_editor import GeneralQuestionRESTHandler
from question_editor import GiftQuestionRESTHandler
from question_editor import McQuestionRESTHandler
from question_editor import QuestionManagerAndEditor
from question_editor import SaQuestionRESTHandler
from question_group_editor import QuestionGroupManagerAndEditor
from question_group_editor import QuestionGroupRESTHandler
from role_editor import RoleManagerAndEditor
from role_editor import RoleRESTHandler

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
from models import services
from models.models import RoleDAO
from common import menus

from google.appengine.api import app_identity

custom_module = None

TEMPLATE_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'dashboard', 'templates')


class DashboardHandler(
    CourseHandler, FileManagerAndEditor,
    LabelManagerAndEditor, TrackManagerAndEditor, QuestionGroupManagerAndEditor,
    QuestionManagerAndEditor, ReflectiveRequestHandler, RoleManagerAndEditor):
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
        'manage_asset', 'manage_text_asset',
        'add_mc_question', 'add_sa_question',
        'edit_question', 'add_question_group', 'edit_question_group',
        'question_preview', 'question_group_preview',
        'add_label', 'edit_label', 'add_track', 'edit_track',
        'add_role', 'edit_role',
        'import_gift_questions']
    # Requests to these handlers automatically go through an XSRF token check
    # that is implemented in ReflectiveRequestHandler.
    post_actions = [
        'create_or_edit_settings',
        'add_to_question_group',
        'clone_question']
    child_routes = [
            (AssetItemRESTHandler.URI, AssetItemRESTHandler),
            (FilesItemRESTHandler.URI, FilesItemRESTHandler),
            (LabelRestHandler.URI, LabelRestHandler),
            (TrackRestHandler.URI, TrackRestHandler),
            (McQuestionRESTHandler.URI, McQuestionRESTHandler),
            (GiftQuestionRESTHandler.URI, GiftQuestionRESTHandler),
            (SaQuestionRESTHandler.URI, SaQuestionRESTHandler),
            (GeneralQuestionRESTHandler.URI, GeneralQuestionRESTHandler),
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
    _get_action_to_permission = {}
    _post_action_to_permission = {}

    default_action = None
    GetAction = collections.namedtuple('GetAction', ['handler', 'in_action'])
    _custom_get_actions = {}  # Map of name to GetAction
    _custom_post_actions = {}  # Map of name to handler callback.

    # Create top level menu groups which other modules can register against.
    # I would do this in "register", but other modules register first.
    actions_to_menu_items = {}
    root_menu_group = menus.MenuGroup('dashboard', 'Dashboard')

    @classmethod
    def add_nav_mapping(cls, name, title, **kwargs):
        """Create a top level nav item."""
        menu_item = cls.root_menu_group.get_child(name)
        if menu_item is None:
            is_link = kwargs.get('href')
            menu_cls = menus.MenuItem if is_link else menus.MenuGroup
            menu_item = menu_cls(
                name, title, group=cls.root_menu_group, **kwargs)
            if not is_link:
                # create the basic buckets
                pinned = menus.MenuGroup(
                    'pinned', None, placement=1000, group=menu_item)
                default = menus.MenuGroup(
                    'default', None, placement=2000, group=menu_item)
                advanced = menus.MenuGroup(
                    'advanced', None,
                    placement=menus.MenuGroup.DEFAULT_PLACEMENT * 2,
                    group=menu_item)
        return menu_item

    @classmethod
    def get_nav_title(cls, action):
        item = cls.actions_to_menu_items.get(action)
        if item:
            return item.group.group.title + " > " + item.title
        else:
            return None

    @classmethod
    def add_sub_nav_mapping(
            cls, group_name, item_name, title, action=None, contents=None,
            can_view=None, href=None, no_app_context=False,
            sub_group_name=None, **kwargs):
        """Create a second level nav item.

        Args:
            group_name: Name of an existing top level nav item to use as the
                parent
            item_name: A unique key for this item
            title: Human-readable label
            action: A unique operation ID for
            contents: A handler which will be added as a custom get-action on
                DashboardHandler
            can_view: Pass a boolean function here if your handler has
                additional permissions logic in it that the dashboard does not
                check for you.  You must additionally check it in your handler.
            sub_group_name: The sub groups 'pinned', 'default', and 'advanced'
                exist in that order and 'default' is used by default.  You can
                pass some other string to create a new group at the end.
            other arguments: see common/menus.py
        """

        group = cls.root_menu_group.get_child(group_name)
        if group is None:
            logging.critical('The group %s does not exist', group_name)
            return

        if sub_group_name is None:
            sub_group_name = 'default'

        sub_group = group.get_child(sub_group_name)
        if not sub_group:
            sub_group = menus.MenuGroup(
                sub_group_name, None, group=group)

        item = sub_group.get_child(item_name)
        if item:
            logging.critical(
                'There is already a sub-menu item named "%s" registered in '
                'group %s subgroup %s.', item_name, group_name, sub_group_name)
            return

        if contents:
            action = action or group_name + '_' + item_name

        if action and not href:
            href = "dashboard?action={}".format(action)

        def combined_can_view(app_context):
            if action:
                # Current design disallows actions at the global level.
                # This might change in the future.
                if not app_context and not no_app_context:
                    return False

                # Check permissions in the dashboard
                if not cls.can_view(action):
                    return False

            # Additional custom visibility check
            if can_view and not can_view(app_context):
                return False

            return True

        item = menus.MenuItem(
            item_name, title, action=action, group=sub_group,
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

        cls._custom_get_actions[action] = cls.GetAction(handler, in_action)

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
                'action : %s already exists. Ignoring the custom post action.',
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

    @classmethod
    def can_view(cls, action):
        """Checks if current user has viewing rights."""
        app_context = sites.get_app_context_for_current_request()
        if action in cls._get_action_to_permission:
            return cls._get_action_to_permission[action](app_context)
        return roles.Roles.is_course_admin(app_context)

    @classmethod
    def can_edit(cls, action):
        """Checks if current user has editing rights."""
        app_context = sites.get_app_context_for_current_request()
        if action in cls._post_action_to_permission:
            return cls._post_action_to_permission[action](app_context)
        return roles.Roles.is_course_admin(app_context)

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
        self.action = action

        if not self.can_view(action):
            self.redirect(self.app_context.get_slug())
            return

        if action in self._custom_get_actions:
            result = self._custom_get_actions[action].handler(self)
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
        action = self.request.get('action')
        self.action = action
        if not self.can_edit(action):
            self.redirect(self.app_context.get_slug())
            return
        if action in self._custom_post_actions:
            # Each POST request must have valid XSRF token.
            xsrf_token = self.request.get('xsrf_token')
            if not crypto.XsrfTokenManager.is_xsrf_token_valid(
                xsrf_token, action):
                self.error(403)
                return
            self._custom_post_actions[action](self)
            return

        return super(DashboardHandler, self).post()

    def get_template(self, template_name, dirs=None):
        """Sets up an environment and Gets jinja template."""
        return jinja_utils.get_template(
            template_name, (dirs or []) + [TEMPLATE_DIR], handler=self)

    def get_alerts(self):
        alerts = []
        if not self.app_context.is_editable_fs():
            alerts.append('Read-only course.')
        if not self.app_context.now_available:
            alerts.append('The course is not publicly available.')
        return '\n'.join(alerts)

    def _get_current_menu_action(self):
        registered_action = self._custom_get_actions.get(self.action)
        if registered_action:
            registered_in_action = registered_action.in_action
            if registered_in_action:
                return registered_in_action

        return self.action

    def render_page(self, template_values, in_action=None):
        """Renders a page using provided template values."""
        template_values['header_title'] = template_values['page_title']
        template_values['page_headers'] = [
            hook(self) for hook in self.PAGE_HEADER_HOOKS]
        template_values['course_title'] = self.app_context.get_title()

        current_action = in_action or self._get_current_menu_action()
        template_values['current_menu_item'] = self.actions_to_menu_items.get(
            current_action)
        template_values['courses_menu_item'] = self.actions_to_menu_items.get(
            'courses')
        template_values['root_menu_group'] = self.root_menu_group

        template_values['course_app_contexts'] = get_visible_courses()
        template_values['app_context'] = self.app_context
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
        template_values['powered_by_url'] = services.help_urls.get(
            'dashboard:powered_by')
        if not template_values.get('sections'):
            template_values['sections'] = []
        if not appengine_config.PRODUCTION_MODE:
            template_values['page_uuid'] = str(uuid.uuid1())

        self.response.write(
            self.get_template('view.html').render(template_values))

    @classmethod
    def register_courses_menu_item(cls, menu_item):
        cls.actions_to_menu_items['courses'] = menu_item

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
        all_roles = sorted(RoleDAO.get_all(), key=lambda role: role.name)
        return safe_dom.Template(
            self.get_template('role_list.html'), roles=all_roles)

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
    def map_get_action_to_permission(cls, action, module, perm):
        """Maps a view/get action to a permission.

        Map a GET action that goes through the dashboard to a
        permission to control which users have access.

        Example:
            The i18n module maps multiple actions to the permission
            'access_i18n_dashboard'.  Users who have a role assigned with this
            permission are then allowed to perform these actions and thus
            access the translation tools.

        Args:
            action: a string specifying the action to map.
            module: The module with which the permission was registered via
                a call to models.roles.Roles.register_permission()
            permission: a string specifying the permission to which the action
                should be mapped.
        """
        checker = lambda ctx: roles.Roles.is_user_allowed(ctx, module, perm)
        cls.map_get_action_to_permission_checker(action, checker)

    @classmethod
    def map_get_action_to_permission_checker(cls, action, checker):
        """Map an action to a function to check permissions.

        Some actions (notably settings and the course overview) produce pages
        that have items that may be controlled by multiple permissions or
        more complex verification than a single permission allows.  This
        function allows modules to specify check functions.

        Args:
          action: A string specifying the name of the action being checked.
              This should have been registered via add_custom_get_action(),
              or present in the 'get_actions' list above in this file.
          checker: A function which is run when the named action is accessed.
              Registered functions should expect one parameter: the application
              context object, and return a Boolean value.
        """
        cls._get_action_to_permission[action] = checker

    @classmethod
    def unmap_get_action_to_permission(cls, action):
        del cls._get_action_to_permission[action]

    @classmethod
    def map_post_action_to_permission(cls, action, module, perm):
        """Maps an edit action to a permission. (See 'get' version, above.)"""
        checker = lambda ctx: roles.Roles.is_user_allowed(ctx, module, perm)
        cls.map_post_action_to_permission_checker(action, checker)

    @classmethod
    def map_post_action_to_permission_checker(cls, action, checker):
        """Map an edit action to check function.  (See 'get' version, above)."""
        cls._post_action_to_permission[action] = checker

    @classmethod
    def unmap_post_action_to_permission(cls, action):
        """Remove mapping to edit action.  (See 'get' version, above)."""
        del cls._post_action_to_permission[action]

    @classmethod
    def deprecated_add_external_permission(cls, permission_name,
                                           permission_description):
        """Adds extra permissions that will be registered by the Dashboard.

        Normally, permissions should be registered in their own modules.
        Due to historical accident, the I18N module registers permissions
        with the dashboard.  For backward compatibility with existing roles,
        this API is preserved, but not suggested for use by future modules.
        """
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


def make_help_menu():
    DashboardHandler.add_nav_mapping('help', 'Help', placement=6000)

    DashboardHandler.add_sub_nav_mapping(
        'help', 'documentation', 'Documentation',
        href=services.help_urls.get('help:documentation'), target='_blank')

    DashboardHandler.add_sub_nav_mapping(
        'help', 'forum', 'Support', href=services.help_urls.get('help:forum'),
        target='_blank')

    DashboardHandler.add_sub_nav_mapping(
        'help', 'videos', 'Videos', href=services.help_urls.get('help:videos'),
        target='_blank')

def get_visible_courses():
    result = []
    for app_context in sorted(sites.get_all_courses(),
            key=lambda course: course.get_title().lower()):
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

    make_help_menu()

    # pylint: disable=protected-access
    DashboardHandler.add_sub_nav_mapping(
        'settings', 'roles', 'Roles', action='edit_roles',
        contents=DashboardHandler._render_roles_view)
    # pylint: enable=protected-access

    def on_module_enabled():
        roles.Roles.register_permissions(
            custom_module, DashboardHandler.permissions_callback)
        ApplicationHandler.RIGHT_LINKS.append(
            DashboardHandler.generate_dashboard_link)

    global_routes = [
        (dashboard_utils.RESOURCES_PATH +'/js/.*', tags.JQueryHandler),
        (dashboard_utils.RESOURCES_PATH + '/.*',
            tags.DeprecatedResourcesHandler)]

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
