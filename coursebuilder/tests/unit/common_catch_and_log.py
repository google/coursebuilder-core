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


"""Unit tests for logger."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import datetime
import unittest

import appengine_config
from common import catch_and_log


class CatchAndLogTests(unittest.TestCase):

    def setUp(self):
        appengine_config.PRODUCTION_MODE = False
        self._catch_and_log = catch_and_log.CatchAndLog()
        self._expected = []

    def test_simple(self):
        complaint = 'No cheese, Gromit!'
        self._catch_and_log.critical(complaint)
        self._expect(complaint, catch_and_log._CRITICAL)
        self._assert_logs_match()

    def test_multiple(self):
        complaints = [
            'Failed to find cheese in pantry',
            'Failed to install cheese to mousetrap',
            'Failed to arm trap',
            'Failed to catch mouse'
            ]
        for complaint in complaints:
            self._catch_and_log.critical(complaint)
            self._expect(complaint, catch_and_log._CRITICAL)
        self._assert_logs_match()

    def test_multiple_levels(self):
        complaint = 'No cheese, Gromit!'
        self._catch_and_log.critical(complaint)
        self._expect(complaint, catch_and_log._CRITICAL)

        complaint = 'Moon out of range!'
        self._catch_and_log.warn(complaint)
        self._expect(complaint, catch_and_log._WARNING)

        complaint = 'Parking brake engaged!'
        self._catch_and_log.warning(complaint)
        self._expect(complaint, catch_and_log._WARNING)

        complaint = 'Five mice spectating'
        self._catch_and_log.info(complaint)
        self._expect(complaint, catch_and_log._INFO)

        complaint = 'Red light blinking'
        self._catch_and_log.info(complaint)
        self._expect(complaint, catch_and_log._INFO)

        complaint = 'Low blinker fluid'
        self._catch_and_log.warning(complaint)
        self._expect(complaint, catch_and_log._WARNING)

        complaint = 'Insufficient fuel for landing!'
        self._catch_and_log.critical(complaint)
        self._expect(complaint, catch_and_log._CRITICAL)
        self._assert_logs_match()

    def test_exception_suppressed(self):
        topic = 'Entering Orbit'
        complaint = 'Perigee below surface of Moon!'
        with self._catch_and_log.consume_exceptions(topic):
            raise ValueError(complaint)

        self._expect(
            '%s: ValueError: %s at   ' % (topic, complaint) +
            'File "/tests/unit/common_catch_and_log.py", line 86, in '
            'test_exception_suppressed\n    raise ValueError(complaint)\n',
            catch_and_log._CRITICAL)
        self._assert_logs_match()

    def test_exception_propagates(self):
        topic = 'Entering Orbit'
        complaint = 'Perigee below surface of Moon!'
        with self.assertRaises(ValueError):
            with self._catch_and_log.propagate_exceptions(topic):
                raise ValueError(complaint)

        self._expect(
            '%s: ValueError: %s at   ' % (topic, complaint) +
            'File "/tests/unit/common_catch_and_log.py", line 100, in '
            'test_exception_propagates\n    raise ValueError(complaint)\n',
            catch_and_log._CRITICAL)
        self._assert_logs_match()

    def test_traceback_info_suppressed_in_production(self):
        appengine_config.PRODUCTION_MODE = True
        topic = 'Entering Orbit'
        complaint = 'Perigee below surface of Moon!'
        with self._catch_and_log.consume_exceptions(topic):
            raise ValueError(complaint)

        self._expect('%s: ValueError: %s' % (topic, complaint),
                     catch_and_log._CRITICAL)
        self._assert_logs_match()

    def _expect(self, message, level):
        self._expected.append({
            'message': message,
            'level': level,
            'timestamp': datetime.datetime.now().strftime(
                catch_and_log._LOG_DATE_FORMAT)})

    def _assert_logs_match(self):
        if len(self._expected) != len(self._catch_and_log.get()):
            self.fail('Expected %d entries, but have %d' %
                      (len(self._expected), len(self._catch_and_log.get())))

        for expected, actual in zip(self._expected, self._catch_and_log.get()):
            self.assertEquals(expected['level'], actual['level'])
            self.assertEquals(expected['message'], actual['message'])
            expected_time = datetime.datetime.strptime(
                expected['timestamp'], catch_and_log._LOG_DATE_FORMAT)
            actual_time = datetime.datetime.strptime(
                actual['timestamp'], catch_and_log._LOG_DATE_FORMAT)
            self.assertAlmostEqual(
                0, abs((expected_time - actual_time).total_seconds()), 1)
