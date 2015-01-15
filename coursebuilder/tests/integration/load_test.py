# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Performance test for a peer review system.

WARNING! Use this script to test load Course Builder. This is very dangerous
feature, be careful, because anyone can impersonate super user of your Course
Builder instance; use only if you have to perform specific load testing

Keep in mind:
    - when repeatedly running tests and creating new test namespaces,
      flush memcache

Here is how to run:
    - update /controllers/sites.py and enable CAN_IMPERSONATE
    - navigate to the root directory of the app
    - run a command line by typing:
        python tests/integration/load_test.py \
        --thread_count=5 \
        --start_uid=1 \
        https://mycourse.appspot.com

If you use http instead of https, your tests will fail because your requests
will instantly be redirected (which can confound GET vs POST, for example).
"""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import argparse
import cookielib
import json
import logging
import random
import re
import sys
import threading
import time
import urllib
import urllib2


# The unit id for the peer review assignment in the default course.
LEGACY_REVIEW_UNIT_ID = 'ReviewAssessmentExample'


# command line arguments parser
PARSER = argparse.ArgumentParser()
PARSER.add_argument(
    'base_url', help=('Base URL of the course you want to test'), type=str)
PARSER.add_argument(
    '--start_uid',
    help='Initial value for unique thread identifier.', default=1, type=int)
PARSER.add_argument(
    '--thread_count',
    help='Number of concurrent threads for executing the test.',
    default=1, type=int)
PARSER.add_argument(
    '--iteration_count',
    help='Number of iterations for executing the test. Each thread of each '
    'iteration acts as a unique user with the uid equal to:'
    'start_uid + thread_count * iteration_index.',
    default=1, type=int)


def assert_contains(needle, haystack):
    if needle not in haystack:
        raise Exception('Expected to find term: %s\n%s', needle, haystack)


def assert_does_not_contain(needle, haystack):
    if needle in haystack:
        raise Exception('Did not expect to find term: %s\n%s', needle, haystack)


def assert_equals(expected, actual):
    if expected != actual:
        raise Exception('Expected equality of %s and %s.', expected, actual)


class WebSession(object):
    """A class that allows navigation of web pages keeping cookie session."""

    PROGRESS_LOCK = threading.Lock()
    MAX_RETRIES = 3
    RETRY_SLEEP_SEC = 3

    GET_COUNT = 0
    POST_COUNT = 0
    RETRY_COUNT = 0
    PROGRESS_BATCH = 10
    RESPONSE_TIME_HISTOGRAM = [0, 0, 0, 0, 0, 0]

    def __init__(self, uid, common_headers=None):
        if common_headers is None:
            common_headers = {}
        self.uid = uid
        self.common_headers = common_headers
        self.cj = cookielib.CookieJar()
        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cj))

    @classmethod
    def increment_duration_bucket(cls, index):
        cls.RESPONSE_TIME_HISTOGRAM[index] += 1

    @classmethod
    def update_duration(cls, duration):
        if duration > 30:
            cls.increment_duration_bucket(0)
        elif duration > 15:
            cls.increment_duration_bucket(1)
        elif duration > 7:
            cls.increment_duration_bucket(2)
        elif duration > 3:
            cls.increment_duration_bucket(3)
        elif duration > 1:
            cls.increment_duration_bucket(4)
        else:
            cls.increment_duration_bucket(5)

    @classmethod
    def log_progress(cls, force=False):
        update = ((cls.GET_COUNT + cls.POST_COUNT) % (
            cls.PROGRESS_BATCH) == 0)
        if update or force:
            logging.info(
                'GET/POST:[%s, %s], RETRIES:[%s], SLA:%s',
                cls.GET_COUNT, cls.POST_COUNT, cls.RETRY_COUNT,
                cls.RESPONSE_TIME_HISTOGRAM)

    def get_cookie_value(self, name):
        for cookie in self.cj:
            if cookie.name == name:
                return cookie.value
        return None

    def is_soft_error(self, http_error):
        """Checks if HTTPError is due to starvation of frontend instances."""
        body = http_error.fp.read()

        # this is the text specific to the front end instance starvation, which
        # is a retriable error for both GET and POST; normal HTTP error 500 has
        # this specific text '<h1>500 Internal Server Error</h1>'
        if http_error.code == 500 and '<h1>Error: Server Error</h1>' in body:
            return True

        logging.error(
            'Non-retriable HTTP %s error:\n%s', http_error.code, body)
        return False

    def open(self, request, hint):
        """Executes any HTTP request."""
        start_time = time.time()
        try:
            try_count = 0
            while True:
                try:
                    return self.opener.open(request)
                except urllib2.HTTPError as he:
                    if (
                            try_count < WebSession.MAX_RETRIES and
                            self.is_soft_error(he)):
                        try_count += 1
                        with WebSession.PROGRESS_LOCK:
                            WebSession.RETRY_COUNT += 1
                        time.sleep(WebSession.RETRY_SLEEP_SEC)
                        continue
                    raise he
        except Exception as e:
            logging.info(
                'Error in session %s executing: %s', self.uid, hint)
            raise e
        finally:
            with WebSession.PROGRESS_LOCK:
                self.update_duration(time.time() - start_time)

    def get(self, url, expected_code=200):
        """HTTP GET."""
        with WebSession.PROGRESS_LOCK:
            WebSession.GET_COUNT += 1
            self.log_progress()

        request = urllib2.Request(url)
        for key, value in self.common_headers.items():
            request.add_header(key, value)
        response = self.open(request, 'GET %s' % url)
        assert_equals(expected_code, response.code)
        return response.read()

    def post(self, url, args_dict, expected_code=200):
        """HTTP POST."""
        with WebSession.PROGRESS_LOCK:
            WebSession.POST_COUNT += 1
            self.log_progress()

        data = None
        if args_dict:
            data = urllib.urlencode(args_dict)
        request = urllib2.Request(url, data)
        for key, value in self.common_headers.items():
            request.add_header(key, value)
        response = self.open(request, 'POST %s' % url)
        assert_equals(expected_code, response.code)
        return response.read()


class TaskThread(threading.Thread):
    """Runs a task in a separate thread."""

    def __init__(self, func, name=None):
        super(TaskThread, self).__init__()
        self.func = func
        self.exception = None
        self.name = name

    @classmethod
    def start_all_tasks(cls, tasks):
        """Starts all tasks."""
        for task in tasks:
            task.start()

    @classmethod
    def check_all_tasks(cls, tasks):
        """Checks results of all tasks; fails on the first exception found."""
        failed_count = 0
        for task in tasks:
            while True:
                # Timeouts should happen after 30 seconds.
                task.join(30)
                if task.isAlive():
                    logging.info('Still waiting for: %s.', task.name)
                    continue
                else:
                    break
            if task.exception:
                failed_count += 1

        if failed_count:
            raise Exception('Tasks failed: %s', failed_count)

    @classmethod
    def execute_task_list(cls, tasks):
        """Starts all tasks and checks the results."""
        cls.start_all_tasks(tasks)
        cls.check_all_tasks(tasks)

    def run(self):
        try:
            self.func()
        except Exception as e:  # pylint: disable=broad-except
            logging.error('Error in %s: %s', self.name, e)
            self.exc_info = sys.exc_info()
            raise self.exc_info[1], None, self.exc_info[2]


class LoadTest(object):
    """Parent for all load tests."""

    def __init__(self, base_url, uid):
        self.uid = uid
        self.host = base_url

        # this is an impersonation identity for the actor thread
        self.email = 'load_test_bot_%s@example.com' % self.uid
        self.name = 'Load Test Bot #%s' % self.uid

        # begin web session
        impersonate_header = {
            'email': self.email, 'user_id': u'impersonation-%s' % self.uid}
        self.session = WebSession(
            uid=uid,
            common_headers={'Gcb-Impersonate': json.dumps(impersonate_header)})

    def get_hidden_field(self, name, body):
        # The "\s*" denotes arbitrary whitespace; sometimes, this tag is split
        # across multiple lines in the HTML.
        # pylint: disable=anomalous-backslash-in-string
        reg = re.compile(
            '<input type="hidden" name="%s"\s* value="([^"]*)">' % name)
        # pylint: enable=anomalous-backslash-in-string
        return reg.search(body).group(1)

    def register_if_has_to(self):
        """Performs student registration action."""
        body = self.session.get('%s/' % self.host)
        assert_contains('Logout', body)
        if 'href="register"' not in body:
            body = self.session.get('%s/student/home' % self.host)
            assert_contains(self.email, body)
            assert_contains(self.name, body)
            return False

        body = self.session.get('%s/register' % self.host)
        xsrf_token = self.get_hidden_field('xsrf_token', body)

        data = {'xsrf_token': xsrf_token, 'form01': self.name}
        body = self.session.post('%s/register' % self.host, data)

        body = self.session.get('%s/' % self.host)
        assert_contains('Logout', body)
        assert_does_not_contain('href="register"', body)

        return True


class PeerReviewLoadTest(LoadTest):
    """A peer review load test."""

    def run(self):
        self.register_if_has_to()
        self.submit_peer_review_assessment_if_possible()

        while self.count_completed_reviews() < 2:
            self.request_and_do_a_review()

    def get_js_var(self, name, body):
        reg = re.compile('%s = \'([^\']*)\';\n' % name)
        return reg.search(body).group(1)

    def get_draft_review_url(self, body):
        """Returns the URL of a draft review on the review dashboard."""
        # The "\s*" denotes arbitrary whitespace; sometimes, this tag is split
        # across multiple lines in the HTML.
        # pylint: disable=anomalous-backslash-in-string
        reg = re.compile(
            '<a href="([^"]*)">Assignment [0-9]+</a>\s*\(Draft\)')
        # pylint: enable=anomalous-backslash-in-string
        result = reg.search(body)
        if result is None:
            return None
        return result.group(1)

    def submit_peer_review_assessment_if_possible(self):
        """Submits the peer review assessment."""
        body = self.session.get(
            '%s/assessment?name=%s' % (self.host, LEGACY_REVIEW_UNIT_ID))
        assert_contains('You may only submit this assignment once', body)

        if 'Submitted assignment' in body:
            # The assignment was already submitted.
            return True

        assessment_xsrf_token = self.get_js_var('assessmentXsrfToken', body)

        answers = [
            {'index': 0, 'type': 'regex',
             'value': 'Answer 0 by %s' % self.email},
            {'index': 1, 'type': 'choices', 'value': self.uid},
            {'index': 2, 'type': 'regex',
             'value': 'Answer 2 by %s' % self.email},
        ]

        data = {
            'answers': json.dumps(answers),
            'assessment_type': LEGACY_REVIEW_UNIT_ID,
            'score': 0,
            'xsrf_token': assessment_xsrf_token,
        }
        body = self.session.post('%s/answer' % self.host, data)
        assert_contains('Review peer assignments', body)
        return True

    def request_and_do_a_review(self):
        """Request a new review, wait for it to be granted, then submit it."""
        review_dashboard_url = (
            '%s/reviewdashboard?unit=%s' % (self.host, LEGACY_REVIEW_UNIT_ID))

        completed = False
        while not completed:
            # Get peer review dashboard and inspect it.
            body = self.session.get(review_dashboard_url)
            assert_contains('Assignments for your review', body)
            assert_contains('Review a new assignment', body)

            # Pick first pending review if any or ask for a new review.
            draft_review_url = self.get_draft_review_url(body)
            if draft_review_url:  # There is a pending review. Choose it.
                body = self.session.get(
                    '%s/%s' % (self.host, draft_review_url))
            else:  # Request a new assignment to review.
                assert_contains('xsrf_token', body)
                xsrf_token = self.get_hidden_field('xsrf_token', body)
                data = {
                    'unit_id': LEGACY_REVIEW_UNIT_ID,
                    'xsrf_token': xsrf_token,
                }
                body = self.session.post(review_dashboard_url, data)

                # It is possible that we fail to get a new review because the
                # old one is now visible, but was not yet visible when we asked
                # for the dashboard page.
                if (
                        'You must complete all assigned reviews before you '
                        'can request a new one.' in body):
                    continue

                # It is possible that no submissions available for review yet.
                # Wait for a while until they become available on the dashboard
                # page.
                if 'Back to the review dashboard' not in body:
                    assert_contains('Assignments for your review', body)
                    # Sleep for a random number of seconds between 1 and 4.
                    time.sleep(1.0 + random.random() * 3.0)
                    continue

            # Submit the review.
            review_xsrf_token = self.get_js_var('assessmentXsrfToken', body)
            answers = [
                {'index': 0, 'type': 'choices', 'value': 0},
                {'index': 1, 'type': 'regex',
                 'value': 'Review 0 by %s' % self.email},
            ]
            data = {
                'answers': json.dumps(answers),
                'assessment_type': None,
                'is_draft': 'false',
                'key': self.get_js_var('assessmentGlobals.key', body),
                'score': 0,
                'unit_id': LEGACY_REVIEW_UNIT_ID,
                'xsrf_token': review_xsrf_token,
            }
            body = self.session.post('%s/review' % self.host, data)
            assert_contains('Your review has been submitted', body)
            return True

    def count_completed_reviews(self):
        """Counts the number of reviews that the actor has completed."""
        review_dashboard_url = (
            '%s/reviewdashboard?unit=%s' % (self.host, LEGACY_REVIEW_UNIT_ID))

        body = self.session.get(review_dashboard_url)
        num_completed = body.count('(Completed)')
        return num_completed


class WelcomeNotificationLoadTest(LoadTest):
    """Tests registration confirmation notifications.

    You must enable notifications in the target course for this test to be
    meaningful. You must also swap the test class that's instantiated in
    run_all, below.
    """

    def run(self):
        self.register_if_has_to()


def run_all(args):
    """Runs test scenario in multiple threads."""
    if args.thread_count < 1 or args.thread_count > 256:
        raise Exception('Please use between 1 and 256 threads.')

    start_time = time.time()
    logging.info('Started testing: %s', args.base_url)
    logging.info('base_url: %s', args.base_url)
    logging.info('start_uid: %s', args.start_uid)
    logging.info('thread_count: %s', args.thread_count)
    logging.info('iteration_count: %s', args.iteration_count)
    logging.info('SLAs are [>30s, >15s, >7s, >3s, >1s, <1s]')
    try:
        for iteration_index in range(0, args.iteration_count):
            logging.info('Started iteration: %s', iteration_index)
            tasks = []
            WebSession.PROGRESS_BATCH = args.thread_count
            for index in range(0, args.thread_count):
                test = PeerReviewLoadTest(
                    args.base_url,
                    (
                        args.start_uid +
                        iteration_index * args.thread_count +
                        index))
                task = TaskThread(
                    test.run, name='PeerReviewLoadTest-%s' % index)
                tasks.append(task)
            try:
                TaskThread.execute_task_list(tasks)
            except Exception as e:
                logging.info('Failed iteration: %s', iteration_index)
                raise e
    finally:
        WebSession.log_progress(force=True)
        logging.info('Done! Duration (s): %s', time.time() - start_time)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_all(PARSER.parse_args())
