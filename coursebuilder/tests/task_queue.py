# Copyright 2014 Google Inc. All Rights Reserved.
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

"""Module providing handlers for running jobs added to task queue in tests."""

__author__ = 'Mike Gainer (mgainer@google.com)'

# The following import is needed in order to configure modules.mapreduce
# before code in this module references it.
import base64
import re

import appengine_config  # pylint: disable=unused-import

from common import utils as common_utils
from models import custom_modules
from modules.mapreduce import mapreduce_module

from google.appengine.ext import deferred


class TaskQueueItemHandler(object):

    def matches(self, task):
        raise NotImplementedError(
            'Classes derived from TaskQueueItemHandler are expected to '
            'implement "matches()".  This should return True or False.'
            'If True, then the run() method in this class will be called '
            'to process the task.  The "task" parameter is a task as '
            'found on the task queue.  Tasks are just hashes with the '
            'following keys: '
            '"url": URL to which the content of the task is to be sent. '
            '"body": Opaque string containing a body to be handled by '
            '  the specified URL handler'
            '"name": Name of task on queue.  Typically something like '
            '  task1, task2, ...'
            '"eta_delta": Expected completion time as a delta.'
            '"queue_name": Name of queue on which this task was found. '
            '  Typically "default".'
            '"headers": Headers to be sent when the URL is POSTed or GETed.'
            '"eta": Expected completion time.'
            '"eta_usec": Microseconds of expected completion time'
            '"method": GET or POST')

    def run(self, task):
        raise NotImplementedError(
            'Classes derived from TaskQueueItemHandler are expected to '
            'implement "run()".  This method should operate to invoke '
            'the handler associated with the URL in the task, or if that '
            'handler is not available, perform the equivalent operations.')


class DeferredTaskQueueItemHandler(TaskQueueItemHandler):
    """Simulate operation of the '/_ah/queue/deferred' handler.

    The 'deferred' library is a wrapper on top of AppEngine task queues.
    In testing environments, this handler is not registered, and we need
    to simulate its operation.
    """

    def matches(self, task):
        return task['url'] == '/_ah/queue/deferred'

    def run(self, task):
        data = base64.b64decode(task['body'])
        namespace = dict(task['headers']).get(
            'X-AppEngine-Current-Namespace', '')
        with common_utils.Namespace(namespace):
            deferred.run(data)


class PostingTaskQueueItemHandler(TaskQueueItemHandler):

    def __init__(self, testapp):
        self._testapp = testapp

    def run(self, task):
        namespace = dict(task['headers']).get(
            'X-AppEngine-Current-Namespace', '')

        data = base64.b64decode(task['body'])
        # Work around unicode/string non-conversion bug in old versions.
        headers = {key: str(val) for key, val in task['headers']}
        headers['Content-Length'] = str(len(data))
        with common_utils.Namespace(namespace):
            response = self._testapp.post(
                url=str(task['url']), params=data, headers=headers)
        if response.status_code != 200:
            raise RuntimeError(
                'Failed calling map/reduce task for url %s; response was %s' % (
                    task['url'],
                    str(response)))


class MapReduceTaskQueueItemHandler(PostingTaskQueueItemHandler):
    """Pass task queue items through to actually-registered Map/Reduce handlers.

    The map/reduce internals enqueue a number of tasks onto the task queue
    in order to complete a map/reduce pipeline.  These are handled as normal
    POSTs to the various handler URLs.  However, given that we are at a
    backleveled version of the AppEngine runtime, we need to do some minor
    conversions in order to work around compatibility problems between
    the old AppEngine runtime and some assumptions made by the Map Reduce code.
    """

    def __init__(self, testapp):
        super(MapReduceTaskQueueItemHandler, self).__init__(testapp)
        self._mapreduce_path_regex = re.compile('|'.join(
            ['^' + path + r'/?(\?.*)?$' for path, unused_handler in
             mapreduce_module.custom_module.global_routes]))

    def matches(self, task):
        match = self._mapreduce_path_regex.search(task['url'])
        return match is not None


class GlobalUrlItemHandler(PostingTaskQueueItemHandler):
    """Locate handlers for task queue items in registered modules."""

    def __init__(self, testapp):
        super(GlobalUrlItemHandler, self).__init__(testapp)

    def matches(self, task):
        url = task['url']
        for module in custom_modules.Registry.registered_modules.itervalues():
            for route in module.global_routes:
                if url == route[0]:
                    return True
        return False


class TaskQueueHandlerDispatcher(object):

    def __init__(self, testapp, task_queue):
        self._handlers = []
        self._task_queue = task_queue

        # We could establish the list of handlers for task item queues
        # from module setup calls.  On the other hand, that would be
        # forcing test-related concerns into production code, so it's
        # simpler to just nail these in by hand here.
        self._handlers.append(DeferredTaskQueueItemHandler())
        self._handlers.append(MapReduceTaskQueueItemHandler(testapp))
        self._handlers.append(GlobalUrlItemHandler(testapp))

    def dispatch_task(self, task):
        found_handler = False
        for handler in self._handlers:
            if handler.matches(task):
                found_handler = True
                self._task_queue.DeleteTask(task['queue_name'], task['name'])
                handler.run(task)
                break

        if not found_handler:
            raise RuntimeError(
                'Did not find any task queue handler to work on url "%s"' %
                task['url'])
