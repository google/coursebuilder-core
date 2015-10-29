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

"""Libraries for writing extract-transform-load scripts."""

__author__ = [
    'johncox@google.com',
]

import argparse
import datetime
import logging
import sys
import time

from common import utils as common_utils
from controllers import sites
from models import courses

_LOG = logging.getLogger('coursebuilder.tools.etl')


def get_context(course_url_prefix):
    """Gets requested application context from the given course URL prefix.

    Args:
        course_url_prefix: string. Value of etl.py's course_url_prefix flag.

    Returns:
        sites.ApplicationContext.
    """
    found = None
    for context in sites.get_all_courses():
        if context.raw.startswith('course:%s:' % course_url_prefix):
            found = context
            break
    return found


def get_course(app_context):
    """Gets a courses.Course from the given sites.ApplicationContext.

    Does not ensure the course exists on the backend; validation should be done
    by the caller when getting the app_context object.

    Args:
        app_context: sites.ApplicationContext. The context we're getting the
            course for.

    Returns:
        courses.Course.
    """

    class _Adapter(object):

        def __init__(self, app_context):
            self.app_context = app_context

    return courses.Course(_Adapter(app_context))


class Job(object):
    """Abstract base class for user-defined custom ETL jobs.

    Custom jobs can be executed by etl.py. The advantage of this is that they
    can run arbitrary local computations, but calls to App Engine services
    (db.get() or db.put(), for example) are executed against a remote server.
    This allows you to perform arbitrary computations against your app's data,
    and to construct data pipelines that are not possible within the App Engine
    execution environment.

    When you run your custom job under etl.py in this way, it authenticates
    against the remote server. It then configures the local environment so RPCs
    execute against the requested remote endpoint.

    It then imports your custom job. Your job must be a Python class that is
    a child of this class. Before invoking etl.py, you must configure sys.path
    so all required libraries are importable. See etl.py for details. Your
    class must override main() with the computations you want your job to
    perform.

    You invoke your custom job via etl.py:

    $ python etl.py run path.to.my.Job /cs101 server.appspot.com \
        --job_args='more_args --delegated_to my.Job'

    Before main() is executed, arguments are parsed. The full set of parsed
    arguments passed to etl.py are available in your job as self.etl_args. The
    arguments passed as a quote-enclosed string to --job_args, if any, are
    delegated to your job. An argument parser is available as self.parser. You
    must override self._configure_parser to register command-line arguments for
    parsing. They will be parsed in advance of running main() and will be
    available as self.args.

    See tools/etl/examples.py for some nontrivial sample job implementations.
    """

    def __init__(self, parsed_etl_args):
        """Constructs a new job.

        Args:
            parsed_etl_args: argparse.Namespace. Parsed arguments passed to
                etl.py.
        """
        self._parsed_args = None
        self._parsed_etl_args = parsed_etl_args
        self._parser = None

    def _configure_parser(self):
        """Configures custom command line parser for this job, if any.

        For example:

        self.parser.add_argument(
            'my_arg', help='A required argument', type=str)
        """
        pass

    def main(self):
        """Computations made by this job; must be overridden in subclass."""
        pass

    @property
    def args(self):
        """Returns etl.py's parsed --job_args, or None if run() not invoked."""
        return self._parsed_args

    @property
    def etl_args(self):
        """Returns parsed etl.py arguments."""
        return self._parsed_etl_args

    @property
    def parser(self):
        """Returns argparse.ArgumentParser, or None if run() not yet invoked."""
        if not self._parser:
            self._parser = argparse.ArgumentParser(
                prog='%s.%s' % (
                    self.__class__.__module__, self.__class__.__name__),
                usage=(
                    'etl.py run %(prog)s [etl.py options] [--job_args] '
                    '[%(prog)s options]'))
        return self._parser

    def _parse_args(self):
        self._configure_parser()
        self._parsed_args = self.parser.parse_args(
            self._parsed_etl_args.job_args)

    def run(self):
        """Executes the job; called for you by etl.py."""
        self._parse_args()
        self.main()


class CourseJob(Job):

    @classmethod
    def _get_app_context_or_die(cls, course_url_prefix):
        app_context = get_context(course_url_prefix)
        if not app_context:
            _LOG.critical('Unable to find course with url prefix ' +
                          course_url_prefix)
            sys.exit(1)
        return app_context

    def run(self):
        app_context = self._get_app_context_or_die(
            self.etl_args.course_url_prefix)
        course = courses.Course(None, app_context=app_context)

        sites.set_path_info(app_context.slug)
        courses.Course.set_current(course)
        try:
            with common_utils.Namespace(app_context.get_namespace_name()):
                super(CourseJob, self).run()
        finally:
            courses.Course.clear_current()
            sites.unset_path_info()



class _ProgressReporter(object):
    """Provide intermittent reports on progress of a long-running operation."""

    def __init__(self, logger, verb, noun, chunk_size, total, num_history=10):
        self._logger = logger
        self._verb = verb
        self._noun = noun
        self._chunk_size = chunk_size
        self._total = total
        self._num_history = num_history
        self._rate_history = []
        self._start_time = self._chunk_start_time = time.time()
        self._total_count = 0
        self._chunk_count = 0

    def count(self, quantity=1):
        self._total_count += quantity
        self._chunk_count += quantity
        while self._chunk_count >= self._chunk_size:
            now = time.time()
            self._chunk_count -= self._chunk_size
            self._rate_history.append(now - self._chunk_start_time)
            self._chunk_start_time = now
            while len(self._rate_history) > self._num_history:
                del self._rate_history[0]
            self.report()

    def get_count(self):
        return self._total_count

    def report(self):
        now = time.time()
        total_time = datetime.timedelta(
            days=0, seconds=int(now - self._start_time))

        if not sum(self._rate_history):
            rate = 0
            time_left = 0
            expected_total = 0
        else:
            rate = ((len(self._rate_history) * self._chunk_size) /
                    sum(self._rate_history))
            time_left = datetime.timedelta(
                days=0,
                seconds=int((self._total - self._total_count) / rate))
            expected_total = datetime.timedelta(
                days=0, seconds=int(self._total / rate))
        self._logger.info(
            '%(verb)s %(total_count)9d of %(total)d %(noun)s '
            'in %(total_time)s.  Recent rate is %(rate)d/sec; '
            '%(time_left)s seconds to go '
            '(%(expected_total)s total) at this rate.' %
            {
                'verb': self._verb,
                'total_count': self._total_count,
                'total': self._total,
                'noun': self._noun,
                'total_time': total_time,
                'rate': rate,
                'time_left': time_left,
                'expected_total': expected_total
            })
