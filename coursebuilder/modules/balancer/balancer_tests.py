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

"""Functional tests for the balancer module."""

__author__ = [
    'johncox@google.com (John Cox)',
]

import types

from models import config
from models import transforms
from modules.balancer import balancer
from tests.functional import actions

from google.appengine.api import urlfetch
from google.appengine.ext import db

# Allow access to protected code under test. pylint: disable=protected-access


class _FakeResponse(object):
    def __init__(self, code, body):
        self.content = transforms.dumps(body)
        self.status_code = code


class ExternalTaskTest(actions.TestBase):

    def setUp(self):
        super(ExternalTaskTest, self).setUp()
        self.worker_id = 'worker_id'
        self.external_task = balancer._ExternalTask(
            status=balancer._ExternalTask.RUNNING, worker_id='worker_id')
        self.key = self.external_task.put()

    def test_get_key_by_ticket_raises_value_error(self):
        self.assertRaises(
            ValueError, balancer._ExternalTask.get_key_by_ticket, 1)

    def test_get_key_by_ticket_and_get_ticket_round_trip(self):
        ticket = self.external_task.get_ticket()
        saved_external_task = db.get(
            balancer._ExternalTask.get_key_by_ticket(ticket))

        self.assertEqual(self.key, saved_external_task.key())

    def test_get_key_by_ticket_and_get_ticket_by_key_round_trip(self):
        ticket = balancer._ExternalTask.get_ticket_by_key(self.key)
        saved_external_task = db.get(
            balancer._ExternalTask.get_key_by_ticket(ticket))

        self.assertEqual(self.key, saved_external_task.key())


class ManagerTest(actions.TestBase):

    def setUp(self):
        super(ManagerTest, self).setUp()
        self.user_id = 'user_id'
        self.worker_id = 'worker_id'

    def test_create(self):
        no_user_id_key = balancer.Manager.create()
        with_user_id_key = balancer.Manager.create(user_id=self.user_id)
        no_user_id = db.get(no_user_id_key)
        with_user_id = db.get(with_user_id_key)

        self.assertEqual(balancer._ExternalTask.CREATED, no_user_id.status)
        self.assertIsNone(no_user_id.user_id)

        self.assertEqual(balancer._ExternalTask.CREATED, with_user_id.status)
        self.assertEqual(self.user_id, with_user_id.user_id)

    def test_delete_removes_entity(self):
        ticket = balancer.Manager.create()

        self.assertTrue(balancer.Manager.get(ticket))

        balancer.Manager._delete(ticket)

        self.assertFalse(balancer.Manager.get(ticket))

    def test_get(self):
        ticket = balancer.Manager.create()

        self.assertEqual(ticket, balancer.Manager.get(ticket).ticket)

        balancer.Manager._delete(ticket)

        self.assertIsNone(balancer.Manager.get(ticket))

    def test_list(self):
        self.assertEqual([], balancer.Manager.list(self.user_id))

        missing_ticket = balancer.Manager.create(user_id=self.user_id)
        first_match_ticket = balancer.Manager.create(user_id=self.user_id)
        second_match_ticket = balancer.Manager.create(user_id=self.user_id)
        balancer.Manager._delete(missing_ticket)

        self.assertEqual(
            [first_match_ticket, second_match_ticket],
            [task.ticket for task in balancer.Manager.list(self.user_id)])

    def test_mark_deleted(self):
        ticket = balancer.Manager.create()

        self.assertEqual(
            balancer._ExternalTask.CREATED, balancer.Manager.get(ticket).status)

        balancer.Manager.mark_deleted(ticket)

        self.assertEqual(
            balancer._ExternalTask.DELETED, balancer.Manager.get(ticket).status)

        balancer.Manager._delete(ticket)

        self.assertRaises(
            balancer.NotFoundError, balancer.Manager.mark_deleted, ticket)

    def test_mark_done_updates_result_and_status(self):
        ticket = balancer.Manager.create()
        task = balancer.Manager.get(ticket)

        self.assertIsNone(task.result)
        self.assertEqual(balancer._ExternalTask.CREATED, task.status)

        result = 'result'
        balancer.Manager.mark_done(
            ticket, balancer._ExternalTask.COMPLETE, result)
        task = balancer.Manager.get(ticket)

        self.assertEqual(result, task.result)
        self.assertEqual(balancer._ExternalTask.COMPLETE, task.status)

    def test_mark_done_raises_not_found_error_if_no_task_for_ticket(self):
        ticket = balancer.Manager.create()
        balancer.Manager._delete(ticket)

        self.assertRaises(
            balancer.NotFoundError, balancer.Manager.mark_done, ticket,
            balancer._ExternalTask.COMPLETE, 'result')

    def test_mark_done_raises_transition_error_if_status_nonterminal(self):
        ticket = balancer.Manager.create()

        self.assertFalse(
            balancer._ExternalTask.is_status_terminal(
                balancer._ExternalTask.RUNNING))
        self.assertRaises(
            balancer.TransitionError, balancer.Manager.mark_done, ticket,
            balancer._ExternalTask.RUNNING, 'result')

    def test_mark_failed(self):
        ticket = balancer.Manager.create()

        self.assertEqual(
            balancer._ExternalTask.CREATED, balancer.Manager.get(ticket).status)

        balancer.Manager.mark_failed(ticket)

        self.assertEqual(
            balancer._ExternalTask.FAILED, balancer.Manager.get(ticket).status)

        balancer.Manager._delete(ticket)

        self.assertRaises(
            balancer.NotFoundError, balancer.Manager.mark_deleted, ticket)

    def test_mark_running(self):
        ticket = balancer.Manager.create()

        task = balancer.Manager.get(ticket)
        self.assertEqual(balancer._ExternalTask.CREATED, task.status)
        self.assertIsNone(task.worker_id)

        balancer.Manager.mark_running(ticket, self.worker_id)

        task = balancer.Manager.get(ticket)
        self.assertEqual(balancer._ExternalTask.RUNNING, task.status)
        self.assertEqual(self.worker_id, task.worker_id)

        balancer.Manager._delete(ticket)

        self.assertRaises(
            balancer.NotFoundError, balancer.Manager.mark_running, ticket,
            self.worker_id)


class _RestTestBase(actions.TestBase):

    def setUp(self):
        super(_RestTestBase, self).setUp()
        self.worker_url = 'http://worker_url'

    def tearDown(self):
        config.Registry.test_overrides = {}
        super(_RestTestBase, self).tearDown()

    def assert_bad_request_error(self, response):
        self.assertEqual(400, response.status_code)
        self.assertIn('Bad request', response.body)

    def assert_response_equal(self, expected_code, expected_body, response):
        self.assertEqual(expected_code, response.status_code)
        self.assertEqual(expected_body, transforms.loads(response.body))

    def assert_rest_enabled_but_url_not_set_error(self, response):
        self.assertEqual(500, response.status_code)
        self.assertIn('No worker pool found', response.body)

    def assert_rest_not_enabled_error(self, response):
        self.assertEqual(404, response.status_code)
        self.assertIn('Not found', response.body)

    def assert_unable_to_dispatch_request_error(self, response):
        self.assertEqual(500, response.status_code)
        self.assertIn('Unable to dispatch request', response.body)

    def configure_registry(self):
        config.Registry.test_overrides[
            balancer.EXTERNAL_TASK_BALANCER_REST_ENABLED.name] = True
        config.Registry.test_overrides[
            balancer.EXTERNAL_TASK_BALANCER_WORKER_URL.name] = self.worker_url


class ProjectRestHandlerTest(_RestTestBase):

    def setUp(self):
        super(ProjectRestHandlerTest, self).setUp()
        self.project = 'project'
        self.params = self.make_request_params(self.project)

    def make_request_params(self, project):
        return {'request': transforms.dumps({'project': project})}

    def test_get_returns_400_if_request_malformed(self):
        self.configure_registry()

        self.assert_bad_request_error(self.testapp.get(
            balancer._REST_URL_PROJECT, expect_errors=True))

    def test_get_returns_404_if_config_enabled_false(self):
        self.assert_rest_not_enabled_error(self.testapp.get(
            balancer._REST_URL_PROJECT, expect_errors=True))

    def test_get_returns_500_if_cannot_dispatch_request_to_pool(self):
        self.configure_registry()

        self.assert_unable_to_dispatch_request_error(self.testapp.get(
            balancer._REST_URL_PROJECT, expect_errors=True, params=self.params))

    def test_get_returns_500_if_config_enabled_but_no_url_set(self):
        config.Registry.test_overrides[
            balancer.EXTERNAL_TASK_BALANCER_REST_ENABLED.name] = True

        self.assert_rest_enabled_but_url_not_set_error(self.testapp.get(
            balancer._REST_URL_PROJECT, expect_errors=True))

    def test_get_returns_worker_response(self):
        self.configure_registry()
        expected_code = 200
        expected_body = {'payload': 'contents'}

        def fetch_response(
                _, deadline=None, headers=None, method=None, payload=None):
            return _FakeResponse(expected_code, expected_body)

        self.swap(balancer.urlfetch, 'fetch', fetch_response)
        response = self.testapp.get(
            balancer._REST_URL_PROJECT, params=self.params)
        self.assert_response_equal(expected_code, expected_body, response)


class TaskRestHandlerTest(_RestTestBase):

    def setUp(self):
        super(TaskRestHandlerTest, self).setUp()
        self.user_id = 'user_id'
        self.worker_id = 'http://worker_id'

    def assert_invalid_status_or_payload_too_big_error(self, response):
        self.assertEqual(500, response.status_code)
        self.assertIn('Invalid worker status or payload too big', response.body)

    def assert_task_found(self, expected_task, response):
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            expected_task.for_json(), transforms.loads(response.body))

    def assert_task_not_found_error(self, response):
        self.assertEqual(404, response.status_code)
        self.assertIn('Task not found for ticket', response.body)

    def assert_ticket_mismatch_error(self, response):
        self.assertEqual(500, response.status_code)
        self.assertIn('Ticket mismatch', response.body)

    def assert_unable_to_compose_request_for_worker_error(self, response):
        self.assertEqual(500, response.status_code)
        self.assertIn('Unable to compose request for worker', response.body)

    def assert_worker_failed_error(self, response):
        self.assertEqual(500, response.status_code)
        self.assertIn('Worker failed', response.body)

    def assert_worker_locked_error(self, response):
        self.assertEqual(500, response.status_code)
        self.assertIn('Worker locked', response.body)

    def assert_worker_sent_partial_response_error(self, response):
        self.assertEqual(500, response.status_code)
        self.assertIn('Worker sent partial response', response.body)

    def make_get_request_params(self, ticket, payload=None, worker_id=None):
        body = {'ticket': ticket}

        if payload:
            body['payload'] = payload
        if worker_id:
            body['worker_id'] = worker_id

        return {'request' : transforms.dumps(body)}

    def make_post_request_params(self, payload):
        return {'request': transforms.dumps(payload)}

    def test_get_returns_200_if_task_already_done(self):
        self.configure_registry()
        ticket = balancer.Manager.create()
        balancer.Manager.mark_done(
            ticket, balancer._ExternalTask.COMPLETE, 'result')
        task = balancer.Task._from_external_task(
            db.get(balancer._ExternalTask.get_key_by_ticket(ticket)))
        params = self.make_get_request_params(ticket)

        response = self.testapp.get(balancer._REST_URL_TASK, params=params)
        self.assert_task_found(task, response)

    def test_get_returns_400_if_request_malformed(self):
        self.configure_registry()

        self.assert_bad_request_error(self.testapp.get(
            balancer._REST_URL_TASK, expect_errors=True))

    def test_get_returns_404_if_config_enabled_false(self):
        self.assert_rest_not_enabled_error(self.testapp.get(
            balancer._REST_URL_TASK, expect_errors=True))

    def test_get_returns_404_if_ticket_has_no_matching_task(self):
        self.configure_registry()
        ticket = balancer.Manager.create()
        balancer.Manager._delete(ticket)
        params = self.make_get_request_params(ticket)

        self.assert_task_not_found_error(self.testapp.get(
            balancer._REST_URL_TASK, expect_errors=True, params=params))

    def test_get_returns_404_if_ticket_invalid(self):
        self.configure_registry()
        ticket = 1
        params = self.make_get_request_params(ticket)

        self.assert_task_not_found_error(self.testapp.get(
            balancer._REST_URL_TASK, expect_errors=True, params=params))

    def test_get_returns_500_if_config_enabled_but_no_url_set(self):
        config.Registry.test_overrides[
            balancer.EXTERNAL_TASK_BALANCER_REST_ENABLED.name] = True

        self.assert_rest_enabled_but_url_not_set_error(self.testapp.get(
            balancer._REST_URL_TASK, expect_errors=True))

    def test_get_returns_500_if_task_update_fails(self):
        self.configure_registry()
        ticket = balancer.Manager.create()
        balancer.Manager.mark_running(ticket, self.worker_id)
        params = self.make_get_request_params(ticket)

        def worker_response(
                _, deadline=None, headers=None, method=None, payload=None):
            return _FakeResponse(
                200,
                {'payload': {'status': balancer._ExternalTask.COMPLETE,
                             'payload': 'x' * 1024 * 1025}})  # Overflow db.

        self.swap(balancer.urlfetch, 'fetch', worker_response)
        self.assert_invalid_status_or_payload_too_big_error(self.testapp.get(
            balancer._REST_URL_TASK, expect_errors=True, params=params))

    def test_get_returns_500_if_unable_to_compose_request_for_worker(self):
        self.configure_registry()
        ticket = balancer.Manager.create()
        params = self.make_get_request_params(ticket)

        self.assert_unable_to_compose_request_for_worker_error(self.testapp.get(
            balancer._REST_URL_TASK, expect_errors=True, params=params))

    def test_get_returns_500_if_worker_sends_partial_response(self):
        self.configure_registry()
        ticket = balancer.Manager.create()
        balancer.Manager.mark_running(ticket, self.worker_id)
        params = self.make_get_request_params(ticket)

        def worker_response(
                _, deadline=None, headers=None, method=None, payload=None):
            return _FakeResponse(200, {'payload': {'no_status': None}})

        self.swap(balancer.urlfetch, 'fetch', worker_response)
        self.assert_worker_sent_partial_response_error(self.testapp.get(
            balancer._REST_URL_TASK, expect_errors=True, params=params))

    def test_get_relays_non_200_response_from_worker(self):
        self.configure_registry()
        ticket = balancer.Manager.create()
        balancer.Manager.mark_running(ticket, self.worker_id)
        params = self.make_get_request_params(ticket)

        self.assert_unable_to_dispatch_request_error(self.testapp.get(
            balancer._REST_URL_TASK, expect_errors=True, params=params))

    def test_get_relays_worker_response_if_status_nonterminal(self):
        self.configure_registry()
        ticket = balancer.Manager.create()
        balancer.Manager.mark_running(ticket, self.worker_id)
        params = self.make_get_request_params(ticket)

        def worker_response(
                _, deadline=None, headers=None, method=None, payload=None):
            return _FakeResponse(200, {'payload': {'status': 'nonterminal'}})

        self.swap(balancer.urlfetch, 'fetch', worker_response)
        response = self.testapp.get(balancer._REST_URL_TASK, params=params)
        self.assertEqual(200, response.status_code)
        self.assertIn('nonterminal', response.body)

    def test_get_updates_task_relays_worker_response_if_status_terminal(self):
        self.configure_registry()
        ticket = balancer.Manager.create()
        balancer.Manager.mark_running(ticket, self.worker_id)
        expected_payload = {
            'payload': {
                'status': balancer._ExternalTask.COMPLETE,
                'payload': 'new_payload',
            },
        }
        params = self.make_get_request_params(ticket)

        def worker_response(
                _, deadline=None, headers=None, method=None, payload=None):
            return _FakeResponse(200, expected_payload)

        self.swap(balancer.urlfetch, 'fetch', worker_response)
        response = self.testapp.get(balancer._REST_URL_TASK, params=params)
        task = balancer.Manager.get(ticket)

        self.assert_response_equal(200, expected_payload, response)
        self.assertEqual('new_payload', task.result)
        self.assertEqual(balancer._ExternalTask.COMPLETE, task.status)

    def test_post_returns_400_if_request_malformed(self):
        self.configure_registry()

        self.assert_bad_request_error(self.testapp.post(
            balancer._REST_URL_TASK, expect_errors=True))

    def test_post_returns_404_if_config_enabled_false(self):
        self.assert_rest_not_enabled_error(self.testapp.post(
            balancer._REST_URL_TASK, expect_errors=True))

    def test_post_returns_500_if_config_enabled_but_no_url_set(self):
        config.Registry.test_overrides[
            balancer.EXTERNAL_TASK_BALANCER_REST_ENABLED.name] = True

        self.assert_rest_enabled_but_url_not_set_error(self.testapp.post(
            balancer._REST_URL_TASK, expect_errors=True))

    # TODO(johncox): figure out a way to test op.ready() false.

    def test_post_returns_200_and_marks_task_running(self):
        self.configure_registry()
        params = self.make_post_request_params({'user_id': self.user_id})
        ticket = balancer.Manager.create()
        worker_response_body = {
            'payload': {
                'payload': None,
                'ticket': ticket,
                'status': balancer._ExternalTask.RUNNING,
            }
        }

        def create(*args, **kwargs):
            return ticket

        def worker_response(
                _, deadline=None, headers=None, method=None, payload=None):
            return _FakeResponse(200, worker_response_body)

        bound_create = types.MethodType(
            create, balancer.Manager(), balancer.Manager)
        self.swap(balancer.Manager, 'create', bound_create)
        self.swap(balancer.urlfetch, 'fetch', worker_response)
        response = self.testapp.post(balancer._REST_URL_TASK, params=params)
        task = balancer.Manager.get(ticket)

        self.assert_response_equal(200, worker_response_body, response)
        self.assertEqual(balancer._ExternalTask.RUNNING, task.status)

    def test_post_returns_200_and_marks_task_running_if_retry_succeeds(self):
        self.configure_registry()
        params = self.make_post_request_params({'user_id': self.user_id})
        ticket = balancer.Manager.create()

        def create(*args, **kwargs):
            return ticket

        def successful_retry(self, response, op):
            return 200, {'payload': {'status': 'running', 'ticket': ticket}}

        def worker_response(
                _, deadline=None, headers=None, method=None, payload=None):
            return _FakeResponse(500, {'payload': balancer._WORKER_LOCKED})

        bound_create = types.MethodType(
            create, balancer.Manager(), balancer.Manager)
        self.swap(balancer.Manager, 'create', bound_create)
        self.swap(
            balancer._TaskRestHandler, '_retry_create_task', successful_retry)
        self.swap(balancer.urlfetch, 'fetch', worker_response)
        response = self.testapp.post(balancer._REST_URL_TASK, params=params)
        external_task = balancer._ExternalTask.all().fetch(1)[0]

        self.assertEqual(200, response.status_code)
        self.assertEqual(balancer._ExternalTask.RUNNING, external_task.status)

    def test_post_returns_500_and_marks_task_failed_if_retry_fails(self):
        self.configure_registry()
        params = self.make_post_request_params({'user_id': self.user_id})
        ticket = balancer.Manager.create()

        def create(*args, **kwargs):
            return ticket

        def worker_response(
                _, deadline=None, headers=None, method=None, payload=None):
            return _FakeResponse(500, {'payload': balancer._WORKER_LOCKED})

        bound_create = types.MethodType(
            create, balancer.Manager(), balancer.Manager)
        self.swap(balancer.Manager, 'create', bound_create)
        self.swap(balancer.urlfetch, 'fetch', worker_response)
        response = self.testapp.post(
            balancer._REST_URL_TASK, expect_errors=True, params=params)
        external_task = balancer._ExternalTask.all().fetch(1)[0]

        self.assert_worker_locked_error(response)
        self.assertEqual(balancer._ExternalTask.FAILED, external_task.status)

    def test_post_returns_500_and_marks_task_failed_if_ticket_mismatch(self):
        self.configure_registry()
        params = self.make_post_request_params({'user_id': self.user_id})

        def worker_response(
                _, deadline=None, headers=None, method=None, payload=None):
            return _FakeResponse(
                200, {'payload': {'status': 'running', 'payload': None}})

        self.swap(balancer.urlfetch, 'fetch', worker_response)
        response = self.testapp.post(
            balancer._REST_URL_TASK, expect_errors=True, params=params)
        external_task = balancer._ExternalTask.all().fetch(1)[0]

        self.assert_ticket_mismatch_error(response)
        self.assertEqual(balancer._ExternalTask.FAILED, external_task.status)

    def test_post_returns_500_and_marks_task_failed_if_worker_failed(self):
        self.configure_registry()
        params = self.make_post_request_params({'user_id': self.user_id})
        ticket = balancer.Manager.create()

        def create(*args, **kwargs):
            return ticket

        def worker_response(
                _, deadline=None, headers=None, method=None, payload=None):
            return _FakeResponse(500, {'payload': {'ticket': ticket}})

        bound_create = types.MethodType(
            create, balancer.Manager(), balancer.Manager)
        self.swap(balancer.Manager, 'create', bound_create)
        self.swap(balancer.urlfetch, 'fetch', worker_response)
        response = self.testapp.post(
            balancer._REST_URL_TASK, expect_errors=True, params=params)

        external_task = balancer._ExternalTask.all().fetch(1)[0]

        self.assert_worker_failed_error(response)
        self.assertEqual(balancer._ExternalTask.FAILED, external_task.status)


class WorkerPoolTest(actions.TestBase):

    def setUp(self):
        super(WorkerPoolTest, self).setUp()
        self.op = balancer._GetProjectOperation('payload')

    def assert_unable_to_dispatch_request_error(self, result):
        code, body = result
        self.assertEqual(500, code)
        self.assertEqual('Unable to dispatch request', body['payload'])

    def test_do_fetch_returns_code_and_transformed_body_from_worker(self):
        expected_code = 200
        expected_body = {'payload': 'contents'}

        def fetch_response(
                _, deadline=None, headers=None, method=None, payload=None):
            return _FakeResponse(expected_code, expected_body)

        self.swap(balancer.urlfetch, 'fetch', fetch_response)
        code, body = balancer._WorkerPool._do_fetch(
            'http://url', 'GET', self.op)
        self.assertEqual(expected_code, code)
        self.assertEqual(expected_body, body)

    def test_do_fetch_returns_500_when_urlfetch_raises(self):

        def fetch_error(
                _, deadline=None, headers=None, method=None, payload=None):
            raise urlfetch.DownloadError

        self.swap(balancer.urlfetch, 'fetch', fetch_error)
        self.assert_unable_to_dispatch_request_error(
            balancer._WorkerPool._do_fetch('http://url', 'GET', self.op))
