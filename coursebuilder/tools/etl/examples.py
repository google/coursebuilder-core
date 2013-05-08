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

"""Examples of custom extract-transform-load jobs."""

__author__ = [
    'johncox@google.com',
]

import os
import sys
from models import models
from tools.etl import etl_lib
from google.appengine.api import namespace_manager


class WriteStudentEmailsToFile(etl_lib.Job):
    """Example job that extracts student emails into a file on disk.

    Usage:

    etl.py run tools.etl.examples.WriteStudentEmailsToFile /course myapp \
        server.appspot.com --job_args=/path/to/output_file
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

        # Because courses are namespaced, we need to change to the requested
        # course's namespace before doing datastore reads or we won't find its
        # data. Get the current namespace so we can change back when we're done.
        old_namespace = namespace_manager.get_namespace()
        try:
            namespace_manager.set_namespace(namespace)
            # For this example, we'll only process the first 1000 results. Can
            # do a keys_only query because the student's email is key.name().
            keys = models.Student.all(keys_only=True).fetch(1000)
        finally:
            # The current namespace is global state. We must change it back to
            # the old value no matter what to prevent corrupting datastore
            # operations that run after us.
            namespace_manager.set_namespace(old_namespace)

        # Write the results. Done!
        with open(self.args.path, 'w') as f:
            for key in keys:
                f.write(str(key.name() + '\n'))
