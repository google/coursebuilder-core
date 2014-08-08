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

"""Classes and methods to create and manage Courses."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import datetime
import os
import urllib

from admin_preferences_editor import AdminPreferencesEditor
from admin_preferences_editor import AdminPreferencesRESTHandler
from course_settings import CourseSettingsHandler
from course_settings import CourseSettingsRESTHandler
from course_settings import HtmlHookHandler
from course_settings import HtmlHookRESTHandler
import filer
from filer import AssetItemRESTHandler
from filer import AssetUriRESTHandler
from filer import FileManagerAndEditor
from filer import FilesItemRESTHandler
from filer import TextAssetRESTHandler
from label_editor import LabelManagerAndEditor
from label_editor import LabelRestHandler
import messages
from peer_review import AssignmentManager
from question_editor import McQuestionRESTHandler
from question_editor import QuestionManagerAndEditor
from question_editor import SaQuestionRESTHandler
from question_group_editor import QuestionGroupManagerAndEditor
from question_group_editor import QuestionGroupRESTHandler
import student_answers_analytics
import unit_lesson_editor
from unit_lesson_editor import AssessmentRESTHandler
from unit_lesson_editor import ExportAssessmentRESTHandler
from unit_lesson_editor import ImportActivityRESTHandler
from unit_lesson_editor import ImportCourseRESTHandler
from unit_lesson_editor import LessonRESTHandler
from unit_lesson_editor import LinkRESTHandler
from unit_lesson_editor import UnitLessonEditor
from unit_lesson_editor import UnitLessonTitleRESTHandler
from unit_lesson_editor import UnitRESTHandler

import appengine_config
from common import crypto
from common import jinja_utils
from common import safe_dom
from common import tags
from controllers import sites
from controllers import utils
from controllers.utils import ApplicationHandler
from controllers.utils import ReflectiveRequestHandler
from models import analytics
from models import config
from models import courses
from models import custom_modules
from models import data_sources
from models import models
from models import roles
from models import vfs
from models.models import LabelDAO
from models.models import QuestionDAO
from models.models import QuestionDTO
from models.models import QuestionGroupDAO
from modules.dashboard import tabs
from modules.data_source_providers import rest_providers
from modules.data_source_providers import synchronous_providers
from modules.search.search import SearchDashboardHandler
from tools import verify

from google.appengine.api import app_identity
from google.appengine.api import users

RESOURCES_PATH = '/modules/dashboard/resources'


class DashboardHandler(
    CourseSettingsHandler, FileManagerAndEditor, UnitLessonEditor,
    QuestionManagerAndEditor, QuestionGroupManagerAndEditor,
    LabelManagerAndEditor, AssignmentManager, AdminPreferencesEditor,
    HtmlHookHandler, ApplicationHandler, ReflectiveRequestHandler,
    SearchDashboardHandler):
    """Handles all pages and actions required for managing a course."""

    default_action = 'outline'
    get_actions = [
        default_action, 'assets', 'settings', 'analytics', 'search',
        'edit_basic_settings', 'edit_settings', 'edit_unit_lesson',
        'edit_unit', 'edit_link', 'edit_lesson', 'edit_assessment',
        'add_asset', 'delete_asset', 'manage_text_asset', 'import_course',
        'edit_assignment', 'add_mc_question', 'add_sa_question',
        'edit_question', 'add_question_group', 'edit_question_group',
        'add_label', 'edit_label', 'edit_html_hook', 'question_preview']
    # Requests to these handlers automatically go through an XSRF token check
    # that is implemented in ReflectiveRequestHandler.
    post_actions = [
        'create_or_edit_settings', 'add_unit',
        'add_link', 'add_assessment', 'add_lesson', 'index_course',
        'clear_index', 'edit_basic_course_settings', 'add_reviewer',
        'delete_reviewer', 'edit_admin_preferences', 'set_draft_status']
    nav_mappings = [
        ('', 'Outline'),
        ('assets', 'Assets'),
        ('settings', 'Settings'),
        ('analytics', 'Analytics'),
        ('search', 'Search'),
        ('edit_assignment', 'Peer Review')]
    child_routes = [
            (AdminPreferencesRESTHandler.URI, AdminPreferencesRESTHandler),
            (AssessmentRESTHandler.URI, AssessmentRESTHandler),
            (AssetItemRESTHandler.URI, AssetItemRESTHandler),
            (CourseSettingsRESTHandler.URI, CourseSettingsRESTHandler),
            (HtmlHookRESTHandler.URI, HtmlHookRESTHandler),
            (FilesItemRESTHandler.URI, FilesItemRESTHandler),
            (AssetItemRESTHandler.URI, AssetItemRESTHandler),
            (AssetUriRESTHandler.URI, AssetUriRESTHandler),
            (ImportActivityRESTHandler.URI, ImportActivityRESTHandler),
            (ImportCourseRESTHandler.URI, ImportCourseRESTHandler),
            (LabelRestHandler.URI, LabelRestHandler),
            (LessonRESTHandler.URI, LessonRESTHandler),
            (LinkRESTHandler.URI, LinkRESTHandler),
            (UnitLessonTitleRESTHandler.URI, UnitLessonTitleRESTHandler),
            (UnitRESTHandler.URI, UnitRESTHandler),
            (McQuestionRESTHandler.URI, McQuestionRESTHandler),
            (SaQuestionRESTHandler.URI, SaQuestionRESTHandler),
            (TextAssetRESTHandler.URI, TextAssetRESTHandler),
            (QuestionGroupRESTHandler.URI, QuestionGroupRESTHandler),
            (ExportAssessmentRESTHandler.URI, ExportAssessmentRESTHandler)]

    # Other modules which manage editable assets can add functions here to
    # list their assets on the Assets tab. The function will receive an instance
    # of DashboardHandler as an argument.
    contrib_asset_listers = []

    local_fs = vfs.LocalReadOnlyFileSystem(logical_home_folder='/')

    @classmethod
    def get_child_routes(cls):
        """Add child handlers for REST."""
        return cls.child_routes

    def can_view(self):
        """Checks if current user has viewing rights."""
        return roles.Roles.is_course_admin(self.app_context)

    def can_edit(self):
        """Checks if current user has editing rights."""
        return roles.Roles.is_course_admin(self.app_context)

    def get(self):
        """Enforces rights to all GET operations."""
        if not self.can_view():
            self.redirect(self.app_context.get_slug())
            return
        # Force reload of properties. It is expensive, but admin deserves it!
        config.Registry.get_overrides(force_update=True)
        return super(DashboardHandler, self).get()

    def post(self):
        """Enforces rights to all POST operations."""
        if not self.can_edit():
            self.redirect(self.app_context.get_slug())
            return
        return super(DashboardHandler, self).post()

    def get_template(self, template_name, dirs):
        """Sets up an environment and Gets jinja template."""
        return jinja_utils.get_template(
            template_name, dirs + [os.path.dirname(__file__)], handler=self)

    def _get_alerts(self):
        alerts = []
        if not self.app_context.is_editable_fs():
            alerts.append('Read-only course.')
        if not self.app_context.now_available:
            alerts.append('The course is not publicly available.')
        return '\n'.join(alerts)

    def _get_top_nav(self, in_action, in_tab):
        current_action = in_action or self.request.get('action')

        nav_bars = []
        nav = safe_dom.NodeList()
        for action, title in self.nav_mappings:

            class_name = 'selected' if action == current_action else ''
            action_href = 'dashboard?action=%s' % action
            nav.append(safe_dom.Element(
                'a', href=action_href, className=class_name).add_text(
                    title))

        if roles.Roles.is_super_admin():
            nav.append(safe_dom.Element(
                'a', href='/admin').add_text('Admin'))

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
            tab_name = in_tab or self.request.get('tab') or tab_group[0].name
            sub_nav = safe_dom.NodeList()
            for tab in tab_group:
                sub_nav.append(
                    safe_dom.A(
                        'dashboard?action=%s&tab=%s' % (
                            current_action, tab.name),
                        className=('selected' if tab.name == tab_name else ''))
                    .add_text(tab.title))
            nav_bars.append(sub_nav)
        return nav_bars

    def render_page(self, template_values, in_action=None, in_tab=None):
        """Renders a page using provided template values."""

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
        if not template_values.get('sections'):
            template_values['sections'] = []

        self.response.write(
            self.get_template('view.html', []).render(template_values))

    def format_title(self, text, as_link=False):
        """Formats standard title."""
        title = self.app_context.get_environ()['course']['title']
        ret = safe_dom.NodeList()
        cb_text = 'Course Builder '
        if as_link:
            ret.append(safe_dom.A('/admin').add_text(cb_text))
        else:
            ret.append(safe_dom.Text(cb_text))
        ret.append(safe_dom.Entity('&gt;'))
        ret.append(safe_dom.Text(' %s ' % title))
        ret.append(safe_dom.Entity('&gt;'))
        dashboard_text = ' Dashboard '
        if as_link:
            ret.append(
                safe_dom.A(self.canonicalize_url('/dashboard')).
                add_text(dashboard_text))
        else:
            ret.append(safe_dom.Text(dashboard_text))
        ret.append(safe_dom.Entity('&gt;'))
        ret.append(safe_dom.Text(' %s' % text))
        return ret

    def render_course_outline_to_html(self):
        """Renders course outline to HTML."""
        course = courses.Course(self)
        if not course.get_units():
            return []
        lines = safe_dom.Element(
            'ul', style='list-style: none;', id='course-outline',
            data_status_xsrf_token=self.create_xsrf_token('set_draft_status')
        )
        for unit in course.get_units():
            if course.get_parent_unit(unit.unit_id):
                continue  # Will be rendered as part of containing element.
            if unit.type == verify.UNIT_TYPE_ASSESSMENT:
                lines.add_child(self._render_assessment_li(unit))
            elif unit.type == verify.UNIT_TYPE_LINK:
                lines.add_child(self._render_link_li(unit))
            elif unit.type == verify.UNIT_TYPE_UNIT:
                lines.add_child(self._render_unit_li(course, unit))
            else:
                raise Exception('Unknown unit type: %s.' % unit.type)
        return lines

    def _render_status_icon(self, dom_element, resource, key, component_type):
        if not hasattr(resource, 'now_available'):
            return
        icon = safe_dom.Element(
            'div', data_key=str(key), data_component_type=component_type)
        common_classes = 'icon icon-draft-status'
        if self.app_context.is_editable_fs():
            common_classes += ' active'
        if resource.now_available:
            icon.add_attribute(
                alt=unit_lesson_editor.PUBLISHED_TEXT,
                title=unit_lesson_editor.PUBLISHED_TEXT,
                className=common_classes + ' icon-unlocked',
            )
        else:
            icon.add_attribute(
                alt=unit_lesson_editor.DRAFT_TEXT,
                title=unit_lesson_editor.DRAFT_TEXT,
                className=common_classes + ' icon-locked'
            )
        dom_element.add_child(icon)

    def _render_assessment_li(self, unit):
        li = safe_dom.Element('li').add_child(
            safe_dom.Element(
                'a', href='assessment?name=%s' % unit.unit_id,
                className='strong'
            ).add_text(unit.title)
        )
        self._render_status_icon(li, unit, unit.unit_id, 'unit')
        if self.app_context.is_editable_fs():
            url = self.canonicalize_url(
                '/dashboard?%s') % urllib.urlencode({
                    'action': 'edit_assessment',
                    'key': unit.unit_id})
            li.add_child(self._create_edit_button(url))
        return li

    def _render_link_li(self, unit):
        li = safe_dom.Element('li').add_child(
            safe_dom.Element(
                'a', href=unit.href, className='strong'
            ).add_text(unit.title)
        )
        self._render_status_icon(li, unit, unit.unit_id, 'unit')
        if self.app_context.is_editable_fs():
            url = self.canonicalize_url(
                '/dashboard?%s') % urllib.urlencode({
                    'action': 'edit_link',
                    'key': unit.unit_id})
            li.add_child(self._create_edit_button(url))
        return li

    def _render_unit_li(self, course, unit):
        is_editable = self.app_context.is_editable_fs()
        li = safe_dom.Element('li').add_child(
            safe_dom.Element(
                'a', href='unit?unit=%s' % unit.unit_id,
                className='strong').add_text(
                    utils.display_unit_title(unit))
        )
        self._render_status_icon(li, unit, unit.unit_id, 'unit')
        if is_editable:
            url = self.canonicalize_url(
                '/dashboard?%s') % urllib.urlencode({
                    'action': 'edit_unit',
                    'key': unit.unit_id})
            li.add_child(self._create_edit_button(url))

        if unit.pre_assessment:
            assessment = course.find_unit_by_id(unit.pre_assessment)
            if assessment:
                ul = safe_dom.Element('ul')
                ul.add_child(self._render_assessment_li(assessment))
                li.add_child(ul)
        ol = safe_dom.Element('ol')
        for lesson in course.get_lessons(unit.unit_id):
            li2 = safe_dom.Element('li').add_child(
                safe_dom.Element(
                    'a',
                    href='unit?unit=%s&lesson=%s' % (
                        unit.unit_id, lesson.lesson_id),
                ).add_text(lesson.title)
            )
            self._render_status_icon(li2, lesson, lesson.lesson_id, 'lesson')
            if is_editable:
                url = self.get_action_url(
                    'edit_lesson', key=lesson.lesson_id)
                li2.add_child(self._create_edit_button(url))
            ol.add_child(li2)
        li.add_child(ol)
        if unit.post_assessment:
            assessment = course.find_unit_by_id(unit.post_assessment)
            if assessment:
                ul = safe_dom.Element('ul')
                ul.add_child(self._render_assessment_li(assessment))
                li.add_child(ul)
        return li

    def get_question_preview(self):
        template_values = {}
        template_values['gcb_course_base'] = self.get_base_href(self)
        template_values['question'] = tags.html_to_safe_dom(
            '<question quid="%s">' % self.request.get('quid'), self)
        self.response.write(self.get_template(
            'question_preview.html', []).render(template_values))

    def get_outline(self):
        """Renders course outline view."""

        administered_courses_actions = [
            {'id': 'add_course',
             'caption': 'Add Course',
             'href': '/admin?action=add_course'}]
        administered_courses_items = []
        all_courses = sites.get_all_courses()
        for course in sorted(all_courses, key=lambda c: c.get_title()):
            if roles.Roles.is_course_admin(course):
                slug = course.get_slug()
                content = safe_dom.NodeList()
                administered_courses_items.append(content)
                title = course.get_title()
                content.append(safe_dom.A(slug).add_text(title))
                content.append(safe_dom.Text('  %s  ' % slug))
                content.append(
                    safe_dom.A('%s/dashboard' % ('' if slug == '/' else slug))
                    .add_text('Dashboard'))

        pages_info = [
            safe_dom.Element(
                'a', href=self.canonicalize_url('/announcements')
            ).add_text('Announcements'),
            safe_dom.Element(
                'a', href=self.canonicalize_url('/course')
            ).add_text('Course')]

        outline_actions = []
        if self.app_context.is_editable_fs():
            outline_actions.append({
                'id': 'edit_unit_lesson',
                'caption': 'Organize',
                'href': self.get_action_url('edit_unit_lesson')})
            all_units = courses.Course(self).get_units()
            if any([unit.type == verify.UNIT_TYPE_UNIT for unit in all_units]):
                outline_actions.append({
                    'id': 'add_lesson',
                    'caption': 'Add Lesson',
                    'action': self.get_action_url('add_lesson'),
                    'xsrf_token': self.create_xsrf_token('add_lesson')})
            outline_actions.append({
                'id': 'add_unit',
                'caption': 'Add Unit',
                'action': self.get_action_url('add_unit'),
                'xsrf_token': self.create_xsrf_token('add_unit')})
            outline_actions.append({
                'id': 'add_link',
                'caption': 'Add Link',
                'action': self.get_action_url('add_link'),
                'xsrf_token': self.create_xsrf_token('add_link')})
            outline_actions.append({
                'id': 'add_assessment',
                'caption': 'Add Assessment',
                'action': self.get_action_url('add_assessment'),
                'xsrf_token': self.create_xsrf_token('add_assessment')})
            if not courses.Course(self).get_units():
                outline_actions.append({
                    'id': 'import_course',
                    'caption': 'Import',
                    'href': self.get_action_url('import_course')
                    })

        data_info = self.list_files('/data/')

        sections = [
            {
                'title': 'Administered Courses',
                'description': messages.ADMINISTERED_COURSES_DESCRIPTION,
                'actions': administered_courses_actions,
                'children': administered_courses_items},
            {
                'title': 'Pages',
                'description': messages.PAGES_DESCRIPTION,
                'children': pages_info},
            {
                'title': 'Course Outline',
                'description': messages.COURSE_OUTLINE_DESCRIPTION,
                'actions': outline_actions,
                'pre': self.render_course_outline_to_html()},
            {
                'title': 'Data Files',
                'description': messages.DATA_FILES_DESCRIPTION,
                'children': data_info}]

        template_values = {
            'page_title': self.format_title('Outline'),
            'page_title_linked': self.format_title('Outline', as_link=True),
            'alerts': self._get_alerts(),
            'sections': sections,
            }
        self.render_page(template_values)

    def get_action_url(self, action, key=None, extra_args=None):
        args = {'action': action}
        if key:
            args['key'] = key
        if extra_args:
            args.update(extra_args)
        url = '/dashboard?%s' % urllib.urlencode(args)
        return self.canonicalize_url(url)

    def get_settings(self):
        """Renders course settings view."""

        admin_prefs_actions = []
        yaml_actions = []
        basic_setting_actions = []

        # Admin prefs setup.
        admin_prefs_actions.append({
            'id': 'edit_admin_prefs',
            'caption': 'Edit Prefs',
            'action': self.get_action_url('edit_admin_preferences'),
            'xsrf_token': self.create_xsrf_token('edit_admin_preferences')})
        admin_prefs_info = []
        admin_prefs = models.StudentPreferencesDAO.load_or_create()
        admin_prefs_info.append('Show hook edit buttons: %s' %
                                admin_prefs.show_hooks)
        admin_prefs_info.append('Show jinja context: %s' %
                                admin_prefs.show_jinja_context)

        # Basic course info.
        course_info = [
            'Course Title: %s' % self.app_context.get_environ()['course'][
                'title'],
            'Context Path: %s' % self.app_context.get_slug(),
            'Datastore Namespace: %s' % self.app_context.get_namespace_name()]

        # Course file system.
        fs = self.app_context.fs.impl
        course_info.append(('File System: %s' % fs.__class__.__name__))
        if fs.__class__ == vfs.LocalReadOnlyFileSystem:
            course_info.append(('Home Folder: %s' % sites.abspath(
                self.app_context.get_home_folder(), '/')))

        # Enable editing if supported.
        if self.app_context.is_editable_fs():
            yaml_actions.append({
                'id': 'edit_course_yaml',
                'caption': 'Advanced Edit',
                'action': self.get_action_url('create_or_edit_settings'),
                'xsrf_token': self.create_xsrf_token(
                    'create_or_edit_settings')})
            yaml_actions.append({
                'id': 'edit_basic_course_settings_unit',
                'caption': 'Unit Options',
                'action': self.get_action_url(
                    'edit_basic_course_settings',
                    extra_args={'section_names': 'unit'}),
                'xsrf_token': self.create_xsrf_token(
                    'edit_basic_course_settings')})
            yaml_actions.append({
                'id': 'edit_basic_course_settings_reg_opts',
                'caption': 'Course Homepage Options',
                'action': self.get_action_url(
                    'edit_basic_course_settings',
                    extra_args={'section_names': 'homepage'}),
                'xsrf_token': self.create_xsrf_token(
                    'edit_basic_course_settings')})
            yaml_actions.append({
                'id': 'edit_basic_course_settings_reg_opts',
                'caption': 'Registration Options',
                'action': self.get_action_url(
                    'edit_basic_course_settings',
                    extra_args={'section_names': 'reg_form'}),
                'xsrf_token': self.create_xsrf_token(
                    'edit_basic_course_settings')})
            yaml_actions.append({
                'id': 'edit_basic_course_settings_course',
                'caption': 'Course Options',
                'action': self.get_action_url(
                    'edit_basic_course_settings',
                    extra_args={'section_names': 'course'}),
                'xsrf_token': self.create_xsrf_token(
                    'edit_basic_course_settings')})
            yaml_actions.append({
                'id': 'edit_basic_course_settings_base',
                'caption': 'Base Options',
                'action': self.get_action_url(
                    'edit_basic_course_settings',
                    extra_args={'section_names': 'base'}),
                'xsrf_token': self.create_xsrf_token(
                    'edit_basic_course_settings')})

        # course.yaml file content.
        yaml_info = []
        yaml_stream = self.app_context.fs.open(
            self.app_context.get_config_filename())
        if yaml_stream:
            yaml_lines = yaml_stream.read().decode('utf-8')
            for line in yaml_lines.split('\n'):
                yaml_info.append(line)
        else:
            yaml_info.append('< empty file >')

        # course_template.yaml file contents
        course_template_info = []
        course_template_stream = open(os.path.join(os.path.dirname(
            __file__), '../../course_template.yaml'), 'r')
        if course_template_stream:
            course_template_lines = course_template_stream.read().decode(
                'utf-8')
            for line in course_template_lines.split('\n'):
                course_template_info.append(line)
        else:
            course_template_info.append('< empty file >')

        # Prepare template values.
        template_values = {
            'page_title': self.format_title('Settings'),
            'page_title_linked': self.format_title('Settings', as_link=True),
            'page_description': messages.SETTINGS_DESCRIPTION,
        }
        template_values['sections'] = [
            {
                'title': 'Admin Preferences',
                'description': messages.ADMIN_PREFERENCES_DESCRIPTION,
                'actions': admin_prefs_actions,
                'children': admin_prefs_info},
            {
                'title': 'About the Course',
                'description': messages.ABOUT_THE_COURSE_DESCRIPTION,
                'actions': basic_setting_actions,
                'children': course_info},
            {
                'title': 'Contents of course.yaml file',
                'description': messages.CONTENTS_OF_THE_COURSE_DESCRIPTION,
                'actions': yaml_actions,
                'children': yaml_info},
            {
                'title': 'Contents of course_template.yaml file',
                'description': messages.COURSE_TEMPLATE_DESCRIPTION,
                'children': course_template_info}]

        self.render_page(template_values)

    def list_files(self, subfolder, merge_local_files=False, all_paths=None):
        """Makes a list of files in a subfolder.

        Args:
            subfolder: string. Relative path of the subfolder to list.
            merge_local_files: boolean. If True, the returned list will
                contain files found on either the datastore filesystem or the
                read-only local filesystem. If a file is found on both, its
                datastore filesystem version will trump its local filesystem
                version.
            all_paths: list. A list of all file paths in the underlying file
                system.

        Returns:
            List of relative, normalized file path strings.
        """
        home = sites.abspath(self.app_context.get_home_folder(), '/')
        _paths = None
        if all_paths is not None:
            _paths = []
            for _path in all_paths:
                if _path.startswith(sites.abspath(
                        self.app_context.get_home_folder(), subfolder)):
                    _paths.append(_path)
            _paths = set(_paths)
        else:
            _paths = set(self.app_context.fs.list(
                sites.abspath(self.app_context.get_home_folder(), subfolder)))

        if merge_local_files:
            _paths = _paths.union(set([
                os.path.join(appengine_config.BUNDLE_ROOT, path) for path in
                self.local_fs.list(subfolder[1:])]))

        result = []
        for abs_filename in _paths:
            filename = os.path.relpath(abs_filename, home)
            result.append(vfs.AbstractFileSystem.normpath(filename))
        return sorted(result)

    def list_and_format_file_list(
        self, title, subfolder, tab_name,
        links=False, upload=False, prefix=None, caption_if_empty='< none >',
        edit_url_template=None, merge_local_files=False, sub_title=None,
        all_paths=None):
        """Walks files in folders and renders their names in a section."""

        # keep a list of files without merging
        unmerged_files = {}
        if merge_local_files:
            unmerged_files = self.list_files(
                subfolder, merge_local_files=False, all_paths=all_paths)

        items = safe_dom.NodeList()
        count = 0
        for filename in self.list_files(
                subfolder, merge_local_files=merge_local_files,
                all_paths=all_paths):
            if prefix and not filename.startswith(prefix):
                continue

            # make a <li> item
            li = safe_dom.Element('li')
            if links:
                li.add_child(safe_dom.Element(
                    'a', href=urllib.quote(filename)).add_text(filename))
            else:
                li.add_text(filename)

            # add actions if available
            if (edit_url_template and
                self.app_context.fs.impl.is_read_write()):

                li.add_child(safe_dom.Entity('&nbsp;'))
                edit_url = edit_url_template % (
                    tab_name, urllib.quote(filename))
                # show [overridden] + edit button if override exists
                if (filename in unmerged_files) or (not merge_local_files):
                    li.add_text('[Overridden]').add_child(
                        self._create_edit_button(edit_url))
                # show an [override] link otherwise
                else:
                    li.add_child(safe_dom.A(edit_url).add_text('[Override]'))

            count += 1
            items.append(li)

        output = safe_dom.NodeList()

        if self.app_context.is_editable_fs() and upload:
            output.append(
                safe_dom.Element(
                    'a', className='gcb-button gcb-pull-right',
                    href='dashboard?%s' % urllib.urlencode(
                        {'action': 'add_asset',
                         'tab': tab_name,
                         'base': subfolder})
                ).add_text(
                    'Upload to ' +
                    filer.strip_leading_and_trailing_slashes(subfolder))
            ).append(
                safe_dom.Element(
                    'div', style='clear: both; padding-top: 2px;'
                )
            )
        if title:
            h3 = safe_dom.Element('h3')
            if count:
                h3.add_text('%s (%s)' % (title, count))
            else:
                h3.add_text(title)
            output.append(h3)
        if sub_title:
            output.append(safe_dom.Element('blockquote').add_text(sub_title))
        if items:
            output.append(safe_dom.Element('ol').add_children(items))
        else:
            if caption_if_empty:
                output.append(
                    safe_dom.Element('blockquote').add_text(caption_if_empty))
        return output

    def _get_location_links(self, component, component_type):
        locations = courses.Course(self).get_component_locations(
            component.id, component_type)
        links = []
        for assessment in locations['assessments']:
            url = 'assessment?name=%s' % assessment.unit_id
            links.append(
                safe_dom.Element('a', href=url).add_text(assessment.title))

        for (lesson, unit) in locations['lessons']:
            url = 'unit?unit=%s&lesson=%s' % (unit.unit_id, lesson.lesson_id)
            links.append(
                safe_dom.Element('a', href=url).add_text(
                '%s: %s' % (unit.title, lesson.title)))
        return links

    def _create_list_cell(self, list_items):
        ul = safe_dom.Element('ul')
        for item in list_items:
            ul.add_child(safe_dom.Element('li').add_child(item))
        return safe_dom.Element('td').add_child(ul)

    def _create_edit_button(self, edit_url):
        return safe_dom.A(
            href=edit_url,
            className='icon icon-edit',
            title='Edit',
            alt='Edit',
        )

    def _create_preview_button(self, **arg):
        return safe_dom.Element(
            'div',
            className='icon icon-preview',
            title='Preview',
            alt='Preview',
            **arg
        )

    def _add_assets_table(self, output, columns):
        """Creates an assets table with the specified columns.

        Args:
            output: safe_dom.NodeList to which the table should be appended.
            columns: list of tuples that specifies column name and width.
                For example ("Description", 35) would create a column with a
                width of 35% and the header would be Description.

        Returns:
            The tbody safe_dom.Element of the created table.
        """
        container = safe_dom.Element('div', className='assets-table-container')
        output.append(container)
        table = safe_dom.Element('table', className='assets-table')
        container.add_child(table)
        thead = safe_dom.Element('thead')
        table.add_child(thead)
        tr = safe_dom.Element('tr')
        thead.add_child(tr)
        ths = safe_dom.NodeList()
        for (title, width) in columns:
            ths.append(safe_dom.Element(
                'th', style=('width: %s%%' % width)).add_text(title))
        tr.add_children(ths)
        tbody = safe_dom.Element('tbody')
        table.add_child(tbody)
        return tbody

    def list_questions(self):
        """Prepare a list of the question bank contents."""
        if not self.app_context.is_editable_fs():
            return safe_dom.NodeList()

        output = safe_dom.NodeList().append(
            safe_dom.Element(
                'a', className='gcb-button gcb-pull-right',
                href='dashboard?action=add_mc_question'
            ).add_text('Add Multiple Choice')
        ).append(
            safe_dom.Element(
                'a', className='gcb-button gcb-pull-right',
                href='dashboard?action=add_sa_question'
            ).add_text('Add Short Answer')
        ).append(
            safe_dom.Element('div', style='clear: both; padding-top: 2px;')
        ).append(
            safe_dom.Element('h3').add_text('Question Bank')
        )

        # Create questions table
        tbody = self._add_assets_table(
            output, [
            ('Description', 25), ('Question Groups', 25),
            ('Course Locations', 25), ('Last Modified', 20), ('Type', 5)]
        )
        all_questions = QuestionDAO.get_all()

        if not all_questions:
            tbody.add_child(safe_dom.Element('tr').add_child(safe_dom.Element(
                'td', colspan='5', style='text-align: center'
            ).add_text('No questions available')))
            return output

        for question in all_questions:
            tr = safe_dom.Element('tr')
            # Add description including edit button
            td = safe_dom.Element('td')
            tr.add_child(td)
            td.add_child(self._create_edit_button(
                'dashboard?action=edit_question&key=%s' % question.id))
            td.add_child(
                self._create_preview_button(data_quid=str(question.id)))
            td.add_text(question.description)

            # Add containing question groups
            tr.add_child(self._create_list_cell(
                [safe_dom.Text(qg) for qg in QuestionDAO.used_by(question.id)]
            ))

            # Add locations
            tr.add_child(self._create_list_cell(
                self._get_location_links(question, 'question')
            ))

            # Add last modified timestamp
            tr.add_child(safe_dom.Element(
                'td',
                data_timestamp=str(question.last_modified),
                className='timestamp'
            ))

            # Add question type
            tr.add_child(safe_dom.Element('td').add_text(
                'MC' if question.type == QuestionDTO.MULTIPLE_CHOICE else (
                    'SA' if question.type == QuestionDTO.SHORT_ANSWER else (
                    'Unknown Type'))
            ).add_attribute(style='text-align: center'))
            tbody.add_child(tr)

        return output

    def list_question_groups(self):
        """Prepare a list of question groups."""
        if not self.app_context.is_editable_fs():
            return safe_dom.NodeList()

        output = safe_dom.NodeList()
        output.append(
            safe_dom.Element(
                'a', className='gcb-button gcb-pull-right',
                href='dashboard?action=add_question_group'
            ).add_text('Add Question Group')
        ).append(
            safe_dom.Element(
                'div', style='clear: both; padding-top: 2px;'
            )
        )
        output.append(
            safe_dom.Element('h3').add_text('Question Groups')
        )

        # Create question groups table
        tbody = self._add_assets_table(
            output, [
            ('Description', 25), ('Questions', 25), ('Course Locations', 25),
            ('Last Modified', 25)]
        )
        # TODO(jorr): Hook this into the datastore
        all_question_groups = QuestionGroupDAO.get_all()

        if not all_question_groups:
            tbody.add_child(safe_dom.Element('tr').add_child(safe_dom.Element(
                'td', colspan='4', style='text-align: center;'
            ).add_text('No question groups available')))
            return output

        for question_group in all_question_groups:
            tr = safe_dom.Element('tr')
            # Add description including edit button
            td = safe_dom.Element('td')
            tr.add_child(td)
            td.add_child(self._create_edit_button(
                'dashboard?action=edit_question_group&key=%s' % (
                question_group.id)))
            td.add_text(question_group.description)

            # Add questions
            tr.add_child(self._create_list_cell([
                safe_dom.Text(QuestionDAO.load(quid).description)
                for quid in question_group.question_ids
            ]))

            # Add locations
            tr.add_child(self._create_list_cell(
                self._get_location_links(question_group, 'question-group')
            ))

            # Add last modified timestamp
            tr.add_child(safe_dom.Element(
                'td',
                data_timestamp=str(question_group.last_modified),
                className='timestamp'
            ))

            tbody.add_child(tr)

        return output

    def list_labels(self):
        """Prepare a list of labels for use on the Assets page."""
        output = safe_dom.NodeList()
        if not self.app_context.is_editable_fs():
            return output

        output.append(
            safe_dom.A('dashboard?action=add_label',
                       className='gcb-button gcb-pull-right'
                      ).add_text('Add Label')
            ).append(
                safe_dom.Element(
                    'div', style='clear: both; padding-top: 2px;'
                )
            )
        output.append(
                safe_dom.Element('h3').add_text('Labels')
        )
        labels = LabelDAO.get_all()
        if labels:
            all_labels_ul = safe_dom.Element('ul')
            output.append(all_labels_ul)
            for label_type in sorted(
                models.LabelDTO.LABEL_TYPES,
                lambda a, b: cmp(a.menu_order, b.menu_order)):

                type_li = safe_dom.Element('li').add_text(label_type.title)
                all_labels_ul.add_child(type_li)
                labels_of_type_ul = safe_dom.Element('ul')
                type_li.add_child(labels_of_type_ul)
                for label in sorted(
                    labels, lambda a, b: cmp(a.title, b.title)):
                    if label.type == label_type.type:
                        li = safe_dom.Element('li')
                        labels_of_type_ul.add_child(li)
                        li.add_text(
                            label.title
                        ).add_child(
                            self._create_edit_button(
                                'dashboard?action=edit_label&key=%s' %
                                label.id,
                            ).add_attribute(id='label_%s' % label.title))
        else:
            output.append(safe_dom.Element('blockquote').add_text('< none >'))
        return output

    def get_assets(self):
        """Renders course assets view."""

        all_paths = self.app_context.fs.list(
            sites.abspath(self.app_context.get_home_folder(), '/'))
        tab = tabs.Registry.get_tab(
            'assets', self.request.get('tab') or 'questions')
        items = safe_dom.NodeList()
        tab.contents(self, items, tab, all_paths)
        title_text = 'Assets > %s' % tab.title
        template_values = {
            'page_title': self.format_title(title_text),
            'page_title_linked': self.format_title(title_text, as_link=True),
            'page_description': messages.ASSETS_DESCRIPTION,
            'main_content': items,
        }
        self.render_page(template_values)

    def filer_url_template(self):
        return 'dashboard?action=manage_text_asset&tab=%s&uri=%s'

    def get_assets_contrib(self, items, tab, all_paths):
        if not self.contrib_asset_listers:
            items.append(safe_dom.Text(
                'No assets extensions have been registered'))
        else:
            for asset_lister in self.contrib_asset_listers:
                items.append(asset_lister(self))

    def get_assets_questions(self, items, tab, all_paths):
        items.append(self.list_questions())
        items.append(self.list_question_groups())

    def get_assets_labels(self, items, tab, all_paths):
        items.append(self.list_labels())

    def get_assets_assessments(self, items, tab, all_paths):
        items.append(self.list_and_format_file_list(
            'Assessments', '/assets/js/', tab.name, links=True,
            prefix='assets/js/assessment-', all_paths=all_paths))

    def get_assets_activities(self, items, tab, all_paths):
        items.append(self.list_and_format_file_list(
            'Activities', '/assets/js/', tab.name, links=True,
            prefix='assets/js/activity-', all_paths=all_paths))

    def get_assets_images(self, items, tab, all_paths):
        items.append(self.list_and_format_file_list(
            'Images & Documents', '/assets/img/', tab.name, links=True,
            upload=True,
            edit_url_template='dashboard?action=delete_asset&tab=%s&uri=%s',
            caption_if_empty='< inherited from /assets/img/ >',
            all_paths=all_paths))

    def get_assets_css(self, items, tab, all_paths):
        items.append(self.list_and_format_file_list(
            'CSS', '/assets/css/', tab.name, links=True,
            upload=True, edit_url_template=self.filer_url_template(),
            caption_if_empty='< inherited from /assets/css/ >',
            merge_local_files=True, all_paths=all_paths))

    def get_assets_js(self, items, tab, all_paths):
        items.append(self.list_and_format_file_list(
            'JavaScript', '/assets/lib/', tab.name, links=True,
            upload=True, edit_url_template=self.filer_url_template(),
            caption_if_empty='< inherited from /assets/lib/ >',
            merge_local_files=True, all_paths=all_paths))

    def get_assets_html(self, items, tab, all_paths):
        items.append(self.list_and_format_file_list(
            'HTML', '/assets/html/', tab.name, links=True,
            upload=True, edit_url_template=self.filer_url_template(),
            caption_if_empty='< inherited from /assets/html/ >',
            merge_local_files=True, all_paths=all_paths))

    def get_assets_templates(self, items, tab, all_paths):
        items.append(self.list_and_format_file_list(
            'View Templates', '/views/', tab.name, upload=True,
            edit_url_template=self.filer_url_template(),
            caption_if_empty='< inherited from /views/ >',
            merge_local_files=True, all_paths=all_paths))

    def get_analytics(self):
        """Renders course analytics view."""
        tab = tabs.Registry.get_tab('analytics',
                                    self.request.get('tab') or 'students')
        title_text = 'Analytics > %s' % tab.title
        template_values = {
            'page_title': self.format_title(title_text),
            'page_title_linked': self.format_title(title_text, as_link=True),
            'main_content': analytics.generate_display_html(
                self, crypto.XsrfTokenManager, tab.contents),
            }
        self.render_page(template_values)


custom_module = None


def register_module():
    """Registers this module in the registry."""

    data_sources.Registry.register(
        student_answers_analytics.QuestionAnswersDataSource)
    data_sources.Registry.register(
        student_answers_analytics.CourseQuestionsDataSource)
    data_sources.Registry.register(
        student_answers_analytics.CourseUnitsDataSource)

    multiple_choice_question = analytics.Visualization(
        'multiple_choice_question',
        'Multiple Choice Question',
        'multiple_choice_question.html',
        data_source_classes=[
            synchronous_providers.QuestionStatsSource])
    student_progress = analytics.Visualization(
        'student_progress',
        'Student Progress',
        'student_progress.html',
        data_source_classes=[
            synchronous_providers.StudentProgressStatsSource])
    enrollment_assessment = analytics.Visualization(
        'enrollment_assessment',
        'Enrollment/Assessment',
        'enrollment_assessment.html',
        data_source_classes=[
            synchronous_providers.StudentEnrollmentAndScoresSource])
    assessment_difficulty = analytics.Visualization(
        'assessment_difficulty',
        'Assessment Difficulty',
        'assessment_difficulty.html',
        data_source_classes=[
            rest_providers.StudentAssessmentScoresDataSource])
    labels_on_students = analytics.Visualization(
        'labels_on_students',
        'Labels on Students',
        'labels_on_students.html',
        data_source_classes=[rest_providers.LabelsOnStudentsDataSource])
    question_answers = analytics.Visualization(
        'question_answers',
        'Question Answers',
        'question_answers.html',
        data_source_classes=[
            student_answers_analytics.QuestionAnswersDataSource,
            student_answers_analytics.CourseQuestionsDataSource,
            student_answers_analytics.CourseUnitsDataSource])

    tabs.Registry.register('analytics', 'students', 'Students',
                           [labels_on_students,
                            student_progress,
                            enrollment_assessment])
    tabs.Registry.register('analytics', 'questions', 'Questions',
                           [multiple_choice_question, question_answers])
    tabs.Registry.register('analytics', 'assessments', 'Assessments',
                           [assessment_difficulty])
    tabs.Registry.register('assets', 'questions', 'Questions',
                           DashboardHandler.get_assets_questions)
    tabs.Registry.register('assets', 'labels', 'Labels',
                           DashboardHandler.get_assets_labels)
    tabs.Registry.register('assets', 'assessments', 'Assessments',
                           DashboardHandler.get_assets_assessments)
    tabs.Registry.register('assets', 'activities', 'Activities',
                           DashboardHandler.get_assets_activities)
    tabs.Registry.register('assets', 'images', 'Images and Documents',
                           DashboardHandler.get_assets_images)
    tabs.Registry.register('assets', 'css', 'CSS',
                           DashboardHandler.get_assets_css)
    tabs.Registry.register('assets', 'js', 'JavaScript',
                           DashboardHandler.get_assets_js)
    tabs.Registry.register('assets', 'html', 'HTML',
                           DashboardHandler.get_assets_html)
    tabs.Registry.register('assets', 'templates', 'Templates',
                           DashboardHandler.get_assets_templates)
    tabs.Registry.register('assets', 'contrib', 'Extension Items',
                           DashboardHandler.get_assets_contrib)

    global_routes = [
        (os.path.join(RESOURCES_PATH, 'js', '.*'), tags.JQueryHandler),
        (os.path.join(RESOURCES_PATH, '.*'), tags.ResourcesHandler)]

    dashboard_handlers = [
        ('/dashboard', DashboardHandler),
    ]
    global custom_module
    custom_module = custom_modules.Module(
        'Course Dashboard',
        'A set of pages for managing Course Builder course.',
        global_routes, dashboard_handlers)
    return custom_module
