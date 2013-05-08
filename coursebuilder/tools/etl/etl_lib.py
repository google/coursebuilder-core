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
from controllers import sites


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


class Job(object):
    """Abstract base class for user-defined custom ETL jobs.

    Custom jobs can be executed by etl.py. The advantage of this is that they
    can run arbitrary local computations, but calls to App Engine services
    (db.get() or db.put(), for example) are executed against a remove server.
    This allows you to perform arbitrary computations against your app's data,
    and to construct data pipelines that are not possible within the App Engine
    execution environment.

    When you run your custom job under etl.py in this way, it authenticates
    against the remove server, prompting the user for credentials if necessary.
    It then configures the local environment so RPCs execute against the
    requested remote endpoint.

    It then imports your custom job. Your job must be a Python class that is
    a child of this class. Before invoking etl.py, you must configure sys.path
    so all required libraries are importable. See etl.py for details. Your
    class must override main() with the computations you want your job to
    perform.

    You invoke your custom job via etl.py:

    $ python etl.py run path.to.my.Job /cs101 myapp server.appspot.com \
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
