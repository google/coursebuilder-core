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

"""Site administration functionality."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import cgi
import datetime
import os
from controllers import sites
from controllers.utils import ReflectiveRequestHandler
import jinja2
import webapp2
from google.appengine.api import users


class AdminHandler(webapp2.RequestHandler, ReflectiveRequestHandler):
    """Handles all pages and actions required for administration of site."""

    default_action = 'courses'
    get_actions = [default_action, 'server']
    post_actions = []

    def get(self):
        """Enforces rights to all GET operations."""
        if not users.get_current_user() or not users.is_current_user_admin():
            self.redirect('/')
            return
        return super(AdminHandler, self).get()

    def render_page(self, template_values):
        """Renders a page using provided template values."""
        template_values['user_nav'] = '%s | <a href="%s">Logout</a>' % (
            users.get_current_user().email(), users.create_logout_url('/'))
        template_values['top_nav'] = """
          <a href="/admin">Courses</a>
          <a href="/admin?action=server">Server Information</a>
          """
        template_values[
            'page_footer'] = 'Created on: %s' % datetime.datetime.now()

        jinja_environment = jinja2.Environment(
            loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))
        self.response.write(jinja_environment.get_template(
            'admin.html').render(template_values))

    def render_dict(self, source_dict, title):
        """Renders a dictionary ordered by keys."""
        keys = sorted(source_dict.keys())

        content = []
        content.append('<h3>%s</h3>' % title)
        content.append('<ol>')
        for key in keys:
            value = source_dict[key]
            content.append(
                '<li>%s: %s</li>' % (cgi.escape(key), cgi.escape(str(value))))
        content.append('</ol>')
        return '\n'.join(content)

    def get_server(self):
        """Shows server & application information page."""
        template_values = {}
        template_values['page_title'] = 'Course Builder - Server Information'

        yaml_content = []
        yaml_content.append('<h3>Contents of <code>app.yaml</code></h3>')
        yaml_content.append('<ul><pre>')
        yaml_lines = open(os.path.join(os.path.dirname(
            __file__), '../../app.yaml'), 'r').readlines()
        for line in yaml_lines:
            yaml_content.append('%s<br/>' % cgi.escape(line))
        yaml_content.append('</pre></ul>')

        template_values['main_content'] = ''.join(
            yaml_content) + self.render_dict(
                os.environ, 'Server Environment Variables')

        self.render_page(template_values)

    def get_courses(self):
        """Shows a list of all courses available on this site."""
        template_values = {}
        template_values['page_title'] = 'Course Builder - Courses'

        content = []
        content.append('<h3>Courses</h3>')
        content.append('<table>')
        content.append(
            '<tr><th>Context Path</th><th>Data Location</th><th>Name</th></tr>')
        courses = sites.get_all_courses()
        count = 0
        for course in courses:
            slug = course.get_slug()
            location = sites.abspath(course.get_home_folder(), '/')
            try:
                name = cgi.escape(course.get_environ()['course']['title'])
            except Exception as e:  # pylint: disable-msg=broad-except
                name = 'Error in course.yaml:<br/>%s' % cgi.escape(str(e))

            link = '<a href="%s">%s</a>' % (slug, name)

            content.append('<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                slug, location, link))
            count += 1

        content.append("""
            <tr><th colspan="3" align="right">Total: %s course(s)</th></tr>
            """ % count)
        content.append('</table>')

        template_values['main_content'] = ''.join(content)

        self.render_page(template_values)
