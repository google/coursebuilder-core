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

from course_settings import CourseSettingsHandler
from course_settings import CourseSettingsRESTHandler
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
from controllers import sites
from controllers import utils
from controllers.utils import ApplicationHandler
from controllers.utils import ReflectiveRequestHandler
from models import analytics
from models import config
from models import courses
from models import custom_modules
from models import roles
from models import vfs
from models.models import LabelDAO
from models.models import QuestionDAO
from models.models import QuestionGroupDAO
from modules.dashboard import tabs
from modules.data_source_providers import rest_providers
from modules.data_source_providers import synchronous_providers
from modules.search.search import SearchDashboardHandler
from tools import verify

from google.appengine.api import users


class DashboardHandler(
    CourseSettingsHandler, FileManagerAndEditor, UnitLessonEditor,
    QuestionManagerAndEditor, QuestionGroupManagerAndEditor,
    LabelManagerAndEditor, AssignmentManager,
    ApplicationHandler, ReflectiveRequestHandler, SearchDashboardHandler):
    """Handles all pages and actions required for managing a course."""

    default_action = 'outline'
    get_actions = [
        default_action, 'assets', 'settings', 'analytics', 'search',
        'edit_basic_settings', 'edit_settings', 'edit_unit_lesson',
        'edit_unit', 'edit_link', 'edit_lesson', 'edit_assessment',
        'add_asset', 'delete_asset', 'manage_text_asset', 'import_course',
        'edit_assignment', 'add_mc_question', 'add_sa_question',
        'edit_question', 'add_question_group', 'edit_question_group',
        'add_label', 'edit_label']
    # Requests to these handlers automatically go through an XSRF token check
    # that is implemented in ReflectiveRequestHandler.
    post_actions = [
        'create_or_edit_settings', 'add_unit',
        'add_link', 'add_assessment', 'add_lesson', 'index_course',
        'clear_index', 'edit_basic_course_settings', 'add_reviewer',
        'delete_reviewer']
    nav_mappings = [
        ('', 'Outline'),
        ('assets', 'Assets'),
        ('settings', 'Settings'),
        ('analytics', 'Analytics'),
        ('search', 'Search'),
        ('edit_assignment', 'Peer Review')]
    child_routes = [
            (AssessmentRESTHandler.URI, AssessmentRESTHandler),
            (AssetItemRESTHandler.URI, AssetItemRESTHandler),
            (CourseSettingsRESTHandler.URI, CourseSettingsRESTHandler),
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
        if not courses.is_editable_fs(self.app_context):
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
            'page_footer'] = 'Created on: %s' % datetime.datetime.now()

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

    def _get_edit_link(self, url):
        return safe_dom.NodeList().append(
            safe_dom.Text(' ')
        ).append(
            safe_dom.Element('a', href=url).add_text('Edit')
        )

    def _get_availability(self, resource):
        if not hasattr(resource, 'now_available'):
            return safe_dom.Text('')
        if resource.now_available:
            return safe_dom.Text('')
        else:
            return safe_dom.NodeList().append(
                safe_dom.Text(' ')
            ).append(
                safe_dom.Element(
                    'span', className='draft-label'
                ).add_text('(%s)' % unit_lesson_editor.DRAFT_TEXT)
            )

    def render_course_outline_to_html(self):
        """Renders course outline to HTML."""
        course = courses.Course(self)
        if not course.get_units():
            return []

        is_editable = filer.is_editable_fs(self.app_context)

        lines = safe_dom.Element('ul', style='list-style: none;')
        for unit in course.get_units():
            if unit.type == verify.UNIT_TYPE_ASSESSMENT:
                li = safe_dom.Element('li').add_child(
                    safe_dom.Element(
                        'a', href='assessment?name=%s' % unit.unit_id,
                        className='strong'
                    ).add_text(unit.title)
                ).add_child(self._get_availability(unit))
                if is_editable:
                    url = self.canonicalize_url(
                        '/dashboard?%s') % urllib.urlencode({
                            'action': 'edit_assessment',
                            'key': unit.unit_id})
                    li.add_child(self._get_edit_link(url))
                lines.add_child(li)
                continue

            if unit.type == verify.UNIT_TYPE_LINK:
                li = safe_dom.Element('li').add_child(
                    safe_dom.Element(
                        'a', href=unit.href, className='strong'
                    ).add_text(unit.title)
                ).add_child(self._get_availability(unit))
                if is_editable:
                    url = self.canonicalize_url(
                        '/dashboard?%s') % urllib.urlencode({
                            'action': 'edit_link',
                            'key': unit.unit_id})
                    li.add_child(self._get_edit_link(url))
                lines.add_child(li)
                continue

            if unit.type == verify.UNIT_TYPE_UNIT:
                li = safe_dom.Element('li').add_child(
                    safe_dom.Element(
                        'a', href='unit?unit=%s' % unit.unit_id,
                        className='strong').add_text(
                            utils.display_unit_title(unit))
                ).add_child(self._get_availability(unit))
                if is_editable:
                    url = self.canonicalize_url(
                        '/dashboard?%s') % urllib.urlencode({
                            'action': 'edit_unit',
                            'key': unit.unit_id})
                    li.add_child(self._get_edit_link(url))

                ol = safe_dom.Element('ol')
                for lesson in course.get_lessons(unit.unit_id):
                    li2 = safe_dom.Element('li').add_child(
                        safe_dom.Element(
                            'a',
                            href='unit?unit=%s&lesson=%s' % (
                                unit.unit_id, lesson.lesson_id),
                        ).add_text(lesson.title)
                    ).add_child(self._get_availability(lesson))
                    if is_editable:
                        url = self.get_action_url(
                            'edit_lesson', key=lesson.lesson_id)
                        li2.add_child(self._get_edit_link(url))
                    ol.add_child(li2)
                li.add_child(ol)
                lines.add_child(li)
                continue

            raise Exception('Unknown unit type: %s.' % unit.type)

        return lines

    def get_outline(self):
        """Renders course outline view."""

        pages_info = [
            safe_dom.Element(
                'a', href=self.canonicalize_url('/announcements')
            ).add_text('Announcements'),
            safe_dom.Element(
                'a', href=self.canonicalize_url('/course')
            ).add_text('Course')]

        outline_actions = []
        if filer.is_editable_fs(self.app_context):
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

        yaml_actions = []
        basic_setting_actions = []

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
        if filer.is_editable_fs(self.app_context):
            yaml_actions.append({
                'id': 'edit_course_yaml',
                'caption': 'Advanced Edit',
                'action': self.get_action_url('create_or_edit_settings'),
                'xsrf_token': self.create_xsrf_token(
                    'create_or_edit_settings')})
            yaml_actions.append({
                'id': 'edit_basic_course_settings',
                'caption': 'Edit',
                'action': self.get_action_url('edit_basic_course_settings'),
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

            # show different captions depending if the override exists or not
            has_override = filename in unmerged_files
            link_caption = '[Override]'
            if has_override or not merge_local_files:
                link_caption = '[Edit]'

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
                edit_url = edit_url_template % (tab_name,
                                                urllib.quote(filename))
                li.add_child(
                    safe_dom.Entity('&nbsp;')
                ).add_child(
                    safe_dom.Element('a', href=edit_url).add_text(link_caption))

            count += 1
            items.append(li)

        output = safe_dom.NodeList()

        if filer.is_editable_fs(self.app_context) and upload:
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

    def list_questions(self):
        """Prepare a list of the question bank contents."""
        if not filer.is_editable_fs(self.app_context):
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

        all_questions = QuestionDAO.get_all()
        if all_questions:
            ol = safe_dom.Element('ol')
            for question in all_questions:
                edit_url = 'dashboard?action=edit_question&key=%s' % question.id
                li = safe_dom.Element('li')
                li.add_text(
                    question.description
                ).add_child(
                    safe_dom.Entity('&nbsp;')
                ).add_child(
                    safe_dom.Element('a', href=edit_url).add_text('[Edit]'))
                ol.add_child(li)
            output.append(ol)
        else:
            output.append(safe_dom.Element('blockquote').add_text('< none >'))

        return output

    def list_question_groups(self):
        """Prepare a list of question groups."""
        if not filer.is_editable_fs(self.app_context):
            return safe_dom.NodeList()

        all_questions = QuestionDAO.get_all()
        output = safe_dom.NodeList()
        if all_questions:
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

        # TODO(jorr): Hook this into the datastore
        all_question_groups = QuestionGroupDAO.get_all()
        if all_question_groups:
            ol = safe_dom.Element('ol')
            for question_group in all_question_groups:
                edit_url = 'dashboard?action=edit_question_group&key=%s' % (
                    question_group.id)
                li = safe_dom.Element('li')
                li.add_text(
                    question_group.description
                ).add_child(
                    safe_dom.Entity('&nbsp;')
                ).add_child(
                    safe_dom.Element('a', href=edit_url).add_text('[Edit]'))
                ol.add_child(li)
            output.append(ol)
        else:
            output.append(safe_dom.Element('blockquote').add_text('< none >'))

        return output

    def list_labels(self):
        """Prepare a list of labels for use on the Assets page."""
        output = safe_dom.NodeList()
        if not filer.is_editable_fs(self.app_context):
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
            ol = safe_dom.Element('ol')
            for label in labels:
                li = safe_dom.Element('li')
                li.add_text(
                    label.title
                ).add_child(
                    safe_dom.Entity('&nbsp;')
                ).add_child(
                    safe_dom.A('dashboard?action=edit_label&key=%s' % label.id,
                               id='label_%s' % label.title).add_text('[Edit]'))
                ol.add_child(li)
            output.append(ol)
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
            'Cascading Style Sheets', '/assets/css/', tab.name, links=True,
            upload=True, edit_url_template=self.filer_url_template(),
            caption_if_empty='< inherited from /assets/css/ >',
            merge_local_files=True, all_paths=all_paths))

    def get_assets_js(self, items, tab, all_paths):
        items.append(self.list_and_format_file_list(
            'JavaScript Libraries', '/assets/lib/', tab.name, links=True,
            upload=True, edit_url_template=self.filer_url_template(),
            caption_if_empty='< inherited from /assets/lib/ >',
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

    tabs.Registry.register('analytics', 'students', 'Students',
                           [labels_on_students,
                            student_progress,
                            enrollment_assessment])
    tabs.Registry.register('analytics', 'questions', 'Questions',
                           [multiple_choice_question])
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
    tabs.Registry.register('assets', 'css', 'Cascading Style Sheets',
                           DashboardHandler.get_assets_css)
    tabs.Registry.register('assets', 'js', 'JavaScript Libraries',
                           DashboardHandler.get_assets_js)
    tabs.Registry.register('assets', 'templates', 'Templates',
                           DashboardHandler.get_assets_templates)
    tabs.Registry.register('assets', 'contrib', 'Extension Items',
                           DashboardHandler.get_assets_contrib)

    dashboard_handlers = [
        ('/dashboard', DashboardHandler),
    ]
    global custom_module
    custom_module = custom_modules.Module(
        'Course Dashboard',
        'A set of pages for managing Course Builder course.',
        [], dashboard_handlers)
    return custom_module
