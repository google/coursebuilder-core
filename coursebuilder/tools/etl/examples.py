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

"""Examples of custom extract-transform-load jobs.

Custom jobs are run via tools/etl/etl.py. You must do environment setup before
etl.py can be invoked; see its module docstring for details.

See tools/etl/etl_lib.py for documentation on writing Job subclasses.
"""

__author__ = [
    'johncox@google.com',
]

import os
import sys

import appengine_config
from common import utils as common_utils
from models import models
from tools.etl import etl_lib
from google.appengine.api import memcache


class PrintMemcacheStats(etl_lib.Job):
    """Example job that prints remote memcache statistics.

    Usage:

    etl.py run tools.etl.examples.PrintMemcacheStats /course \
        server.appspot.com

    Arguments to etl.py are documented in tools/etl/etl.py. You must do some
    environment configuration (setting up imports, mostly) before you can run
    etl.py; see the tools/etl/etl.py module-level docstring for details.
    """

    # String. Template to use when printing memcache stats.
    _STATS_TEMPLATE = """Global memcache stats:
\tHits: %(hits)s
\tItems in cache: %(items)s
\tMisses: %(misses)s
\tOldest item in seconds: %(oldest_item_age)s
\tTotal bytes in cache: %(bytes)s
\tTotal bytes retrieved via get: %(byte_hits)s"""

    def main(self):
        # Custom jobs execute locally, but can talk to remote services like the
        # datastore and memcache. Here we get the same memcache stats you can
        # see in the Memcache Viewer part of App Engine's admin console.
        print self._STATS_TEMPLATE % memcache.get_stats()


class UploadFileToCourse(etl_lib.Job):
    """Example job that writes a single local file to a remote server.

    Usage:

    etl.py run tools.etl.examples.UploadFileToCourse /course \
        server.appspot.com --job_args='/path/to/local/file path/to/remote/file'

    Arguments to etl.py are documented in tools/etl/etl.py. You must do some
    environment configuration (setting up imports, mostly) before you can run
    etl.py; see the tools/etl/etl.py module-level docstring for details.
    """

    def _configure_parser(self):
        # Add custom arguments by manipulating self.parser:
        self.parser.add_argument(
            'path', help='Absolute path of the file to upload', type=str)
        self.parser.add_argument(
            'target',
            help=('Internal Course Builder path to upload to (e.g. '
                  '"assets/img/logo.png")'), type=str)

    def main(self):
        # By the time main() is invoked, arguments are parsed and available as
        # self.args. If you need more complicated argument validation than
        # argparse gives you, do it here:
        if not os.path.exists(self.args.path):
            sys.exit('%s does not exist' % self.args.path)

        # Arguments passed to etl.py are also parsed and available as
        # self.etl_args. Here we use them to figure out the requested course's
        # context.
        context = etl_lib.get_context(self.etl_args.course_url_prefix)
        # Create the absolute path we'll write to.
        remote_path = os.path.join(
            appengine_config.BUNDLE_ROOT, self.args.target)

        with open(self.args.path) as f:
            # Perform the write using the context's filesystem. In a real
            # program you'd probably want to do additional work (preventing
            # overwrites of existing files, etc.).
            context.fs.impl.put(remote_path, f, is_draft=False)


class WriteStudentEmailsToFile(etl_lib.Job):
    """Example job that reads student emails from remote server to local file.

    Usage:

    etl.py run tools.etl.examples.WriteStudentEmailsToFile /course \
        server.appspot.com --job_args=/path/to/output_file

    Arguments to etl.py are documented in tools/etl/etl.py. You must do some
    environment configuration (setting up imports, mostly) before you can run
    etl.py; see the tools/etl/etl.py module-level docstring for details.
    """

    def _configure_parser(self):
        # Add custom arguments by manipulating self.parser.
        self.parser.add_argument(
            'path', help='Absolute path to save output to', type=str)
        self.parser.add_argument(
            '--batch_size', default=20,
            help='Number of students to download in each batch', type=int)

    def main(self):
        # By the time main() is invoked, arguments are parsed and available as
        # self.args. If you need more complicated argument validation than
        # argparse gives you, do it here:
        if self.args.batch_size < 1:
            sys.exit('--batch size must be positive')
        if os.path.exists(self.args.path):
            sys.exit('Cannot download to %s; file exists' % self.args.path)

        # Arguments passed to etl.py are also parsed and available as
        # self.etl_args. Here we use them to figure out the requested course's
        # namespace.
        namespace = etl_lib.get_context(
            self.etl_args.course_url_prefix).get_namespace_name()

        # Because our models are namespaced, we need to change to the requested
        # course's namespace when doing datastore reads.
        with common_utils.Namespace(namespace):

            # This base query can be modified to add whatever filters you need.
            query = models.Student.all()
            students = common_utils.iter_all(query, self.args.batch_size)

            # Write the results. Done!
            with open(self.args.path, 'w') as f:
                for student in students:
                    f.write(student.email)
                    f.write('\n')
