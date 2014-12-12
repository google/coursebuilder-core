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

"""Module providing simplistic logger."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import datetime
import logging
import traceback

import appengine_config

_LOG_DATE_FORMAT = '%Y-%m-%dT%H:%M:%S.%f'
_CRITICAL = 'critical'
_WARNING = 'warning'
_INFO = 'info'


class CatchAndLog(object):
    """Simplistic logger allowing WebApp handlers to note errors for consumers.

    During processing of a request, there may be recoverable errors and other
    noteworthy events.  This logger allows components to simply note these so
    that they can be reported, rather than having to report only the first
    problem, or trying to encode multiple events into a single HTTP response
    code.
    """

    class _Catcher(object):
        """Automatically note thrown exceptions as log messages."""

        def __init__(self, log, consume_exceptions, message):
            self._log = log
            self._consume_exceptions = consume_exceptions
            self._message = message

        def __enter__(self):
            return self

        def __exit__(self, ex_type, value, tb):
            if ex_type:
                frame_tuple = list(traceback.extract_tb(tb)[-1])
                frame_tuple[0] = frame_tuple[0].replace(
                    appengine_config.CODE_ROOT, '')
                exception_message = (
                    '%s: %s: %s' %
                    (self._message, ex_type.__name__, str(value)))
                if not appengine_config.PRODUCTION_MODE:
                    exception_message += (
                        ' at %s' % traceback.format_list([frame_tuple])[0])
                self._log.critical(exception_message)
                return self._consume_exceptions

    def __init__(self):
        self._messages = []

    def consume_exceptions(self, message):
        """Convert exceptions into 'critical' log messages.

        This is a convenience function for use in contexts where exceptions
        may be raised, but are not fatal and should not propagate.  Usage:

        with log.log_and_consume_exceptions("Arming mouse trap"):
            mouse_trap.set_bait('Wensleydale')
            mouse_trap.set_closing_force('critical personal injury')
            mouse_trap.arm()

        Args:
          message: Prepended to exception messages to give more context.
              E.g., suppose some calling code receives an exception:
              OutOfCheeseException('Can't open pantry!').  That may be true,
              neither is it very helpful.  If this is expressed as:
              Arming mouse trap: OutOfCheeseException: Can't open pantry!
              then the external caller has a somewhat better idea of why
              being out of cheese is a problem.
        Returns:
          A context manager for use in a 'with' statement.
        """
        return CatchAndLog._Catcher(
            self, consume_exceptions=True, message=message)

    def propagate_exceptions(self, message):
        """Log exceptions as 'critical' log messages, and propagate them.

        See log_and_consume_exceptions() for usage.

        Args:
          message: Prepended to exception messages to give more context.
        Returns:
          A context manager for use in a 'with' statement.
        """
        return CatchAndLog._Catcher(
            self, consume_exceptions=False, message=message)

    def _log(self, level, message):
        self._messages.append({
            'message': message,
            'level': level,
            'timestamp': datetime.datetime.now().strftime(_LOG_DATE_FORMAT)})

    def critical(self, message):
        self._log(_CRITICAL, message)
        logging.critical(message)

    def warning(self, message):
        self._log(_WARNING, message)
        logging.warning(message)

    def warn(self, message):
        self._log(_WARNING, message)
        logging.warning(message)

    def info(self, message):
        self._log(_INFO, message)
        logging.info(message)

    def get(self):
        return self._messages
