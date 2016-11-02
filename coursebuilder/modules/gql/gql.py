# Copyright 2016 Google Inc. All Rights Reserved.
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

"""A GraphQL server for Course Builder.

This module provides an implementation of GraphQL server for some of the core
Course Builder data types. See https://facebook.github.io/graphql/ for details
on GraphQL. The server is disabled by default; to enable it, set the flag
labelled "GraphQL" in the Advanced Site Settings page.

The GraphQL server is accessed using queries of the following form:
  https://my_cb.appspot.com/modules/gql/query?q=<GraphQL query string>
and the response is returned as a JSON structure including a payload in the
form:
  {
    "data": { ... }
    "errors": [err1, err2, ...]
  }

The service currently provides a limited subset of read-only access to Course
Builder data, sufficient to run the Guides module (/modules/guide). New fields
and data types can be exposed by customizing this module. See
http://graphene-python.org/ for more details on how to model data in GraphQL
using Python, but very briefly:
  * Objects exposed in the tree are subclasses of graphene.ObjectType
  * The data members of an object are fields of type graphene.<data type>
  * Each exposed field uses a render_* method to extract the data.

The tree exposed by the GraphQL service need not exactly model the tree of data
in either App Engine data store or in the server-side in-memory object model;
the key requirement is that the tree is suitable to the needs of front-end
clients. The current model is:
  Query
    +-- course(id: String)
          +-- id
          +-- title
          +-- unit(id: String)
                +-- id
                +-- title
                +-- header
                +-- footer
                +-- lesson(id: String)
                      +-- id
                      +-- title
                      +-- body
                +-- allLessons
                      +--- Relay connection for lessons
          +-- allUnits
                +-- Relay connection for units
          +-- enrollment
    +-- allCourses
          +-- Relay connection for courses
    +-- currentUser

This module includes a lightwight front-end for exploring the GraphQL service.
Connect to:
    https://<your_cb_instance>/modules/gql/_static/query/index.html
This will bring up a form where you can enter GraphQL queries against your
server and see the raw results returned.

Course Builder module developers may want to insert additional fields into
locations in the base CB GraphQL tree. See the test
gql_tests.TopLevelQueryTests.test_extensibility for an example of how to do
this.
"""

__author__ = [
    'John Orr (jorr@google.com)',
]

import graphene
import graphene.relay
import graphql
from graphql_relay.node import node as graphql_node
import logging
import os

import appengine_config

from common import jinja_utils
from common import utils as common_utils
from common import users
from controllers import sites
from controllers import utils
from models import config
from models import courses
from models import custom_modules
from models import roles
from models import transforms
from modules.courses import unit_outline


_TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'gql', 'templates')

# Character used as separator for compound id's
ID_SEP = ':'

custom_module = None


def _resolve_id(cls, node_id):
    # Resolve an opaque global id into an internal form
    resolved_id = graphql_node.from_global_id(node_id)
    assert resolved_id.type == cls.__name__
    return resolved_id.id


class CourseAwareObjectType(object):
    """Mixin providing methods for Graphene objects having a course context."""

    def __init__(self, app_context, course=None, course_view=None, **kwargs):
        super(CourseAwareObjectType, self).__init__(**kwargs)
        self.app_context = app_context
        self._course = course
        self._course_view = course_view

    @property
    def course(self):
        return self._course or courses.Course(None, self.app_context)

    @property
    def course_view(self):
        # StudentCourseView is expensive to build, so only construct it when
        # needed, and inherit from the parent if possible.
        if not self._course_view:
            self._course_view = self.get_course_view(
                self.course, self.get_student(self.app_context))
        return self._course_view

    @classmethod
    def get_course_view(cls, course, student):
        with common_utils.Namespace(course.app_context.namespace):
            return unit_outline.StudentCourseView(
                course, student=student,
                list_lessons_with_visible_names=True)

    def _get_template_env(self, handler, expanded_gcb_tags):
        app_context = self.course.app_context
        if expanded_gcb_tags:
            tags = expanded_gcb_tags.strip().split()
            tags_filter = lambda k, v: k in tags
        else:
            tags_filter = lambda k, v: True

        env = app_context.get_template_environ(
            app_context.get_current_locale(), [_TEMPLATES_DIR])
        env.filters['gcb_tags'] = jinja_utils.get_gcb_tags_filter(
            handler, tags_filter=tags_filter)
        return env

    def _get_template(self, handler, expanded_gcb_tags, template_file):
        return self._get_template_env(handler, expanded_gcb_tags).get_template(
            template_file)

    def _render(self, handler, expanded_gcb_tags, template_values,
                template_file):
        return self._get_template(
            handler, expanded_gcb_tags, template_file).render(
                template_values, autoescape=True)

    def expand_tags(self, text_with_tags, info):
        handler = info.context.request_context.get('handler')
        expanded_gcb_tags = info.context.request_context.get(
            'expanded_gcb_tags')
        try:
            handler.app_context = self.app_context
            return self._render(
                handler, expanded_gcb_tags, {'content': text_with_tags},
                'content_with_tags.html')
        finally:
            del handler.app_context

    @classmethod
    def get_student(cls, app_context):
        with common_utils.Namespace(app_context.namespace):
            _, student = utils.CourseHandler.get_user_and_student_or_transient()
            return student


class Lesson(CourseAwareObjectType, graphene.relay.Node):
    title = graphene.String()
    body = graphene.String()

    def __init__(self, app_context, unit, lesson, **kwargs):
        super(Lesson, self).__init__(app_context, **kwargs)
        self._lesson = lesson
        self._unit = unit

    @classmethod
    def get_node(cls, node_id, info):
        try:
            return cls.get_lesson(node_id)
        except:  # pylint: disable=bare-except
            logging.exception('Errors resolving node')
            return None

    def resolve_title(self, args, info):
        return self._lesson.title

    def resolve_body(self, args, info):
        if not self.course_view.is_visible(
                [self._unit.unit_id, self._lesson.lesson_id]):
            return None
        return self.expand_tags(self._lesson.objectives, info)

    @classmethod
    def _get_lesson_id(cls, course, unit, lesson):
        course_id = course.app_context.get_slug()
        unit_id = unit.unit_id
        lesson_id = lesson.lesson_id
        assert ID_SEP not in course_id
        return ID_SEP.join([course_id, str(unit_id), str(lesson_id)])

    @classmethod
    def get_lesson(cls, lesson_id):
        course_id, unit_id, lesson_id = lesson_id.split(ID_SEP)
        course = Course.get_course(course_id).course
        student = cls.get_student(course.app_context)
        course_view = cls.get_course_view(course, student)
        unit = course_view.find_element([unit_id]).course_element
        lesson = course_view.find_element([unit_id, lesson_id]).course_element
        if lesson:
            return Lesson(
                course.app_context, unit, lesson,
                course=course, course_view=course_view,
                id=cls._get_lesson_id(course, unit, lesson))
        else:
            return None

    @classmethod
    def get_all_lessons(cls, course, course_view, unit):
        return [
            Lesson(
                course.app_context, unit, lesson,
                course=course, course_view=course_view,
                id=cls._get_lesson_id(course, unit, lesson))
            for lesson in course_view.get_lessons(unit.unit_id)]


# TODO(jorr): Introduce a ToplLevel interface and make Unit, Assessment etc
# extend that
# TODO(jorr): Support for pre-, post- Assessments at Lesson containment level.
class Unit(CourseAwareObjectType, graphene.relay.Node):
    title = graphene.String()
    description = graphene.String()
    all_lessons = graphene.relay.ConnectionField(Lesson)
    lesson = graphene.Field(Lesson, id=graphene.String())
    header = graphene.String()
    footer = graphene.String()

    def __init__(self, app_context, unit, **kwargs):
        super(Unit, self).__init__(app_context, **kwargs)
        self._unit = unit

    @classmethod
    def get_node(cls, node_id, info):
        try:
            return cls.get_unit(node_id)
        except:  # pylint: disable=bare-except
            logging.exception('Errors resolving node')
            return None

    @classmethod
    def _get_unit_id(cls, course, unit):
        course_id = course.app_context.get_slug()
        unit_id = unit.unit_id
        assert ID_SEP not in course_id
        return ID_SEP.join([course_id, str(unit_id)])

    @classmethod
    def get_unit(cls, unit_id):
        course_id, unit_id = unit_id.split(ID_SEP)
        course = Course.get_course(course_id).course
        student = cls.get_student(course.app_context)
        course_view = cls.get_course_view(course, student)
        unit = course_view.find_element([unit_id]).course_element
        if unit:
            return Unit(
                course.app_context, unit,
                course=course, course_view=course_view,
                id=cls._get_unit_id(course, unit))
        else:
            return None

    @classmethod
    def get_all_units(cls, course, course_view):
        return [
            Unit(
                course.app_context, unit,
                course=course, course_view=course_view,
                id=cls._get_unit_id(course, unit))
            for unit in course_view.get_units()
        ]

    def resolve_title(self, args, info):
        return self._unit.title

    def resolve_description(self, args, info):
        return self._unit.description

    def resolve_header(self, args, info):
        if not self.course_view.is_visible([self._unit.unit_id]):
            return None
        return self.expand_tags(self._unit.unit_header, info)

    def resolve_footer(self, args, info):
        if not self.course_view.is_visible([self._unit.unit_id]):
            return None
        return self.expand_tags(self._unit.unit_footer, info)

    def resolve_all_lessons(self, args, info):
        return Lesson.get_all_lessons(self.course, self.course_view, self._unit)

    def resolve_lesson(self, args, info):
        try:
            lesson_id = _resolve_id(Lesson, args['id'])
            return Lesson.get_lesson(lesson_id)
        except:  # pylint: disable=bare-except
            logging.exception('Error resolving lesson')
            return None


class Enrollment(graphene.ObjectType):
    # TODO(jorr): Make Enrollment extend CourseAwareObjectType because we may
    # need to be namespace-aware for some student properties. (See
    # coursebuilder-deployments/ignitecs/modules/mod_ignitecs/ignitecs.py
    # resolve_enrollment_tracks() for an example.)
    email = graphene.String()
    is_transient = graphene.Boolean(deprecation_reason='Replaced by enrolled')
    enrolled = graphene.Boolean()

    def __init__(self, student, **kwargs):
        super(Enrollment, self).__init__(**kwargs)
        self._student = student

    def resolve_email(self, args, info):
        if self._student.is_transient:
            return None
        return self._student.email

    def resolve_is_transient(self, args, info):
        return self._student.is_transient

    def resolve_enrolled(self, args, info):
        return not self._student.is_transient


class CurrentUser(graphene.ObjectType):
    email = graphene.String()
    logged_in = graphene.Boolean()
    login_url = graphene.Field(graphene.String(), dest_url=graphene.String())
    logout_url = graphene.Field(graphene.String(), dest_url=graphene.String())
    can_view_dashboard = graphene.Boolean()

    def __init__(self, user, **kwargs):
        super(CurrentUser, self).__init__(**kwargs)
        self._user = user

    def resolve_email(self, args, info):
        return self._user.email() if self._user else None

    def resolve_logged_in(self, args, info):
        return bool(self._user)

    def resolve_login_url(self, args, info):
        return users.create_login_url(dest_url=args['dest_url'])

    def resolve_logout_url(self, args, info):
        return users.create_logout_url(dest_url=args['dest_url'])

    def resolve_can_view_dashboard(self, args, info):
        # TODO(nretallack): Ideally this would return true if you have the right
        # to see any dashboard feature in any course. How can we determine that
        # quickly?
        return roles.Roles.is_super_admin()


class Course(CourseAwareObjectType, graphene.relay.Node):
    title = graphene.String()
    all_units = graphene.relay.ConnectionField(Unit)
    unit = graphene.Field(Unit, id=graphene.String())
    # If the current user is registered in this course, enrollment is an
    # object exposing fields for the student object; otherwise it represents a
    # transient student.
    enrollment = graphene.Field(Enrollment)
    abstract = graphene.String()
    instructor_details = graphene.String()
    url = graphene.String()
    open_for_registration = graphene.Boolean()
    show_in_explorer = graphene.Boolean()

    @property
    def course_environ(self):
        with common_utils.Namespace(self.app_context.namespace):
            return courses.Course.get_environ(self.app_context)

    @classmethod
    def get_node(cls, node_id, info):
        try:
            return cls.get_course(node_id)
        except:  # pylint: disable=bare-except
            logging.exception('Errors resolving node')
            return None

    @classmethod
    def _is_visible(cls, app_context):
        with common_utils.Namespace(app_context.namespace):
            return sites.can_handle_course_requests(app_context)

    @classmethod
    def get_course(cls, course_id):
        app_context = sites.get_course_for_path(course_id)
        if not app_context or app_context.get_slug() != course_id:
            return None
        if cls._is_visible(app_context):
            return Course(app_context, id=app_context.get_slug())
        return None

    @classmethod
    def get_all_courses(cls):
        all_courses = []
        for app_context in sites.get_all_courses():
            if cls._is_visible(app_context):
                all_courses.append(Course(
                    app_context=app_context, id=app_context.get_slug()))
        return all_courses

    def resolve_title(self, args, info):
        return courses.Course.get_named_course_setting_from_environ(
            'title', self.course_environ)

    def resolve_all_units(self, args, info):
        return Unit.get_all_units(self.course, self.course_view)

    def resolve_unit(self, args, info):
        try:
            unit_id = _resolve_id(Unit, args['id'])
            return Unit.get_unit(unit_id)
        except:  # pylint: disable=bare-except
            logging.exception('Errors resolving unit')
            return None

    def resolve_enrollment(self, args, info):
        return Enrollment(self.get_student(self.app_context))

    def resolve_abstract(self, args, info):
        abstract = courses.Course.get_named_course_setting_from_environ(
            'blurb', self.course_environ)
        return self.expand_tags(abstract, info)

    def resolve_instructor_details(self, args, info):
        details = courses.Course.get_named_course_setting_from_environ(
            'instructor_details', self.course_environ)
        return self.expand_tags(details, info)

    def resolve_url(self, args, info):
        return self.app_context.get_slug()

    def resolve_open_for_registration(self, args, info):
        return bool(courses.Course.get_named_reg_setting_from_environ(
            'can_register', self.course_environ, default=False))

    def resolve_show_in_explorer(self, args, info):
        return bool(courses.Course.get_named_course_setting_from_environ(
            'show_in_explorer', self.course_environ, default=True))


class Query(graphene.ObjectType):
    """'Query' represents the root node of the GraphQL tree."""

    course = graphene.Field(Course, id=graphene.String())
    all_courses = graphene.relay.ConnectionField(Course)
    current_user = graphene.Field(CurrentUser)
    node = graphene.relay.NodeField()

    def resolve_course(self, args, info):
        try:
            course_id = _resolve_id(Course, args['id'])
            return Course.get_course(course_id)
        except:  # pylint: disable=bare-except
            common_utils.log_exception_origin()
            logging.exception('Error resolving course')
            return None

    def resolve_all_courses(self, args, info):
        try:
            return Course.get_all_courses()
        except:  # pylint: disable=bare-except
            common_utils.log_exception_origin()
            raise

    def resolve_current_user(self, args, info):
        try:
            return CurrentUser(users.get_current_user())
        except:  # pylint: disable=bare-except
            common_utils.log_exception_origin()
            raise


class GraphQLRestHandler(utils.BaseRESTHandler):
    URL = '/modules/gql/query'

    def _get_response_dict(self, query_str, expanded_gcb_tags):
        if not query_str:
            return {
                'data': None,
                'errors': ['Missing required query parameter "q"']
            }

        schema = graphene.Schema(query=Query)
        try:
            result = schema.execute(
                request=query_str,
                request_context={
                    'handler': self,
                    'expanded_gcb_tags': expanded_gcb_tags,
                })
            for err in result.errors:
                logging.error('GraphQL schema.execute error: %s', err)
            return {
                'data': result.data,
                'errors': [err.message for err in result.errors]
            }
        except graphql.core.error.GraphQLError as err:
            if not appengine_config.PRODUCTION_MODE:
                log_level = logging.exception
            else:
                log_level = logging.error
            log_level('GraphQL error with query: %s', query_str)
            return {
                'data': None,
                'errors': [err.message]
            }

    def _send_response(self, status_code, response):
        self.response.set_status(status_code)
        self.response.headers[
            'Content-Type'] = 'application/javascript; charset=utf-8'
        self.response.headers['X-Content-Type-Options'] = 'nosniff'
        self.response.headers['Content-Disposition'] = 'attachment'
        self.response.write(
            transforms.JSON_XSSI_PREFIX + transforms.dumps(response))

    def get(self):
        if not GQL_SERVICE_ENABLED.value:
            self.error(404)
            return

        query_str = self.request.get('q')
        expanded_gcb_tags = self.request.get('expanded_gcb_tags')
        response_dict = self._get_response_dict(query_str, expanded_gcb_tags)
        status_code = 400 if response_dict['errors'] else 200
        self._send_response(status_code, response_dict)


GQL_SERVICE_ENABLED = config.ConfigProperty(
    'gcb_gql_service_enabled', bool, 'Enable the GraphQL REST endpoint.',
    default_value=True, label='GraphQL')


def register_module():

    global_routes = [(GraphQLRestHandler.URL, GraphQLRestHandler)]

    namespaced_routes = []

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'GraphQL',
        'Handles queries for Course Builder in GraphQL.',
        global_routes, namespaced_routes)

    return custom_module
