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

"""Functional tests for the GraphQL service."""

__author__ = [
    'John Orr (jorr@google.com)',
]

import graphene
from graphql_relay.node import node as graphql_node
import urllib

import appengine_config
from common import utils as common_utils
from controllers import sites
from models import config
from models import courses
from models import transforms
from modules.gql import gql
from tests.functional import actions

from google.appengine.ext import db

ADMIN_EMAIL = 'admin@foo.com'
COURSE_NAME = 'gql'
NAMESPACE = 'ns_%s' % COURSE_NAME
STUDENT_EMAIL = 'student@foo.com'
STUDENT_NAME = 'A. Student'


def get_course_id(internal_course_id):
    return graphql_node.to_global_id('Course', internal_course_id)


def get_unit_id(internal_course_id, internal_unit_id):
    return graphql_node.to_global_id('Unit', ':'.join(
        [internal_course_id, str(internal_unit_id)]))


def get_lesson_id(internal_course_id, internal_unit_id, internal_lesson_id):
    return graphql_node.to_global_id('Lesson', ':'.join(
        [internal_course_id, str(internal_unit_id), str(internal_lesson_id)]))


class BaseGqlTests(actions.TestBase):

    GRAPHQL_REST_HANDLER_URL = '/modules/gql/query'

    def tearDown(self):
        config.Registry.test_overrides.clear()
        super(BaseGqlTests, self).tearDown()

    def set_service_enabled(self, is_enabled):
        with common_utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):
            name = 'gcb_gql_service_enabled'
            try:
                entity = config.ConfigPropertyEntity.get_by_key_name(name)
            except db.BadKeyError:
                entity = None
            if not entity:
                entity = config.ConfigPropertyEntity(key_name=name)
            entity.value = str(is_enabled)
            entity.is_draft = False
            entity.put()

    def query(self, query_str, expanded_gcb_tags=None):
        if query_str is None:
            query_url = self.GRAPHQL_REST_HANDLER_URL
        else:
            query_url = '%s?%s' % (
                self.GRAPHQL_REST_HANDLER_URL,
                urllib.urlencode({'q': query_str}))
            if expanded_gcb_tags:
                query_url += '&' + urllib.urlencode(
                    {'expanded_gcb_tags': expanded_gcb_tags})
        return self.get(query_url, expect_errors=True)

    def get_response(self, query_str, expanded_gcb_tags=None,
                     expect_errors=False):
        response = self.query(query_str, expanded_gcb_tags=expanded_gcb_tags)
        response_dict = transforms.loads(response.body)

        if expect_errors:
            self.assertEquals(400, response.status_int)
            self.assertIsNone(response_dict['data'])
            self.assertTrue(response_dict['errors'])
        else:
            self.assertEquals(200, response.status_int)
            self.assertIsNotNone(response_dict['data'])
            self.assertFalse(response_dict['errors'])

        return response_dict


class GraphQLRestHandlerTests(BaseGqlTests):
    """Tests for basic access control and data flow of the REST handler."""

    BAD_QUERY = 'allCourses { unknownField }'

    COURSE_LIST_QUERY = (
        '{'
        '  allCourses(first: 1) {'
        '    edges {'
        '      node { ... on Course {'
        '        title }}}}}')

    ENROLLMENT_QUERY = (
        '{allCourses (first: 1) { edges { node { enrollment {'
        '  email enrolled }}}}}')

    USER_QUERY = '{currentUser { loggedIn email }}'

    def test_access_control(self):
        # By default the service is enabled.
        response = self.get_response(self.COURSE_LIST_QUERY)
        self.assertEquals(
            {'allCourses': {'edges': [{'node': {
                'title': 'Power Searching with Google'}}]}},
            response['data'])

        # Explicitly disable the service and it's unavailable.
        self.set_service_enabled(False)
        response = self.query(self.COURSE_LIST_QUERY)
        self.assertEquals(404, response.status_int)

    def test_user_is_available_to_graphql_engine(self):
        self.set_service_enabled(True)

        response = self.get_response(self.USER_QUERY)
        self.assertEquals(
            {'currentUser': {'loggedIn': False, 'email': None}},
            response['data'])

        actions.login(STUDENT_EMAIL, is_admin=False)

        response = self.get_response(self.USER_QUERY)
        self.assertEquals(
            {'currentUser': {'loggedIn': True, 'email': STUDENT_EMAIL}},
            response['data'])

    def test_student_is_available_to_graphql_engine(self):
        self.set_service_enabled(True)

        response = self.get_response(self.ENROLLMENT_QUERY)
        self.assertEquals(
            {'allCourses': {'edges': [{'node': {
                'enrollment': {'enrolled': False, 'email': None}}}]}},
            response['data'])

        actions.login(STUDENT_EMAIL, is_admin=False)
        actions.register(self, STUDENT_NAME)

        response = self.get_response(self.ENROLLMENT_QUERY)
        self.assertEquals(
            {'allCourses': {'edges': [{'node': {
                'enrollment': {
                    'enrolled': True, 'email': STUDENT_EMAIL}}}]}},
            response['data'])

    def test_error_messages_are_returned_in_response(self):
        self.set_service_enabled(True)

        response = self.get_response(self.BAD_QUERY, expect_errors=True)
        self.assertEquals(
            [
                'Syntax Error GraphQL request (1:1) '
                'Unexpected Name "allCourses"\n\n'
                '1: allCourses { unknownField }\n'
                '   ^\n'],
            response['errors'])

    def test_error_on_empty_or_missing_query(self):
        self.set_service_enabled(True)

        # Empty query
        response = self.get_response('', expect_errors=True)
        self.assertEquals(
            ['Missing required query parameter "q"'],
            response['errors'])

        # Missing query
        response = self.get_response(None, expect_errors=True)
        self.assertEquals(
            ['Missing required query parameter "q"'],
            response['errors'])


class GraphQLTreeTests(BaseGqlTests):
    """Tests for the object model in the GraphQL tree."""

    def setUp(self):
        super(GraphQLTreeTests, self).setUp()
        self.set_service_enabled(True)

    def tearDown(self):
        courses.Course.ENVIRON_TEST_OVERRIDES = {}
        super(GraphQLTreeTests, self).tearDown()

    def set_course_availability(self, availability):
        settings = courses.COURSE_AVAILABILITY_POLICIES[availability]
        courses.Course.ENVIRON_TEST_OVERRIDES = {
            'course': {
                'now_available': settings['now_available'],
                'browsable': settings['browsable'],
            },
            'reg_form': {
                'can_register': settings['can_register']
            }
        }


class TopLevelQueryTests(GraphQLTreeTests):

    def test_top_level_query_fields(self):
        response = self.get_response(
            '{__type (name: "Query") {'
            '    fields { name type { name kind }}}}')

        expected_fields = [
            {'name': 'course', 'type': {
                'kind': 'OBJECT', 'name': 'Course'}},
            {'name': 'allCourses', 'type': {
                'kind': 'OBJECT', 'name': 'CourseDefaultConnection'}},
            {'name': 'currentUser', 'type': {
                'kind': 'OBJECT', 'name': 'CurrentUser'}},
            {'name': 'node', 'type': {
                'kind': 'INTERFACE', 'name': 'Node'}},
        ]

        for field in response['data']['__type']['fields']:
            for expected_field in expected_fields:
                if field == expected_field:
                    expected_fields.remove(expected_field)

        self.assertEquals(expected_fields, [])

    def test_course_access_private(self):
        self.set_course_availability(courses.COURSE_AVAILABILITY_PRIVATE)

        # An admin can list and access private courses
        actions.login(ADMIN_EMAIL, is_admin=True)
        response = self.get_response(
            '{allCourses(first: 1) {edges {node {id}}}}')
        course_id = response['data']['allCourses']['edges'][0]['node']['id']
        self.assertIsNotNone(course_id)
        response = self.get_response('{course(id: "%s") {id}}' % course_id)
        self.assertIsNotNone(response['data']['course']['id'])
        response = self.get_response('{node(id: "%s") {id}}' % course_id)
        self.assertIsNotNone(response['data']['node']['id'])

        # ...but a student cannot
        actions.login(STUDENT_EMAIL)
        response = self.get_response(
            '{allCourses(first: 1) {edges {node {id}}}}')
        self.assertEquals([], response['data']['allCourses']['edges'])
        response = self.get_response('{course(id: "%s") {id}}' % course_id)
        self.assertIsNone(response['data']['course'])
        response = self.get_response('{node(id: "%s") {id}}' % course_id)
        self.assertIsNone(response['data']['node'])

    def test_course_access_public(self):
        self.set_course_availability(courses.COURSE_AVAILABILITY_PUBLIC)

        # Anonymous user can list and view
        response = self.get_response(
            '{allCourses(first: 1) {edges {node {id}}}}')
        course_id = response['data']['allCourses']['edges'][0]['node']['id']
        self.assertIsNotNone(course_id)
        response = self.get_response('{course(id: "%s") {id}}' % course_id)
        self.assertIsNotNone(response['data']['course']['id'])
        response = self.get_response('{node(id: "%s") {id}}' % course_id)
        self.assertIsNotNone(response['data']['node']['id'])

    def test_course_query_unmatched(self):
        response = self.get_response('{course(id: "unmatched") { id }}')
        self.assertIsNone(response['data']['course'])

    def test_extensibility(self):
        """Test to illustrate how modules can add fields into the tree.

        The added field must be provided a resolver function in its constructor
        and it is then added onto the appropriate node in the graph.
        """

        # The resolver. Note that this will be bound to the target
        # graphene.ObjectType so its first arg is the object it is bound to.
        def resolve_extension(query_obj, args, info):
            return 'Extension[%s]' % args['id']

        # Instantiate the field with the resolver passed in and then add to the
        # class representing the target node in the graph.
        extension = graphene.String(
            resolver=resolve_extension, id=graphene.String())
        gql.Query.add_to_class('extension', extension)

        response = self.get_response('{ extension(id: "five") }')
        self.assertEquals('Extension[five]', response['data']['extension'])

        # Force a reload of the gql classes in order to clear out the extension
        reload(gql)


class CourseSettingsTests(GraphQLTreeTests):
    def setUp(self):
        super(CourseSettingsTests, self).setUp()
        self.base = '/' + COURSE_NAME
        self.course_id = get_course_id(self.base)
        app_context = actions.update_course_config_as_admin(
            COURSE_NAME, ADMIN_EMAIL, {
                'course': {
                    'title': COURSE_NAME,
                    'admin_user_emails': ADMIN_EMAIL,
                    'now_available': True,
                    'browsable': True,
                    'blurb': '<p>Course Abstract</p>',
                    'instructor_details': '<p>Instructor</p>',
                },
            })

    def test_registration_required(self):
        self.set_course_availability(
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED)

        self.assertEquals(
            self.get_response("""
            {
                course (id: "%s") {
                    abstract,
                    instructorDetails,
                    url,
                    openForRegistration
                }
            }""" % self.course_id
            ), {
                'data': {
                    'course': {
                        'abstract': '<p>Course Abstract</p>',
                        'instructorDetails': '<p>Instructor</p>',
                        'url': '/' + COURSE_NAME,
                        'openForRegistration': True,
                    },
                },
                'errors': [],
            })

    def test_registration_disabled(self):
        self.set_course_availability(
            courses.COURSE_AVAILABILITY_PUBLIC)

        self.assertEquals(
            self.get_response(
                '{course (id: "%s") {openForRegistration}}' % self.course_id
            ), {
                'data': {
                    'course': {
                        'openForRegistration': False,
                    },
                },
                'errors': [],
            })

    def test_markup_in_abstract(self):
        with actions.OverriddenEnvironment(
            {'course': {'blurb':
                        '<gcb-markdown instanceid="j7UKhedk1arY">\n'
                        'foo\n'
                        '# bar\n'
                        '### baz\n'
                        '</gcb-markdown>'}}):
            response = self.get_response(
                '{course (id: "%s") { abstract } }' % self.course_id)
            self.assertEquals(
                response['data']['course']['abstract'],
                '<div><link href="/modules/core_tags/_static/css/markdown.css" '
                'rel="stylesheet"/></div><div><div class="gcb-markdown">'
                '<p>foo</p>\n<h1>bar</h1>\n<h3>baz</h3></div></div><div></div>')

    def test_markup_in_instructor_details(self):
        with actions.OverriddenEnvironment(
            {'course': {'instructor_details':
                        '<gcb-markdown instanceid="j7UKhedk1arY">\n'
                        'foo\n'
                        '# bar\n'
                        '### baz\n'
                        '</gcb-markdown>'}}):
            response = self.get_response(
                '{course (id: "%s") { instructorDetails } }' % self.course_id)
            self.assertEquals(
                response['data']['course']['instructorDetails'],
                '<div><link href="/modules/core_tags/_static/css/markdown.css" '
                'rel="stylesheet"/></div><div><div class="gcb-markdown">'
                '<p>foo</p>\n<h1>bar</h1>\n<h3>baz</h3></div></div><div></div>')


class CourseTests(GraphQLTreeTests):

    def setUp(self):
        super(CourseTests, self).setUp()
        self.base = '/' + COURSE_NAME
        app_context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, COURSE_NAME)
        self.course = courses.Course(None, app_context)
        self.unit = self.course.add_unit()
        self.unit.title = 'Test Unit'
        self.course.save()

        self.course_id = get_course_id(self.base)
        self.unit_id = get_unit_id(self.base, self.unit.unit_id)

        self.set_course_availability(
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED)

        actions.login(ADMIN_EMAIL)

    def tearDown(self):
        sites.reset_courses()
        super(CourseTests, self).tearDown()

    def test_course_fields(self):
        response = self.get_response(
            '{__type (name: "Course") {'
            '    fields { name type { name kind ofType {name} }}}}')

        expected_fields = [
            {'name': 'id', 'type': {
                'kind': 'NON_NULL', 'name': None,
                'ofType': {'name': 'ID'}}},
            {'name': 'title', 'type': {
                'kind': 'SCALAR', 'name': 'String', 'ofType': None}},
            {'name': 'allUnits', 'type': {
                'kind': 'OBJECT', 'name': 'UnitDefaultConnection',
                'ofType': None}},
            {'name': 'unit', 'type': {
                'kind': 'OBJECT', 'name': 'Unit', 'ofType': None}},
            {'name': 'enrollment', 'type': {
                'kind': 'OBJECT', 'name': 'Enrollment', 'ofType': None}},
            {'name': 'abstract', 'type': {
                'kind': 'SCALAR', 'name': 'String', 'ofType': None}},
            {'name': 'instructorDetails', 'type': {
                'kind': 'SCALAR', 'name': 'String', 'ofType': None}},
            {'name': 'url', 'type': {
                'kind': 'SCALAR', 'name': 'String', 'ofType': None}},
            {'name': 'openForRegistration', 'type': {
                'kind': 'SCALAR', 'name': 'Boolean', 'ofType': None}},
            {'name': 'showInExplorer', 'type': {
                'kind': 'SCALAR', 'name': 'Boolean', 'ofType': None}},
        ]

        for field in response['data']['__type']['fields']:
            for expected_field in expected_fields:
                if field == expected_field:
                    expected_fields.remove(expected_field)

        self.assertEquals(expected_fields, [])

    def test_node_access(self):
        response = self.get_response('{node(id: "%s") {id}}' % self.course_id)
        self.assertEquals(self.course_id, response['data']['node']['id'])

    def test_course_title(self):
        response = self.get_response(
            '{course(id: "%s") {title}}' % self.course_id)
        self.assertEquals('gql', response['data']['course']['title'])

    def test_unit_access_available(self):
        actions.logout()

        self.unit.availability = courses.AVAILABILITY_AVAILABLE
        self.course.save()

        # Access single unit
        response = self.get_response(
            '{course (id: "%s") {unit(id: "%s") { title } }}' % (
                self.course_id, self.unit_id))
        self.assertEquals(
            self.unit.title, response['data']['course']['unit']['title'])

        # Access unit list
        response = self.get_response(
            '{course(id: "%s") {allUnits {edges {node {'
            '  ... on Unit {id title}}}}}}' % self.course_id)
        edges = response['data']['course']['allUnits']['edges']
        self.assertEquals(1, len(edges))
        self.assertEquals(self.unit.title, edges[0]['node']['title'])

    def test_unit_access_unavailable(self):
        actions.logout()

        self.unit.availability = courses.AVAILABILITY_UNAVAILABLE
        self.course.save()

        # Access single unit
        response = self.get_response(
            '{course(id: "%s") {unit(id: "%s") {title} }}' % (
                self.course_id, self.unit_id))
        self.assertIsNone(response['data']['course']['unit'])

        # Access unit list
        response = self.get_response(
            '{course(id: "%s") {allUnits {edges {node {id}}}}}' % (
                self.course_id))
        self.assertEquals([], response['data']['course']['allUnits']['edges'])

    def test_enrollment(self):
        actions.logout()

        response = self.get_response(
            '{course(id: "%s") {enrollment {email enrolled}}}' % (
                self.course_id))
        enrollment = response['data']['course']['enrollment']
        self.assertEquals({'enrolled': False, 'email': None}, enrollment)

        actions.login(STUDENT_EMAIL)

        response = self.get_response(
            '{course(id: "%s") {enrollment {email enrolled}}}' % (
                self.course_id))
        enrollment = response['data']['course']['enrollment']
        self.assertEquals({'enrolled': False, 'email': None}, enrollment)

        actions.register(self, STUDENT_NAME)

        response = self.get_response(
            '{course (id: "%s") { enrollment { email enrolled}}}' % (
                self.course_id))
        enrollment = response['data']['course']['enrollment']
        self.assertEquals(
            {'enrolled': True, 'email': STUDENT_EMAIL}, enrollment)


class UserTests(GraphQLTreeTests):

    def test_user_fields(self):
        response = self.get_response(
            '{__type (name: "CurrentUser") { fields { name type { name } }}}')
        expected_data = {
            '__type': {
                'fields': [
                    {'type': {'name': 'String'}, 'name': 'email'},
                    {'type': {'name': 'Boolean'}, 'name': 'loggedIn'},
                    {'type': {'name': 'String'}, 'name': 'loginUrl'},
                    {'type': {'name': 'String'}, 'name': 'logoutUrl'},
                    {'type': {'name': 'Boolean'}, 'name': 'canViewDashboard'},
                ]}}
        self.assertEquals(expected_data, response['data'])

    def test_current_user(self):
        response = self.get_response('{currentUser { email loggedIn }}')
        currentUser = response['data']['currentUser']
        self.assertFalse(currentUser['loggedIn'])
        self.assertIsNone(currentUser['email'])

        actions.login(STUDENT_EMAIL)
        response = self.get_response('{currentUser { email loggedIn }}')
        currentUser = response['data']['currentUser']
        self.assertTrue(currentUser['loggedIn'])
        self.assertEquals(STUDENT_EMAIL, currentUser['email'])

    def test_login_logout_urls(self):
        continue_url = 'https://my.location.gr'
        response = self.get_response(
            '{currentUser {'
            '    loginUrl(destUrl: "%s")'
            '    logoutUrl(destUrl: "%s") }}' % (continue_url, continue_url))
        currentUser = response['data']['currentUser']
        self.assertEquals(
            'https://www.google.com/accounts/Login'
            '?continue=https%3A//my.location.gr',
            currentUser['loginUrl'])
        self.assertEquals(
            'https://www.google.com/accounts/Logout'
            '?continue=https%3A//my.location.gr',
            currentUser['logoutUrl'])


class EnrollmentTests(GraphQLTreeTests):

    def test_enrollment_fields(self):
        response = self.get_response(
            '{__type (name: "Enrollment") { fields { name type { name } }}}')
        expected_data = {
            '__type': {
                'fields': [
                    {'type': {'name': 'String'}, 'name': 'email'},
                    {'type': {'name': 'Boolean'}, 'name': 'enrolled'},
                ]}}
        self.assertEquals(expected_data, response['data'])


class UnitTests(GraphQLTreeTests):

    def setUp(self):
        super(UnitTests, self).setUp()
        self.base = '/' + COURSE_NAME
        app_context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, COURSE_NAME)
        self.course = courses.Course(None, app_context)
        self.unit = self.course.add_unit()
        self.unit.title = 'Test Unit'
        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.title = 'Test Lesson'
        self.lesson.objectives = 'Lesson body'
        self.course.save()

        self.course_id = get_course_id(self.base)
        self.unit_id = get_unit_id(self.base, self.unit.unit_id)
        self.lesson_id = get_lesson_id(
            self.base, self.unit.unit_id, self.lesson.lesson_id)

        self.set_course_availability(
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED)

        actions.login(ADMIN_EMAIL)

    def tearDown(self):
        sites.reset_courses()
        super(UnitTests, self).tearDown()

    def test_unit_fields(self):
        response = self.get_response(
            '{__type(name: "Unit") {'
            '    fields {name type {name kind ofType {name}}}}}')
        expected_data = {
            '__type': {'fields': [
                {'name': 'id', 'type': {
                    'kind': 'NON_NULL', 'name': None,
                    'ofType': {'name': 'ID'}}},
                {'name': 'title', 'type': {
                    'kind': 'SCALAR', 'name': 'String', 'ofType': None}},
                {'name': 'description', 'type': {
                    'kind': 'SCALAR', 'name': 'String', 'ofType': None}},
                {'name': 'allLessons', 'type': {
                    'kind': 'OBJECT', 'name': 'LessonDefaultConnection',
                    'ofType': None}},
                {'name': 'lesson', 'type': {
                    'kind': 'OBJECT', 'name': 'Lesson', 'ofType': None}},
                {'name': 'header', 'type': {
                    'kind': 'SCALAR', 'name': 'String', 'ofType': None}},
                {'name': 'footer', 'type': {
                    'kind': 'SCALAR', 'name': 'String', 'ofType': None}},
            ]}}
        self.assertEquals(expected_data, response['data'])

    def test_node_access(self):
        response = self.get_response('{node(id: "%s") {id}}' % self.unit_id)
        self.assertEquals(self.unit_id, response['data']['node']['id'])

    def test_unit_title(self):
        response = self.get_response(
            '{course(id: "%s") {unit(id: "%s") {title }}}' % (
                self.course_id, self.unit_id))
        self.assertEquals(
            self.unit.title, response['data']['course']['unit']['title'])

    def test_header_and_and_footer(self):
        self.unit.unit_header = 'The header'
        self.unit.unit_footer = 'The footer'
        self.course.save()

        response = self.get_response(
            '{course(id: "%s") {unit(id: "%s") {header footer}}}' % (
                self.course_id, self.unit_id))
        self.assertEquals(
            'The header', response['data']['course']['unit']['header'])
        self.assertEquals(
            'The footer', response['data']['course']['unit']['footer'])

    def test_header_and_footer_with_tags(self):
        self.unit.unit_header = 'The <gcb-markdown>*header*</gcb-markdown>'
        self.unit.unit_footer = 'The <gcb-markdown>*footer*</gcb-markdown>'
        self.course.save()

        response = self.get_response(
            '{course(id: "%s") {unit(id: "%s") {header footer}}}' % (
                self.course_id, self.unit_id))
        self.assertIn(
            '<em>header</em>', response['data']['course']['unit']['header'])
        self.assertIn(
            '<em>footer</em>', response['data']['course']['unit']['footer'])

    def test_lesson_access_available(self):
        actions.logout()

        self.unit.availability = courses.AVAILABILITY_AVAILABLE
        self.lesson.availability = courses.AVAILABILITY_AVAILABLE
        self.course.save()
        expected_lesson = {'title': self.lesson.title, 'body': 'Lesson body'}

        # Access single lesson
        response = self.get_response(
            '{course(id: "%s") {unit(id: "%s") {'
              'lesson(id: "%s") {title body}}}}' % (
                self.course_id, self.unit_id, self.lesson_id))
        _lesson = response['data']['course']['unit']['lesson']
        self.assertEquals(expected_lesson, _lesson)

        # Access lesson list
        response = self.get_response(
            '{course(id: "%s") {unit(id: "%s") {allLessons {edges {node {'
            '  ... on Lesson{title body}}}}}}}' % (
                self.course_id, self.unit_id))
        edges = response['data']['course']['unit']['allLessons']['edges']
        self.assertEquals(1, len(edges))
        self.assertEquals(expected_lesson, edges[0]['node'])

    def test_lesson_access_title_only(self):
        actions.logout()

        self.unit.availability = courses.AVAILABILITY_AVAILABLE
        self.lesson.availability = courses.AVAILABILITY_UNAVAILABLE
        self.lesson.shown_when_unavailable = True
        self.course.save()
        expected_lesson = {'title': self.lesson.title, 'body': None}

        # Access single lesson
        response = self.get_response(
            '{course(id: "%s") {unit(id: "%s") {'
              'lesson(id: "%s") {title body}}}}' % (
                self.course_id, self.unit_id, self.lesson_id))
        _lesson = response['data']['course']['unit']['lesson']
        self.assertEquals(expected_lesson, _lesson)

        # Access lesson list
        response = self.get_response(
            '{course(id: "%s") {unit(id: "%s") {allLessons {edges {node {'
            '  ... on Lesson{title body}}}}}}}' % (
                self.course_id, self.unit_id))
        edges = response['data']['course']['unit']['allLessons']['edges']
        self.assertEquals(1, len(edges))
        self.assertEquals(expected_lesson, edges[0]['node'])

    def test_lesson_access_unavailable(self):
        actions.logout()

        self.unit.availability = courses.AVAILABILITY_AVAILABLE
        self.lesson.availability = courses.AVAILABILITY_UNAVAILABLE
        self.lesson.shown_when_unavailable = False
        self.course.save()

        # Access single lesson
        response = self.get_response(
            '{course(id: "%s") {unit(id: "%s") {'
              'lesson(id: "%s") {title body}}}}' % (
                self.course_id, self.unit_id, self.lesson_id))
        self.assertIsNone(response['data']['course']['unit']['lesson'])

        # Access lesson list
        response = self.get_response(
            '{course(id: "%s") {unit(id: "%s") {allLessons {edges {node {'
            '  ... on Lesson{title body}}}}}}}' % (
                self.course_id, self.unit_id))
        self.assertEquals(
            [], response['data']['course']['unit']['allLessons']['edges'])


class LessonTests(GraphQLTreeTests):

    def setUp(self):
        super(LessonTests, self).setUp()
        self.base = '/' + COURSE_NAME
        app_context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, COURSE_NAME)
        self.course = courses.Course(None, app_context)
        self.unit = self.course.add_unit()
        self.unit.title = 'Test Unit'
        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.title = 'Test Lesson'
        self.lesson.objectives = 'Lesson body'
        self.course.save()

        self.course_id = get_course_id(self.base)
        self.unit_id = get_unit_id(self.base, self.unit.unit_id)
        self.lesson_id = get_lesson_id(
            self.base, self.unit.unit_id, self.lesson.lesson_id)

        self.set_course_availability(
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED)

        actions.login(ADMIN_EMAIL)

    def tearDown(self):
        sites.reset_courses()
        super(LessonTests, self).tearDown()

    def get_lesson(self, expanded_gcb_tags=None):
        response = self.get_response(
            '{course(id: "%s") {'
            '    unit(id: "%s") {lesson(id: "%s") {id title body}}}}' % (
                self.course_id, self.unit_id, self.lesson_id),
            expanded_gcb_tags=expanded_gcb_tags)
        return response['data']['course']['unit']['lesson']

    def test_lesson_fields(self):
        response = self.get_response(
            '{__type(name: "Lesson") {'
            '    fields {name type { name kind ofType {name}}}}}')
        expected_data = {
            '__type': {'fields': [
                {'name': 'id', 'type': {
                    'kind': 'NON_NULL', 'name': None,
                    'ofType': {'name': 'ID'}}},
                {'name': 'title', 'type': {
                    'kind': 'SCALAR', 'name': 'String', 'ofType': None}},
                {'name': 'body', 'type': {
                    'kind': 'SCALAR', 'name': 'String', 'ofType': None}}
            ]}}
        self.assertEquals(expected_data, response['data'])

    def test_node_access(self):
        response = self.get_response('{node(id: "%s") {id}}' % self.lesson_id)
        self.assertEquals(self.lesson_id, response['data']['node']['id'])

    def test_lesson_id(self):
        self.assertEquals(str(self.lesson_id), self.get_lesson()['id'])

    def test_lesson_title(self):
        self.assertEquals(self.lesson.title, self.get_lesson()['title'])

    def test_lesson_body(self):
        self.assertEquals(self.lesson.objectives, self.get_lesson()['body'])

    def test_lesson_body_with_tags(self):
        self.lesson.objectives = 'Lesson <gcb-markdown>*body*</gcb-markdown>'
        self.course.save()
        self.assertIn('<em>body</em>', self.get_lesson()['body'])

    def test_lesson_body_with_filtered_tags(self):
        # HTML with <gcb-markdown> and <gcb-math> to test tags expansion.
        self.lesson.objectives = (
            '<div id="markdown"><gcb-markdown>*bold*</gcb-markdown></div>' +
            '<div id="math">' +
            '<gcb-math>&lt;math&gt;&lt;mi&gt;&amp;pi;&lt;/mi&gt;&lt;/math&gt;' +
            '</gcb-math>' +
            '</div>')
        self.course.save()

        # Only <gcb-markdown> tags should be expanded.
        expanded_gcb_tags = 'gcb-markdown'
        body = self.get_lesson(expanded_gcb_tags=expanded_gcb_tags)['body']

        self.assertIn('<em>bold</em>', body)
        self.assertIn(
            '<div id="math"><div style="display:none;"></div></div>',
            body)

        # Only <gcb-math> tags should be expanded.
        expanded_gcb_tags = 'gcb-math'
        body = self.get_lesson(expanded_gcb_tags=expanded_gcb_tags)['body']
        self.assertIn(
            '<div id="markdown"><div style="display:none;"></div></div>',
            body)
        self.assertIn(
            '<div id="math"><script type="math/tex"><math><mi>&pi;</mi>' +
            '</math></script></div>',
            body)

        # Both <gcb-markdown> and <gcb-math> should be expanded.
        expanded_gcb_tags = 'gcb-markdown gcb-math'
        body = self.get_lesson(expanded_gcb_tags=expanded_gcb_tags)['body']
        self.assertIn('<em>bold</em>', body)
        self.assertIn(
            '<div id="math"><script type="math/tex"><math><mi>&pi;</mi>' +
            '</math></script></div>',
            body)

        # No <gcb-markdown> or <gcb-math> tags should be expanded.
        expanded_gcb_tags = 'gcb-youtube'
        body = self.get_lesson(expanded_gcb_tags=expanded_gcb_tags)['body']
        self.assertIn(
            '<div id="markdown"><div style="display:none;"></div></div>',
            body)
        self.assertIn(
            '<div id="math"><div style="display:none;"></div></div>',
            body)




