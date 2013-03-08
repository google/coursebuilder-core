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

import cgi
import datetime
import os
import urllib
from controllers import sites
from controllers.utils import ApplicationHandler
from controllers.utils import ReflectiveRequestHandler
import jinja2
from models import config
from models import courses
from models import jobs
from models import roles
from models import transforms
from models import vfs
from models.models import Student
import filer
from filer import AssetItemRESTHandler
from filer import AssetUriRESTHandler
from filer import FileManagerAndEditor
from filer import FilesItemRESTHandler
import messages
import unit_lesson_editor
from unit_lesson_editor import AssessmentRESTHandler
from unit_lesson_editor import ImportCourseRESTHandler
from unit_lesson_editor import LessonRESTHandler
from unit_lesson_editor import LinkRESTHandler
from unit_lesson_editor import UnitLessonEditor
from unit_lesson_editor import UnitLessonTitleRESTHandler
from unit_lesson_editor import UnitRESTHandler
from google.appengine.api import users
from google.appengine.ext import db


class DashboardHandler(
    FileManagerAndEditor, UnitLessonEditor, ApplicationHandler,
    ReflectiveRequestHandler):
    """Handles all pages and actions required for managing a course."""

    default_action = 'outline'
    get_actions = [
        default_action, 'assets', 'settings', 'students',
        'edit_settings', 'edit_unit_lesson', 'edit_unit', 'edit_link',
        'edit_lesson', 'edit_assessment', 'add_asset', 'delete_asset',
        'import_course']
    post_actions = [
        'compute_student_stats', 'create_or_edit_settings', 'add_unit',
        'add_link', 'add_assessment', 'add_lesson']

    @classmethod
    def get_child_routes(cls):
        """Add child handlers for REST."""
        return [
            (AssessmentRESTHandler.URI, AssessmentRESTHandler),
            (AssetItemRESTHandler.URI, AssetItemRESTHandler),
            (FilesItemRESTHandler.URI, FilesItemRESTHandler),
            (AssetItemRESTHandler.URI, AssetItemRESTHandler),
            (AssetUriRESTHandler.URI, AssetUriRESTHandler),
            (ImportCourseRESTHandler.URI, ImportCourseRESTHandler),
            (LessonRESTHandler.URI, LessonRESTHandler),
            (LinkRESTHandler.URI, LinkRESTHandler),
            (UnitLessonTitleRESTHandler.URI, UnitLessonTitleRESTHandler),
            (UnitRESTHandler.URI, UnitRESTHandler)
        ]

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
        jinja_environment = jinja2.Environment(
            autoescape=True,
            loader=jinja2.FileSystemLoader(dirs + [os.path.dirname(__file__)]))
        return jinja_environment.get_template(template_name)

    def _get_alerts(self):
        alerts = []
        if not courses.is_editable_fs(self.app_context):
            alerts.append('Read-only course.')
        if not self.app_context.now_available:
            alerts.append('The course is not publicly available.')
        return '\n'.join(alerts)

    def _get_top_nav(self):
        current_action = self.request.get('action')
        nav_mappings = [
            ('', 'Outline'),
            ('assets', 'Assets'),
            ('settings', 'Settings'),
            ('students', 'Students')]
        nav = []
        for action, title in nav_mappings:
            class_attr = 'class="selected"' if action == current_action else ''
            nav.append(
                '<a href="dashboard?action=%s" %s>%s</a>' % (
                    action, class_attr, title))

        if roles.Roles.is_super_admin():
            nav.append('<a href="/admin">Admin</a>')

        nav.append(
            '<a href="https://code.google.com/p/course-builder/wiki/Dashboard"'
            ' target="_blank">'
            'Help</a>')

        return '\n'.join(nav)

    def render_page(self, template_values):
        """Renders a page using provided template values."""

        template_values['top_nav'] = self._get_top_nav()
        template_values['gcb_course_base'] = self.get_base_href(self)
        template_values['user_nav'] = '%s | <a href="%s">Logout</a>' % (
            users.get_current_user().email(),
            users.create_logout_url(self.request.uri)
        )
        template_values[
            'page_footer'] = 'Created on: %s' % datetime.datetime.now()

        if not template_values.get('sections'):
            template_values['sections'] = []

        self.response.write(
            self.get_template('view.html', []).render(template_values))

    def format_title(self, text):
        """Formats standard title."""
        title = self.app_context.get_environ()['course']['title']
        return ('Course Builder &gt; %s &gt; Dashboard &gt; %s' %
                (cgi.escape(title), text))

    def _get_edit_link(self, url):
        return '&nbsp;<a href="%s">Edit</a>' % url

    def _get_availability(self, resource):
        if not hasattr(resource, 'now_available'):
            return ''
        if resource.now_available:
            return ''
        else:
            return ' <span class="draft-label">(%s)</span>' % (
                unit_lesson_editor.DRAFT_TEXT)

    def render_course_outline_to_html(self):
        """Renders course outline to HTML."""
        course = courses.Course(self)
        if not course.get_units():
            return []

        is_editable = filer.is_editable_fs(self.app_context)

        lines = []
        lines.append('<ul style="list-style: none;">')
        for unit in course.get_units():
            if unit.type == 'A':
                lines.append('<li>')
                lines.append(
                    '<strong><a href="assessment?name=%s">%s</a></strong>' % (
                        unit.unit_id, cgi.escape(unit.title)))
                lines.append(self._get_availability(unit))
                if is_editable:
                    url = self.canonicalize_url(
                        '/dashboard?%s') % urllib.urlencode({
                            'action': 'edit_assessment',
                            'key': unit.unit_id})
                    lines.append(self._get_edit_link(url))
                lines.append('</li>\n')
                continue

            if unit.type == 'O':
                lines.append('<li>')
                lines.append(
                    '<strong><a href="%s">%s</a></strong>' % (
                        unit.href, cgi.escape(unit.title)))
                lines.append(self._get_availability(unit))
                if is_editable:
                    url = self.canonicalize_url(
                        '/dashboard?%s') % urllib.urlencode({
                            'action': 'edit_link',
                            'key': unit.unit_id})
                    lines.append(self._get_edit_link(url))
                lines.append('</li>\n')
                continue

            if unit.type == 'U':
                lines.append('<li>')
                lines.append(
                    ('<strong><a href="unit?unit=%s">Unit %s - %s</a>'
                     '</strong>') % (
                         unit.unit_id, unit.index, cgi.escape(unit.title)))
                lines.append(self._get_availability(unit))
                if is_editable:
                    url = self.canonicalize_url(
                        '/dashboard?%s') % urllib.urlencode({
                            'action': 'edit_unit',
                            'key': unit.unit_id})
                    lines.append(self._get_edit_link(url))

                lines.append('<ol>')
                for lesson in course.get_lessons(unit.unit_id):
                    lines.append(
                        '<li><a href="unit?unit=%s&lesson=%s">%s</a>\n' % (
                            unit.unit_id, lesson.lesson_id,
                            cgi.escape(lesson.title)))
                    lines.append(self._get_availability(lesson))
                    if is_editable:
                        url = self.get_action_url(
                            'edit_lesson', key=lesson.lesson_id)
                        lines.append(self._get_edit_link(url))
                    lines.append('</li>')
                lines.append('</ol>')
                lines.append('</li>\n')
                continue

            raise Exception('Unknown unit type: %s.' % unit.type)

        lines.append('</ul>')
        return ''.join(lines)

    def get_outline(self):
        """Renders course outline view."""

        pages_info = [
            '<a href="%s">Announcements</a>' % self.canonicalize_url(
                '/announcements'),
            '<a href="%s">Course</a>' % self.canonicalize_url('/course')]

        outline_actions = []
        if filer.is_editable_fs(self.app_context):
            outline_actions.append({
                'id': 'edit_unit_lesson',
                'caption': 'Organize',
                'href': self.get_action_url('edit_unit_lesson')})
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

        template_values = {}
        template_values['page_title'] = self.format_title('Outline')
        template_values['alerts'] = self._get_alerts()
        template_values['sections'] = sections
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

        # Basic course info.
        course_info = [
            ('Course Title', self.app_context.get_environ()['course']['title']),
            ('Context Path', self.app_context.get_slug()),
            ('Datastore Namespace', self.app_context.get_namespace_name())]

        # Course file system.
        fs = self.app_context.fs.impl
        course_info.append(('File system', fs.__class__.__name__))
        if fs.__class__ == vfs.LocalReadOnlyFileSystem:
            course_info.append(('Home folder', sites.abspath(
                self.app_context.get_home_folder(), '/')))

        # Enable editing if supported.
        if filer.is_editable_fs(self.app_context):
            yaml_actions.append({
                'id': 'edit_course_yaml',
                'caption': 'Edit',
                'action': self.get_action_url('create_or_edit_settings'),
                'xsrf_token': self.create_xsrf_token(
                    'create_or_edit_settings')})

        # Yaml file content.
        yaml_info = []
        yaml_stream = self.app_context.fs.open(
            self.app_context.get_config_filename())
        if yaml_stream:
            yaml_lines = yaml_stream.read().decode('utf-8')
            for line in yaml_lines.split('\n'):
                yaml_info.append(line)
        else:
            yaml_info.append('< empty file >')

        # Prepare template values.
        template_values = {}
        template_values['page_title'] = self.format_title('Settings')
        template_values['page_description'] = messages.SETTINGS_DESCRIPTION
        template_values['sections'] = [
            {
                'title': 'About the Course',
                'description': messages.ABOUT_THE_COURSE_DESCRIPTION,
                'children': course_info},
            {
                'title': 'Contents of course.yaml file',
                'description': messages.CONTENTS_OF_THE_COURSE_DESCRIPTION,
                'actions': yaml_actions,
                'children': yaml_info}]

        self.render_page(template_values)

    def list_files(self, subfolder):
        """Makes a list of files in a subfolder."""
        home = sites.abspath(self.app_context.get_home_folder(), '/')
        files = self.app_context.fs.list(
            sites.abspath(self.app_context.get_home_folder(), subfolder))
        result = []
        for abs_filename in sorted(files):
            filename = os.path.relpath(abs_filename, home)
            result.append(vfs.AbstractFileSystem.normpath(filename))
        return result

    def list_and_format_file_list(
        self, title, subfolder,
        links=False, upload=False, prefix=None, caption_if_empty='< none >',
        edit_url_template=None, sub_title=None):
        """Walks files in folders and renders their names in a section."""

        lines = []
        count = 0
        for filename in self.list_files(subfolder):
            if prefix and not filename.startswith(prefix):
                continue
            if links:
                lines.append(
                    '<li><a href="%s">%s</a>' % (
                        urllib.quote(filename), cgi.escape(filename)))
                if edit_url_template:
                    edit_url = edit_url_template % urllib.quote(filename)
                    lines.append('&nbsp;<a href="%s">[Edit]</a>' % edit_url)
                lines.append('</li>\n')
            else:
                lines.append('<li>%s</li>\n' % cgi.escape(filename))
            count += 1

        output = []

        if filer.is_editable_fs(self.app_context) and upload:
            output.append(
                '<a class="gcb-button pull-right" href="dashboard?%s">'
                'Upload</a>' % urllib.urlencode(
                    {'action': 'add_asset', 'base': subfolder}))
            output.append('<div style=\"clear: both; padding-top: 2px;\" />')
        if title:
            output.append('<h3>%s' % cgi.escape(title))
            if count:
                output.append(' (%s)' % count)
            output.append('</h3>')
        if sub_title:
            output.append('<blockquote>%s</blockquote>' % cgi.escape(sub_title))
        if lines:
            output.append('<ol>')
            output += lines
            output.append('</ol>')
        else:
            if caption_if_empty:
                output.append(
                    '<blockquote>%s</blockquote>' % cgi.escape(
                        caption_if_empty))
        return output

    def get_assets(self):
        """Renders course assets view."""

        def inherits_from(folder):
            return '< inherited from %s >' % folder

        lines = []
        lines += self.list_and_format_file_list(
            'Assessments', '/assets/js/', links=True,
            prefix='assets/js/assessment-')
        lines += self.list_and_format_file_list(
            'Activities', '/assets/js/', links=True,
            prefix='assets/js/activity-')
        lines += self.list_and_format_file_list(
            'Images & Documents', '/assets/img/', links=True, upload=True,
            edit_url_template='dashboard?action=delete_asset&uri=%s',
            sub_title='< inherited from /assets/img/ >', caption_if_empty=None)
        lines += self.list_and_format_file_list(
            'Cascading Style Sheets', '/assets/css/', links=True,
            caption_if_empty=inherits_from('/assets/css/'))
        lines += self.list_and_format_file_list(
            'JavaScript Libraries', '/assets/lib/', links=True,
            caption_if_empty=inherits_from('/assets/lib/'))
        lines += self.list_and_format_file_list(
            'View Templates', '/views/',
            caption_if_empty=inherits_from('/views/'))
        lines = ''.join(lines)

        template_values = {}
        template_values['page_title'] = self.format_title('Assets')
        template_values['page_description'] = messages.ASSETS_DESCRIPTION
        template_values['main_content'] = lines
        self.render_page(template_values)

    def get_students(self):
        """Renders course students view."""

        template_values = {}
        template_values['page_title'] = self.format_title('Students')

        details = """
            <h3>Enrollment Statistics</h3>
            <ul><li>pending</li></ul>
            <h3>Assessment Statistics</h3>
            <ul><li>pending</li></ul>
            """

        update_message = ''
        update_action = """
            <form
                id='gcb-compute-student-stats'
                action='dashboard?action=compute_student_stats'
                method='POST'>
                <input type="hidden" name="xsrf_token" value="%s">
                <p>
                    <button class="gcb-button" type="submit">
                        Re-Calculate Now
                    </button>
                </p>
            </form>
        """ % self.create_xsrf_token('compute_student_stats')

        job = ComputeStudentStats(self.app_context).load()
        if not job:
            update_message = """
                Student statistics have not been calculated yet."""
        else:
            if job.status_code == jobs.STATUS_CODE_COMPLETED:
                stats = transforms.loads(job.output)
                enrolled = stats['enrollment']['enrolled']
                unenrolled = stats['enrollment']['unenrolled']

                enrollment = []
                enrollment.append(
                    '<li>previously enrolled: %s</li>' % unenrolled)
                enrollment.append(
                    '<li>currently enrolled: %s</li>' % enrolled)
                enrollment.append(
                    '<li>total: %s</li>' % (unenrolled + enrolled))
                enrollment = ''.join(enrollment)

                assessment = []
                total = 0
                for key, value in stats['scores'].items():
                    total += value[0]
                    avg_score = 0
                    if value[0]:
                        avg_score = round(value[1] / value[0], 1)
                    assessment.append("""
                        <li>%s: completed %s, average score %s
                        """ % (key, value[0], avg_score))
                assessment.append('<li>total: %s</li>' % total)
                assessment = ''.join(assessment)

                details = """
                    <h3>Enrollment Statistics</h3>
                    <ul>%s</ul>
                    <h3>Assessment Statistics</h3>
                    <ul>%s</ul>
                    """ % (enrollment, assessment)

                update_message = """
                    Student statistics were last updated on
                    %s in about %s second(s).""" % (
                        job.updated_on, job.execution_time_sec)
            elif job.status_code == jobs.STATUS_CODE_FAILED:
                update_message = """
                    There was an error updating student statistics.
                    Here is the message:<br>
                    <blockquote>
                      <pre>\n%s</pre>
                    </blockquote>
                    """ % cgi.escape(job.output)
            else:
                update_action = ''
                update_message = """
                    Student statistics update started on %s and is running
                    now. Please come back shortly.""" % job.updated_on

        lines = []
        lines.append(details)
        lines.append(update_message)
        lines.append(update_action)
        lines = ''.join(lines)

        template_values['main_content'] = lines
        self.render_page(template_values)

    def post_compute_student_stats(self):
        """Submits a new student statistics calculation task."""
        job = ComputeStudentStats(self.app_context)
        job.submit()
        self.redirect('/dashboard?action=students')


class ScoresAggregator(object):
    """Aggregates scores statistics."""

    def __init__(self):
        # We store all data as tuples keyed by the assessment type name. Each
        # tuple keeps:
        #     (student_count, sum(score))
        self.name_to_tuple = {}

    def visit(self, student):
        if student.scores:
            scores = transforms.loads(student.scores)
            for key in scores.keys():
                if key in self.name_to_tuple:
                    count = self.name_to_tuple[key][0]
                    score_sum = self.name_to_tuple[key][1]
                else:
                    count = 0
                    score_sum = 0
                self.name_to_tuple[key] = (
                    count + 1, score_sum + float(scores[key]))


class EnrollmentAggregator(object):
    """Aggregates enrollment statistics."""

    def __init__(self):
        self.enrolled = 0
        self.unenrolled = 0

    def visit(self, student):
        if student.is_enrolled:
            self.enrolled += 1
        else:
            self.unenrolled += 1


class ComputeStudentStats(jobs.DurableJob):
    """A job that computes student statistics."""

    def run(self):
        """Computes student statistics."""

        enrollment = EnrollmentAggregator()
        scores = ScoresAggregator()
        query = db.GqlQuery(
            'SELECT * FROM %s' % Student().__class__.__name__,
            batch_size=10000)
        for student in query.run():
            enrollment.visit(student)
            scores.visit(student)

        data = {
            'enrollment': {
                'enrolled': enrollment.enrolled,
                'unenrolled': enrollment.unenrolled},
            'scores': scores.name_to_tuple}

        return data
