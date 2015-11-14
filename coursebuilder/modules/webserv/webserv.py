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

"""Webserv, a module for static content publishing.

  TODO(psimakov):
      - cache various streams (and especially md/jinja) in memcache
      - make sure gcb tags expand properly

"""

__author__ = 'Pavel Simakov (psimakov@google.com)'


import collections
import mimetypes
import os
import re

import markdown

import appengine_config
from common import jinja_utils
from common import schema_fields
from controllers import sites
from controllers import utils
from models import courses
from models import custom_modules
from modules.courses import lessons
from modules.courses import settings


WEBSERV_SETTINGS_SCHEMA_SECTION = 'modules:webserv'
WEBSERV_ENABLED = 'enabled'
WEBSERV_SLUG = 'slug'
WEBSERV_DOC_ROOTS_DIR_NAME = 'document_roots'
WEBSERV_DOC_ROOT = 'doc_root'
WEBSERV_JINJA_ENABLED = 'jinja_enabled'
WEBSERV_MD_ENABLED = 'md_enabled'

BANNED_SLUGS = set(['admin', 'dashboard'])
GOOD_SLUG_REGEX = '^[A-Za-z0-9_-]*$'

ADMIN_HOME_PAGE = '/admin/welcome'
COURSE_HOME_PAGE = '/course?use_last_location=true'
WEBSERV_HOME_PAGE = 'index.html'

webserv_module = None


def get_config(app_context):
    return app_context.get_environ().get(
        'modules', {}).get('webserv', {})


def make_doc_root_select_data():
    select_data = []
    for _, dirs, _ in os.walk(os.path.join(
            os.path.abspath(os.path.dirname(__file__)),
            WEBSERV_DOC_ROOTS_DIR_NAME)):
        for adir in dirs:
            select_data.append((adir, adir))
        del dirs[:]
    return select_data


def slug_validator(value, errors):
    if value:
        if value in BANNED_SLUGS:
            errors.append('Slug value of %s is not allowed' % value)
        if not re.match(GOOD_SLUG_REGEX, value):
            errors.append(
                'Slug value %s contains invalid characters; '
                'valid characters are A..Z, a..z, 0..9, _ and -.' % value)


class RootHandler(utils.ApplicationHandler):
    """Handles routing to '/'."""

    def get(self):
        index = sites.get_course_index()
        if index.get_all_courses():
            course = index.get_course_for_path('/')
            if not course:
                course = index.get_all_courses()[0]
            config = get_config(course)
            if config.get(WEBSERV_ENABLED):
                location = WEBSERV_HOME_PAGE
            else:
                location = COURSE_HOME_PAGE
            self.redirect(utils.ApplicationHandler.canonicalize_url_for(
                course, location))
        else:
            self.redirect(ADMIN_HOME_PAGE)


class WebServer(lessons.CourseHandler, utils.StarRouteHandlerMixin):
    """A class that will handle web requests."""

    def get_mime_type(self, filename, default='application/octet-stream'):
        guess = mimetypes.guess_type(filename)[0]
        if guess is None:
            return default
        return guess

    def norm_path(self, app_context, config, path):
        course_slug = app_context.get_slug()
        slug = '/%s' % config.get(WEBSERV_SLUG)
        if path and path.startswith(course_slug):
            path = sites.unprefix(path, course_slug)
        if path and path.startswith(slug):
            path = sites.unprefix(path, slug)
        return path

    def get_path(self, config):
        path = self.norm_path(self.app_context, config, self.request.path)
        if path == '/':
            path = '/index.html'
        return os.path.normpath(path)

    def prepare_metadata(self):
        self.init_template_values(self.app_context.get_environ())
        self.template_value['gcb_os_env'] = os.environ
        self.template_value['gcb_course_env'] = self.app_context.get_environ()
        metadata = {}
        metadata.update(self.template_value.items())
        del metadata['course_info']
        return collections.OrderedDict(sorted(metadata.items())).items()

    def render_jinja(self, config, relname=None, from_string=None):
        assert relname or from_string
        template_dirs = [
            os.path.join(
                appengine_config.BUNDLE_ROOT, 'modules', 'webserv',
                WEBSERV_DOC_ROOTS_DIR_NAME, config.get(WEBSERV_DOC_ROOT)),
            os.path.join(
                appengine_config.BUNDLE_ROOT, 'views')]

        if from_string:
            template = jinja_utils.create_and_configure_jinja_environment(
                template_dirs, handler=self).from_string(from_string)
        else:
            template = jinja_utils.get_template(
                relname, template_dirs, handler=self)

        self.response.headers['Content-Type'] = 'text/html'
        self.template_value['gcb_webserv_metadata'] = self.prepare_metadata()
        self.response.write(template.render(self.template_value))

    def do_plain(self, config, filename, relname):
        with open(filename, 'r') as stream:
            self.response.headers[
                'Content-Type'] = self.get_mime_type(filename)
            self.response.write(stream.read())

    def do_html(self, config, filename, relname):
        if not config.get(WEBSERV_JINJA_ENABLED):
            self.do_plain(config, filename, relname)
            return

        self.render_jinja(config, relname=relname)

    def do_markdown(self, config, filename, relname):
        if not config.get(WEBSERV_MD_ENABLED):
            self.do_plain(config, filename, relname)
            return

        text = markdown.markdown(open(filename, 'r').read())
        if config.get(WEBSERV_JINJA_ENABLED):
            self.render_jinja(config, from_string=text)
            return

        self.response.headers['Content-Type'] = 'text/html'
        self.response.write(text)

    def serve_resource(self, config):
        doc_root = config.get(WEBSERV_DOC_ROOT)
        if not doc_root:
            self.error(404)
            return

        doc_root = os.path.normpath(doc_root)
        relname = self.get_path(config)
        filename = os.path.join(
            os.path.abspath(os.path.dirname(__file__)),
            WEBSERV_DOC_ROOTS_DIR_NAME, doc_root) + relname
        if not os.path.isfile(filename):
            self.error(404)
            return

        _, ext = os.path.splitext(filename)
        if ext:
            ext = ext[1:]
        extension_to_target = {'html': self.do_html, 'md': self.do_markdown}
        target = extension_to_target.get(ext, self.do_plain)
        target(config, filename, relname)

    def get(self):
        processor = None
        config = get_config(self.app_context)
        if config.get(WEBSERV_ENABLED):
            self.serve_resource(config)
        else:
            if self.path_translated in ['/', '/course']:
                super(WebServer, self).get()
            else:
                self.error(404)


def get_schema_fields():
    enabled = schema_fields.SchemaField(
        WEBSERV_SETTINGS_SCHEMA_SECTION + ':' + WEBSERV_ENABLED,
        'Enabled', 'boolean', optional=True, i18n=False,
        description='Whether to enable static content serving '
            'for this course.')
    slug = schema_fields.SchemaField(
        WEBSERV_SETTINGS_SCHEMA_SECTION + ':' + WEBSERV_SLUG,
        'Path', 'string', optional=True, i18n=False,
        validator=slug_validator,
        description='A path where static content will be accessible. '
            'If value of "sample" is specified, the content will be '
            'accessible at the URL "/sample". Leave this value blank to '
            'access the content at the URL "/".')
    doc_root = schema_fields.SchemaField(
        WEBSERV_SETTINGS_SCHEMA_SECTION + ':' + WEBSERV_DOC_ROOT,
        'Document Root', 'string', optional=False, i18n=False,
        select_data=make_doc_root_select_data(),
        description='A folder containing static resources. '
            'It must be part of your deployment and located under '
            '/modules/webserv/document_roots/.')
    enabled_jinja = schema_fields.SchemaField(
        WEBSERV_SETTINGS_SCHEMA_SECTION + ':' + WEBSERV_JINJA_ENABLED,
        'Templating Enabled', 'boolean', optional=True, i18n=False,
        description='Whether to apply Jinja Template Processor to *.html '
            'files before serving them.')
    enabled_md = schema_fields.SchemaField(
        WEBSERV_SETTINGS_SCHEMA_SECTION + ':' + WEBSERV_MD_ENABLED,
        'Markdown Enabled', 'boolean', optional=True, i18n=False,
        description='Whether to apply Markdown Processor to *.md '
            'files before serving them.')
    return (
        lambda _: enabled, lambda _: slug, lambda _: doc_root,
        lambda _: enabled_jinja, lambda _: enabled_md)


def register_module():
    """Registers this module in the registry."""

    def notify_module_enabled():
        courses.Course.OPTIONS_SCHEMA_PROVIDERS[
            WEBSERV_SETTINGS_SCHEMA_SECTION] += get_schema_fields()
        settings.CourseSettingsHandler.register_settings_section(
            WEBSERV_SETTINGS_SCHEMA_SECTION, title='Web server ')

    global_routes = [('/', RootHandler)]
    namespaced_routes = [('/', WebServer)]

    global webserv_module  # pylint: disable=global-statement
    webserv_module = custom_modules.Module(
        'Webserv, a module for static content serving.',
        'A simple way to publish static web pages with your course content.',
        global_routes, namespaced_routes,
        notify_module_enabled=notify_module_enabled)

    return webserv_module
