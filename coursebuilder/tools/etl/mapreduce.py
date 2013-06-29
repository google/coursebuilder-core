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

"""MapReduce extensions for ETL."""

__author__ = [
    'johncox@google.com (John Cox)',
]

import os
import sys

from models import transforms

import mrs

from tools.etl import etl_lib


class MapReduceJob(etl_lib.Job):
    """Parent classes for custom jobs that run a mapreduce.

    Usage:
        python etl.py run path.to.my.job / appid server.appspot.com \
            --disable_remote \
            --job_args='path_to_input_file path_to_output_directory'
    """

    # Subclass of mrs.MapReduce; override in child.
    MAPREDUCE_CLASS = None

    def _configure_parser(self):
        """Shim that works with the arg parser expected by mrs.Mapreduce."""
        self.parser.add_argument(
            'file', help='Absolute path of the input file', type=str)
        self.parser.add_argument(
            'output', help='Absolute path of the output directory', type=str)

    def main(self):
        if not os.path.exists(self.args.file):
            sys.exit('Input file %s not found' % self.args.file)
        if not os.path.exists(self.args.output):
            sys.exit('Output directory %s not found' % self.args.output)

        mrs.main(self.MAPREDUCE_CLASS, args=self._parsed_etl_args.job_args)


class EventFlattener(mrs.MapReduce):
    """Flattens JSON event data."""

    def _flatten_data(self, json):
        # json['data']['foo'] = 'bar' -> json['data_foo'] = 'bar', with
        # json['data'] removed.
        for k, v in transforms.loads(json.pop('data')).iteritems():
            json['data_' + k] = v
        return json

    def map(self, key, value):
        """Maps key string, value string -> key string, flattened_json_dict."""
        json = None
        value = value.strip()[:-1]

        try:
            json = transforms.loads(value)
        # Skip unparseable rows like the first and last.
        # pylint: disable-msg=broad-except
        except Exception:
            pass

        if json:
            if json.get('data'):
                json = self._flatten_data(json)
            yield key, json

    def reduce(self, unused_key, values):
        yield [value for value in values][0]


class FlattenEvents(MapReduceJob):
    """MapReduce Job that flattens EventEntities."""

    MAPREDUCE_CLASS = EventFlattener
