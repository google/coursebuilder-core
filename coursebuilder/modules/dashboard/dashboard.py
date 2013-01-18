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
from controllers import sites
from controllers.utils import ApplicationHandler
from controllers.utils import ReflectiveRequestHandler
import jinja2
from models import courses
from models import jobs
from models import roles
from models.models import Student
from google.appengine.api import users
from google.appengine.ext import db


class DashboardHandler(ApplicationHandler, ReflectiveRequestHandler):
    """Handles all pages and actions required for managing a course."""

    default_action = 'outline'
    get_actions = [default_action, 'assets', 'settings', 'students']
    post_actions = ['compute_student_stats']

    def can_view(self):
        """Checks if current user has viewing rights."""
        return roles.Roles.is_super_admin()

    def get(self):
        """Enforces rights to all GET operations."""
        if not self.can_view():
            self.redirect(self.app_context.get_slug())
            return
        return super(DashboardHandler, self).get()

    def get_template(self, template_name, dirs):
        """Sets up an environment and Gets jinja template."""
        jinja_environment = jinja2.Environment(
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

        course = courses.Course(self)

        lines = []
        lines.append(
            '<h3>Course Units, Lessons, Activities and Assessments</h3>')
        lines.append('<ul style="list-style: none;">')
        for unit in course.get_units():
            if unit.type == 'A':
                lines.append('<li>')
                lines.append(
                    '<strong><a href="assessment?name=%s">%s</a></strong>' % (
                        unit.unit_id, cgi.escape(unit.title)))
                lines.append('</li>')
                continue

            if unit.type == 'O':
                lines.append('<li>')
                lines.append(
                    '<strong><a href="%s">%s</a></strong>' % (
                        unit.unit_id, cgi.escape(unit.title)))
                lines.append('</li>')
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
                            '<li><a href="%s">%s</a></li>' % (
                                href, lesson.title))
                    lines.append('</ol>')
                lines.append('</li>')
                continue

            raise Exception('Unknown unit type: %s.' % unit.type)

        lines.append('</ul>')
        lines = ''.join(lines)

        template_values['main_content'] = lines
        self.render_page(template_values)

    def get_settings(self):
        """Renders course settings view."""

        template_values = {}
        template_values['page_title'] = self.format_title('Settings')

        # Course identity.
        title = self.app_context.get_environ()['course']['title']
        location = sites.abspath(self.app_context.get_home_folder(), '/')
        yaml = self.app_context.get_config_filename()
        slug = self.app_context.get_slug()
        namespace = self.app_context.get_namespace_name()

        course_info = []
        course_info.append('<h3>About the Course</h3>')
        course_info.append("""
            <ol>
            <li>Course Title: %s</li>
            <li>Content Location: %s</li>
            <li>config.yaml: %s</li>
            <li>Context Path: %s</li>
            <li>Datastore Namespace: %s</li>
            </ol>
            """ % (title, location, yaml, slug, namespace))
        course_info = ''.join(course_info)

        # Yaml file content.
        yaml_content = []
        yaml_content.append(
            '<h3>Contents of <code>course.yaml</code> file</h3>')
        yaml_content.append('<ol>')
        yaml_lines = open(
            self.app_context.get_config_filename(), 'r').readlines()
        for line in yaml_lines:
            yaml_content.append('<li>%s</li>' % cgi.escape(line))
        yaml_content.append('</ol>')
        yaml_content = ''.join(yaml_content)

        template_values['main_content'] = course_info + yaml_content
        self.render_page(template_values)

    def list_and_format_file_list(self, subfolder, links=False):
        """Walks files in folders and renders their names."""

        home = sites.abspath(self.app_context.get_home_folder(), '/')
        start = sites.abspath(self.app_context.get_home_folder(), subfolder)

        files = []
        for dirname, unused_dirnames, filenames in os.walk(start):
            for filename in filenames:
                files.append(
                    os.path.relpath(os.path.join(dirname, filename), home))
        files = sorted(files)

        lines = []
        for filename in files:
            if links:
                lines.append(
                    '<li><a href="%s">%s</a></li>' % (filename, filename))
            else:
                lines.append('<li>%s</li>' % filename)

        return lines

    def get_assets(self):
        """Renders course assets view."""

        template_values = {}
        template_values['page_title'] = self.format_title('Assets')

        lines = []

        lines.append('<h3>Content Location</h3>')
        lines.append('<blockquote>%s</blockquote>' % sites.abspath(
            self.app_context.get_home_folder(), '/'))

        lines.append('<h3>Course Data Files</h3>')
        lines.append('<ol>')
        lines += self.list_and_format_file_list('/data/')
        lines.append('</ol>')

        lines.append('<h3>Course Assets</h3>')
        lines.append('<ol>')
        lines += self.list_and_format_file_list('/assets/', True)
        lines.append('</ol>')

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
