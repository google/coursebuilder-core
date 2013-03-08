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
import json
import os
import urllib
from controllers import sites
from controllers.utils import ApplicationHandler
from controllers.utils import ReflectiveRequestHandler
import jinja2
from models import courses
from models import jobs
from models import roles
from models import vfs
from models.models import Student
import filer
from filer import FileManagerAndEditor
from filer import FilesItemRESTHandler
from unit_lesson_editor import UNIT_LESSON_REST_HANDLER_URI
from unit_lesson_editor import UnitLessonEditor
from unit_lesson_editor import UnitLessonTitleRESTHandler
from google.appengine.api import users
from google.appengine.ext import db


class DashboardHandler(
    FileManagerAndEditor, UnitLessonEditor, ApplicationHandler,
    ReflectiveRequestHandler):
    """Handles all pages and actions required for managing a course."""

    default_action = 'outline'
    get_actions = [
        default_action, 'assets', 'settings', 'students', 'edit_settings',
        'edit_unit_lesson']
    post_actions = ['compute_student_stats', 'create_or_edit_settings']

    @classmethod
    def get_child_routes(cls):
        """Add child handlers for REST."""
        return [
            ('/rest/files/item', FilesItemRESTHandler),
            (UNIT_LESSON_REST_HANDLER_URI, UnitLessonTitleRESTHandler)]

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

    def render_page(self, template_values):
        """Renders a page using provided template values."""

        admin_menu = ''
        if roles.Roles.is_super_admin():
            admin_menu = '<a href="/admin">Admin</a>'

        template_values['top_nav'] = """
          <a href="dashboard">Outline</a>
          <a href="dashboard?action=assets">Assets</a>
          <a href="dashboard?action=settings">Settings</a>
          <a href="dashboard?action=students">Students</a>
          %s
          """ % admin_menu

        template_values['gcb_course_base'] = self.get_base_href(self)
        template_values['user_nav'] = '%s | <a href="%s">Logout</a>' % (
            users.get_current_user().email(), users.create_logout_url('/'))
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

    def get_outline(self):
        """Renders course outline view."""
        template_values = {}
        template_values['page_title'] = self.format_title('Outline')

        lines = []
        lines += self.list_and_format_file_list('Data Files', '/data/')

        course = courses.Course(self)
        lines.append(
            '<a id=\"edit_unit_lesson\"'
            ' class=\"gcb-button pull-right\"'
            ' role=\"button\"'
            ' href=\"dashboard?action=edit_unit_lesson\">Edit</a>')
        lines.append('<div style=\"clear: both; padding-top: 2px;\" />')
        lines.append(
            '<h3>Course Outline</h3>')
        lines.append('<ul style="list-style: none;">')
        if not course.get_units():
            lines.append('<pre>&lt; empty course &gt;</pre>')
        for unit in course.get_units():
            if unit.type == 'A':
                lines.append('<li>')
                lines.append(
                    '<strong><a href="assessment?name=%s">%s</a></strong>' % (
                        unit.unit_id, cgi.escape(unit.title)))
                lines.append('</li>\n')
                continue

            if unit.type == 'O':
                lines.append('<li>')
                lines.append(
                    '<strong><a href="%s">%s</a></strong>' % (
                        unit.unit_id, cgi.escape(unit.title)))
                lines.append('</li>\n')
                continue

            if unit.type == 'U':
                lines.append('<li>')
                lines.append('<strong>Unit %s - %s</strong>' % (
                    unit.unit_id, cgi.escape(unit.title)))
                if unit.type == 'U':
                    lines.append('<ol>')
                    for lesson in course.get_lessons(unit.unit_id):
                        href = 'unit?unit=%s&lesson=%s' % (
                            unit.unit_id, lesson.id)
                        lines.append(
                            '<li><a href="%s">%s</a></li>\n' % (
                                href, lesson.title))
                    lines.append('</ol>')
                lines.append('</li>\n')
                continue

            raise Exception('Unknown unit type: %s.' % unit.type)

        lines.append('</ul>')
        lines = ''.join(lines)

        template_values['main_content'] = lines
        self.render_page(template_values)

    def get_action_url(self, action, key=None, canonicalize=True):
        args = {'action': action}
        if key:
            args['key'] = key
        url = '/dashboard?%s' % urllib.urlencode(args)
        if canonicalize:
            return self.canonicalize_url(url)
        return url

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
        else:
            message = (
                'This course is deployed on read-only media '
                'and can\'t be edited.')
            yaml_actions.append({
                'id': 'edit_course_yaml',
                'caption': 'Edit',
                'href': 'javascript: alert("%s"); return false;' % message})

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
        template_values['sections'] = [
            {
                'title': 'About the Course',
                'children': course_info},
            {
                'title': 'Contents of <code>course.yaml</code> file',
                'actions': yaml_actions,
                'children': yaml_info}]

        self.render_page(template_values)

    def list_and_format_file_list(
        self, title, subfolder,
        links=False, prefix=None, caption_if_empty='< none >'):
        """Walks files in folders and renders their names in a section."""

        home = sites.abspath(self.app_context.get_home_folder(), '/')
        files = self.app_context.fs.list(
            sites.abspath(self.app_context.get_home_folder(), subfolder))

        lines = []
        for abs_filename in sorted(files):
            filename = os.path.relpath(abs_filename, home)
            if prefix and not filename.startswith(prefix):
                continue
            if links:
                lines.append(
                    '<li><a href="%s">%s</a></li>\n' % (
                        cgi.escape(filename), cgi.escape(filename)))
            else:
                lines.append('<li>%s</li>\n' % cgi.escape(filename))

        output = []
        count = len(lines)
        output.append('<h3>%s' % cgi.escape(title))
        if count:
            output.append(' (%s)' % count)
        output.append('</h3>')
        if lines:
            output.append('<ol>')
            output += lines
            output.append('</ol>')
        else:
            output.append(
                '<blockquote>%s</blockquote>' % cgi.escape(caption_if_empty))
        return output

    def get_assets(self):
        """Renders course assets view."""

        def inherits_from(folder):
            return '< inherited from %s >' % folder

        template_values = {}
        template_values['page_title'] = self.format_title('Assets')

        lines = []
        lines += self.list_and_format_file_list(
            'Assessments', '/assets/js/', True,
            prefix='assets/js/assessment-')
        lines += self.list_and_format_file_list(
            'Activities', '/assets/js/', True,
            prefix='assets/js/activity-')
        lines += self.list_and_format_file_list(
            'Images & Documents', '/assets/img/', True)
        lines += self.list_and_format_file_list(
            'Cascading Style Sheets', '/assets/css/', True,
            caption_if_empty=inherits_from('/assets/css/'))
        lines += self.list_and_format_file_list(
            'JavaScript Libraries', '/assets/lib/', True,
            caption_if_empty=inherits_from('/assets/lib/'))
        lines += self.list_and_format_file_list(
            'View Templates', '/views/',
            caption_if_empty=inherits_from('/views/'))
        lines = ''.join(lines)

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
                stats = json.loads(job.output)
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
            scores = json.loads(student.scores)
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
