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

"""External task balancer.

Overall architecture is:

1. Users interact with clients.
2. Clients make requests against the frontend's REST API.
3. The FE makes a REST call against a worker or worker pool identified by
   gcb_external_task_balancer_worker_url. The FE provisions a unique token,
   generates a Task instance, and dispatches a REST request to the worker or
   worker pool.
4. The worker or worker pool exposes a REST API for use by the FE. Worker
   responses contain the name of the worker so the FE can poll a specific worker
   for results using the (ticket, name) combination. Workers are in charge both
   of doing work and of cleaning up their results. Clients do not talk to
   workers directly.

To enable, set up a pool of workers behind a single URL. For example, this might
be a set of machines behind a balancer on GCE or an AWS ELB. Next, set
gcb_external_task_balancer_rest_enabled to True and set
gcb_external_task_balancer_worker_url to the URL of your worker pool. Secure
communication if desired, and write a client against the REST API this module
exposes.

This implementation has the following big limitations:

1. It is insecure. Currently there is no token exchange/validation at the API
   level, so anyone who gets a ticket (for example, by listening to HTTP
   traffic between clients and the FE) can issue API calls.
2. There is no XSSI/XSRF protection. Note that exposed endpoints will 404 by
   default because gcb_external_task_balancer_rest_enabled is False, so the
   behavior without overrides does *not* expose unprotected REST endpoints.
3. Old task items hang around forever. Could implement garbage collection cron
   to remove them past a TTL.
4. The REST api is missing ability to mark a single task for deletion and to
   fetch a paginated list of results (without their payloads) for a given
   user_id. Open issue: we do not expose the notion of a project in the REST
   API, but we have it in the workers. Should we expose it to allow filtering at
   the API level?
5. Add support for one balancer handling multiple pools of workers, not just
   one.
6. Manager.mark* methods don't all check that the requested status transition is
   valid. This means buggy handlers/workers/clients could cause invalid status
   transitions. Fix is to have the Manager throw TransitionError in those cases
   and modify the handlers to 400/500.

TODO(johncox): add URL of sample worker implementation once it's finished.
"""

__author__ = [
    'johncox@google.com (John Cox)',
]

import logging
import urllib

from controllers import utils
from models import config
from models import custom_modules
from models import entities
from models import transforms
from modules.balancer import messages

from google.appengine.api import urlfetch
from google.appengine.ext import db

_DISABLE_CACHING_HEADERS = {
    'Cache-Control': 'max-age=0, must-revalidate',
    'Pragma': 'no-cache',
}
_PAYLOAD = 'payload'
_TICKET = 'ticket'
_PROJECT_NAME = 'project'
_REST_URL_BASE = '/rest/balancer/v1'
_REST_URL_PROJECT = _REST_URL_BASE + '/project'
_REST_URL_TASK = _REST_URL_BASE
_STATUS = 'status'
_USER_ID = 'user_id'
_WORKER_DEADLINE_SECONDS = 5
_WORKER_ID = 'worker_id'
_WORKER_LOCKED = 'Worker locked'
_WORKER_LOCKED_MAX_RETRIES = 3


_LOG = logging.getLogger('modules.balancer.balancer')
logging.basicConfig()


EXTERNAL_TASK_BALANCER_REST_ENABLED = config.ConfigProperty(
    'gcb_external_task_balancer_rest_enabled', bool,
    messages.SITE_SETTINGS_TASK_BALANCER_REST, default_value=False,
    label='Task Balancer REST')
EXTERNAL_TASK_BALANCER_WORKER_URL = config.ConfigProperty(
    'gcb_external_task_balancer_worker_url', str,
    messages.SITE_SETTINGS_TASK_BALANCER_URL, default_value='',
    label='Task Balancer URL')


class Error(Exception):
    """Base error class."""


class NotFoundError(Exception):
    """Raised when an op that needs an entity is run with a missing entity."""


class TransitionError(Exception):
    """Raised when an op attempts an invalid transition on a task."""


def _from_json(json_str):
    """Turns json -> object (or None if json cannot be parsed)."""

    try:
        return transforms.loads(json_str)
    except:  # Deliberately catching everything. pylint: disable=bare-except
        return None


class Manager(object):
    """DAO for external tasks."""

    # Treating access as module-protected. pylint: disable=protected-access

    @classmethod
    def create(cls, user_id=None):
        """Creates task and returns ticket string."""
        task = _ExternalTask(status=_ExternalTask.CREATED, user_id=user_id)
        return _ExternalTask.get_ticket_by_key(db.put(task))

    @classmethod
    def get(cls, ticket):
        """Gets task for ticket (or None if no matching task)."""
        external_task = db.get(_ExternalTask.get_key_by_ticket(ticket))
        if not external_task:
            return None

        return Task._from_external_task(external_task)

    @classmethod
    def list(cls, user_id):
        """Returns list of Task matching user_id, ordered by create date."""
        return [Task._from_external_task(et) for et in sorted(
            _ExternalTask.all().filter(
                '%s =' % _ExternalTask.user_id.name, user_id
            ).fetch(1000), key=lambda task: task.create_date)]

    @classmethod
    @db.transactional
    def mark_deleted(cls, ticket):
        task = cls._get_or_raise_not_found_error(ticket)
        task.status = _ExternalTask.DELETED
        db.put(task)

    @classmethod
    @db.transactional
    def mark_done(cls, ticket, status, result):
        if status not in _ExternalTask._TERMINAL_STATUSES:
            raise TransitionError(
                'mark_done called with non-terminal status ' + status)

        task = cls._get_or_raise_not_found_error(ticket)
        task.result = result
        task.status = status
        db.put(task)

    @classmethod
    @db.transactional
    def mark_failed(cls, ticket):
        task = cls._get_or_raise_not_found_error(ticket)
        task.status = _ExternalTask.FAILED
        db.put(task)

    @classmethod
    @db.transactional
    def mark_running(cls, ticket, worker_id):
        task = cls._get_or_raise_not_found_error(ticket)
        task.status = _ExternalTask.RUNNING
        task.worker_id = worker_id
        db.put(task)

    @classmethod
    def _delete(cls, ticket):
        key = _ExternalTask.get_key_by_ticket(ticket)
        db.delete(key)

    @classmethod
    def _get_or_raise_not_found_error(cls, ticket):
        key = _ExternalTask.get_key_by_ticket(ticket)
        task = db.get(key)
        if not task:
            raise NotFoundError

        return task


class Task(object):
    """DTO for external tasks."""

    def __init__(
            self, change_date, create_date, result, status, ticket, user_id,
            worker_id):
        self.change_date = change_date
        self.create_date = create_date
        self.result = result
        self.status = status
        self.ticket = ticket
        self.user_id = user_id
        self.worker_id = worker_id

    @classmethod
    def _from_external_task(cls, external_task):
        return cls(
            external_task.change_date, external_task.create_date,
            external_task.result, external_task.status,
            external_task.get_ticket(), external_task.user_id,
            external_task.worker_id)

    def is_done(self):
        return _ExternalTask.is_status_terminal(self.status)

    def for_json(self):
        return {
            'change_date': self.change_date.strftime(
                transforms.ISO_8601_DATETIME_FORMAT),
            'create_date': self.create_date.strftime(
                transforms.ISO_8601_DATETIME_FORMAT),
            'result': self.result,
            'status': self.status,
            'ticket': self.ticket,
            'user_id': self.user_id,
            'worker_id': self.worker_id,
        }

    def __eq__(self, other):
        return (
            isinstance(other, Task) and
            self.change_date == other.change_date and
            self.create_date == other.create_date and
            self.result == other.result and
            self.status == other.status and
            self.ticket == other.ticket and
            self.user_id == other.user_id and
            self.worker_id == other.worker_id)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        return (
            'Task - change_date: %(change_date)s, '
            'create_date: %(create_date)s, result: %(result)s, '
            'status: %(status)s, ticket: %(ticket)s, user_id: %(user_id)s, '
            'worker_id: %(worker_id)s' % self.to_dict())


class _ExternalTask(entities.BaseEntity):
    """Storage for external tasks."""

    # States a task may be in.
    COMPLETE = 'complete'  # Done running and in known success state.
    CREATED = 'created'    # Datastore entity created, but task not yet running.
    DELETED = 'deleted'    # Marked for deletion; could be deleted later.
    FAILED = 'failed'      # Done running and in known failure state.
    RUNNING = 'running'    # Currently running on a worker.
    _PENDING_STATUSES = frozenset([
        CREATED,
        RUNNING,
    ])
    _TERMINAL_STATUSES = frozenset([
        COMPLETE,
        DELETED,
        FAILED,
    ])
    STATUSES = _PENDING_STATUSES.union(_TERMINAL_STATUSES)

    # When the task was last edited.
    change_date = db.DateTimeProperty(required=True, auto_now=True)
    # When the task was created.
    create_date = db.DateTimeProperty(required=True, auto_now_add=True)
    # Output of the task in JSON.
    result = db.TextProperty()
    # Last observed status of the task. Can be inaccurate: for example, if a
    # user creates a new task but navigates away before the task completes and
    # their client never fetches the task when it's done, we'll still show it
    # running.
    status = db.StringProperty(required=True, choices=STATUSES)
    # Optional identifier for the user who owns the task. We impose no
    # restrictions beyond the identifier being a string <= 500B, per datastore.
    user_id = db.StringProperty()
    # Identifier for the worker.
    worker_id = db.StringProperty()

    @classmethod
    def get_key_by_ticket(cls, ticket_str):
        try:
            return db.Key(encoded=ticket_str)
        except:
            raise ValueError(
                'Cannot make _ExternalTask key from ticket value: %s' % (
                    ticket_str))

    @classmethod
    def get_ticket_by_key(cls, key):
        return str(key)

    @classmethod
    def is_status_terminal(cls, status):
        return status in cls._TERMINAL_STATUSES

    def get_ticket(self):
        """Returns string identifier for the task; raises NotSavedError."""
        return self.get_ticket_by_key(self.key())


class _Operation(object):
    """Base class for wire operation payloads."""

    @classmethod
    def from_str(cls, raw_str):
        return cls._from_json(transforms.loads(raw_str))

    @classmethod
    def _from_json(cls, parsed):
        # Parse and validate raw input, raising ValueError if necessary.
        raise NotImplementedError

    def ready(self):
        """True iff the operation has all data it needs to be issued."""
        raise NotImplementedError

    def to_json(self):
        return transforms.dumps(self._to_dict())

    def to_url(self):
        return urllib.quote_plus(self.to_json())

    def update(self, updates_dict):
        for k, v in updates_dict.iteritems():
            if not hasattr(self, k):
                raise ValueError('Cannot set name ' + k)

            setattr(self, k, v)

    def _to_dict(self):
        raise NotImplementedError


class _CreateTaskOperation(_Operation):

    def __init__(self, payload, ticket, user_id):
        self.payload = payload
        self.ticket = ticket
        self.user_id = user_id

    @classmethod
    def _from_json(cls, parsed):
        return cls(parsed, None, parsed.get(_USER_ID))

    def ready(self):
        return self.payload is not None and self.ticket is not None

    def _to_dict(self):
        return {
            _PAYLOAD: self.payload,
            _TICKET: self.ticket,
            _USER_ID: self.user_id,
        }


class _GetProjectOperation(_Operation):

    def __init__(self, payload):
        self.payload = payload

    @classmethod
    def _from_json(cls, parsed):
        return cls(parsed)

    def ready(self):
        return self.payload is not None

    def _to_dict(self):
        return {_PAYLOAD: self.payload}


class _GetTaskOperation(_Operation):

    def __init__(self, payload, ticket, worker_id):
        self.payload = payload
        self.ticket = ticket
        self.worker_id = worker_id

    @classmethod
    def _from_json(cls, parsed):
        ticket = parsed.get(_TICKET)
        if not ticket:
            raise ValueError('%s not set' % _TICKET)

        return cls(parsed, ticket, parsed.get(_WORKER_ID))

    def ready(self):
        return (
            self.payload is not None and self.ticket is not None and
            self.worker_id is not None)

    def _to_dict(self):
        return {
            _PAYLOAD: self.payload,
            _TICKET: self.ticket,
            _WORKER_ID: self.worker_id,
        }


class _WorkerPool(object):
    """Interface for the pool of machines that do background work."""

    @classmethod
    def _check_response(cls, response):
        return response.has_key(_PAYLOAD)

    @classmethod
    def _do_fetch(cls, url, method, operation):
        try:
            response = urlfetch.fetch(
                cls._get_url(url, method, operation),
                deadline=_WORKER_DEADLINE_SECONDS,
                headers=_DISABLE_CACHING_HEADERS, method=method,
                payload=cls._get_request_body(method, operation))
            return (
                response.status_code, cls._transform_response(response))
        except urlfetch.DownloadError as e:  # 4xx, 5xx, timeouts.
            _LOG.error('Unable to dispatch request to pool; error: %s', e)
            return 500, {_PAYLOAD: 'Unable to dispatch request'}

    @classmethod
    def _get_base_url(cls, worker_id=None):
        base = (
            worker_id if worker_id is not None else
            EXTERNAL_TASK_BALANCER_WORKER_URL.value)
        return base + '/rest/v1'

    @classmethod
    def _get_create_task_url(cls):
        return cls._get_base_url()

    @classmethod
    def _get_get_project_url(cls):
        return cls._get_base_url() + '/project'

    @classmethod
    def _get_get_task_url(cls, worker_id):
        return cls._get_base_url(worker_id=worker_id)

    @classmethod
    def _get_request_body(cls, method, operation):
        if method == 'GET':
            return None

        return operation.to_json()

    @classmethod
    def _get_url(cls, url, method, operation):
        if method == 'GET':
            return '%s?request=%s' % (url, operation.to_url())

        return url

    @classmethod
    def _transform_response(cls, response):
        """Transforms worker success/error responses into a standard format."""

        try:
            parsed = transforms.loads(response.content)

            if not cls._check_response(parsed):
                raise ValueError

            return {_PAYLOAD: parsed[_PAYLOAD]}
        except:  # Catch everything on purpose. pylint: disable=bare-except
            _LOG.error(
                'Unable to parse worker response: ' + response.content)
            return {_PAYLOAD: 'Received invalid response'}

    @classmethod
    def create_task(cls, operation):
        return cls._do_fetch(cls._get_create_task_url(), 'POST', operation)

    @classmethod
    def get_project(cls, operation):
        return cls._do_fetch(cls._get_get_project_url(), 'GET', operation)

    @classmethod
    def get_task(cls, operation):
        return cls._do_fetch(
            cls._get_get_task_url(operation.worker_id), 'GET', operation)


class _BaseRestHandler(utils.BaseRESTHandler):

    def _send_json_response(self, code, response):
        self.response.headers['Content-Disposition'] = 'attachment'
        self.response.headers['Content-Type'] = (
            'application/javascript; charset=utf-8')
        self.response.headers['X-Content-Type-Options'] = 'nosniff'
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.status_code = code
        self.response.write(transforms.dumps(response))

    def _check_config_or_send_error(self):
        if not EXTERNAL_TASK_BALANCER_REST_ENABLED.value:
            self._send_json_response(404, 'Not found.')
            return False
        elif not EXTERNAL_TASK_BALANCER_WORKER_URL.value:
            self._send_json_response(500, 'No worker pool found.')
            return False

        return True


class _ProjectRestHandler(_BaseRestHandler):

    def get(self):
        configured = self._check_config_or_send_error()
        if not configured:
            return

        try:
            op = _GetProjectOperation.from_str(self.request.get('request'))
        except ValueError:
            self._send_json_response(400, 'Bad request')
            return

        self._send_json_response(*_WorkerPool.get_project(op))


class _TaskRestHandler(_BaseRestHandler):

    def _get_payload(self, response):
        return response.get(_PAYLOAD)

    def _get_status(self, response):
        return self._get_payload(response).get(_STATUS)

    def _get_task_payload(self, response):
        return response.get(_PAYLOAD).get(_PAYLOAD)

    def _get_ticket(self, response):
        return self._get_payload(response).get(_TICKET)

    def _get_worker_id(self, response):
        return self._get_payload(response).get(_WORKER_ID)

    def _retry_create_task(self, response, op):
        tries = 0

        while tries < _WORKER_LOCKED_MAX_RETRIES:
            tries += 1
            _LOG.info('Worker locked; retrying (tries: %s)', tries)
            code, response = _WorkerPool.create_task(op)

            if not self._worker_locked(response):
                return code, response

        return code, {_PAYLOAD: _WORKER_LOCKED}

    def _worker_locked(self, response):
        return response.get(_PAYLOAD) == _WORKER_LOCKED

    def get(self):
        configured = self._check_config_or_send_error()
        if not configured:
            return

        try:
            op = _GetTaskOperation.from_str(self.request.get('request'))
        except:  # pylint: disable=bare-except
            self._send_json_response(400, 'Bad request')
            return

        task = None
        try:
            task = Manager.get(op.ticket)
        except ValueError:
            pass  # Invalid ticket; handle as 404.

        if not task:
            self._send_json_response(
                404, 'Task not found for ticket %s' % op.ticket)
            return

        if task.is_done():
            self._send_json_response(200, task.for_json())
            return

        op.update({_WORKER_ID: task.worker_id})
        if not op.ready():
            # If the operation cannot be issued now, the most likely cause is
            # that a past response from a worker contained insufficient data to
            # dispatch requests to that worker (for example, it might not have)
            # set the worker_id). We cannot recover; all we can do is signal
            # likely programmer error.
            self._send_json_response(
                500, 'Unable to compose request for worker')
            return

        code, response = _WorkerPool.get_task(op)
        if code != 200:
            self._send_json_response(code, response)
            return

        status = self._get_status(response)
        if status is None:
            self._send_json_response(500, 'Worker sent partial response')
            return
        elif _ExternalTask.is_status_terminal(status):
            try:
                payload = self._get_task_payload(response)
                Manager.mark_done(op.ticket, status, payload)
            except:  # Catch everything. pylint: disable=bare-except
                # TODO(johncox): could differentiate here and transition to a
                # failed state when the payload is too big so we don't force
                # unnecessary refetches against workers.
                self._send_json_response(
                    500, 'Invalid worker status or payload too big')
                return

        self._send_json_response(*_WorkerPool.get_task(op))

    def post(self):
        configured = self._check_config_or_send_error()
        if not configured:
            return

        try:
            op = _CreateTaskOperation.from_str(self.request.get('request'))
        except:  # pylint: disable=bare-except
            self._send_json_response(400, 'Bad request')
            return

        # Must allocate ticket at storage level for wire ops against worker, so
        # we cannot create the task in one datastore call.
        ticket = Manager.create(user_id=op.user_id)
        op.update({_TICKET: ticket})

        if not op.ready():
            self._send_json_response(
                500, 'Unable to compose request for worker')
            return

        code, response = _WorkerPool.create_task(op)
        if self._worker_locked(response):
            code, response = self._retry_create_task(response, op)
            if code != 200:
                Manager.mark_failed(ticket)
                self._send_json_response(500, self._get_payload(response))
                return

        request_failed = code != 200
        ticket_mismatch = self._get_ticket(response) != ticket
        if request_failed or ticket_mismatch:
            response = 'Ticket mismatch' if ticket_mismatch else 'Worker failed'
            Manager.mark_failed(ticket)
            self._send_json_response(500, response)
        else:  # Worker response indicates success.
            Manager.mark_running(ticket, self._get_worker_id(response))
            self._send_json_response(code, response)


custom_module = None


def register_module():

    global custom_module  # pylint: disable=global-statement

    global_handlers = [
        (_REST_URL_TASK, _TaskRestHandler),
        (_REST_URL_PROJECT, _ProjectRestHandler),
    ]
    namespaced_handlers = []
    custom_module = custom_modules.Module(
        'External Task Balancer', 'External Task Balancer', global_handlers,
        namespaced_handlers)

    return custom_module
