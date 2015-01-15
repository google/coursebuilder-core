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
    'juliaoh@google.com (Julia Oh)',
]

import csv
import os
import sys
from xml.etree import ElementTree

import mrs

from models import transforms
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


class JsonWriter(mrs.fileformats.Writer):
    """Outputs one JSON literal per line.

    Example JSON output may look like:
    {'foo': 123, 'bar': 456, 'quz': 789}
    {'foo': 321, 'bar': 654, 'quz': 987}
    .
    .
    .
    {'foo': 456, 'bar': 534, 'quz': 154}

    """

    ext = 'json'

    def __init__(self, fileobj, *args, **kwds):
        super(JsonWriter, self).__init__(fileobj, *args, **kwds)

    def _write_json(self, write_fn, python_object):
        """Writes serialized JSON representation of python_object to file.

        Args:
            write_fn: Python file object write() method.
            python_object: object. Contents to write. Must be JSON-serializable.

        Raises:
            TypeError: if python_object is not a dict or a list.
        """
        if isinstance(python_object, dict):
            write_fn(unicode(
                transforms.dumps(python_object) + '\n').encode('utf-8'))
        elif isinstance(python_object, list):
            for item in python_object:
                self._write_json(write_fn, item)
        else:
            raise TypeError('Value must be a dict or a list of dicts.')

    def writepair(self, kvpair, **unused_kwds):
        unused_key, value = kvpair
        self._write_json(self.fileobj.write, value)


class TextWriter(mrs.fileformats.TextWriter):
    """A simplified plain text writer."""

    ext = 'txt'  # Use the expected extension rather than mrs' mtxt default.

    def writepair(self, pair, **unused_kwargs):
        _, value = pair
        # Write the value exactly rather than always prefixing it with the key.
        self.fileobj.write(unicode(value).encode('utf-8') + os.linesep)


class MapReduceBase(mrs.MapReduce):
    """Common functionalities of MR jobs combined into one class."""

    # Subclass of mrs.fileformats.Writer. The writer used to format output.
    WRITER_CLASS = JsonWriter

    def json_parse(self, value):
        """Parses JSON file into Python."""
        if value.strip()[-1] == ',':
            value = value.strip()[:-1]
        try:
            return transforms.loads(value)
        # Skip unparseable rows like the first and last
        # pylint: disable=bare-except
        except:
            return None

    def make_reduce_data(self, job, interm_data):
        """Change the outout format to JSON."""
        outdir = self.output_dir()
        output_data = job.reduce_data(
            interm_data, self.reduce, outdir=outdir, format=self.WRITER_CLASS)
        return output_data


class Histogram(object):
    """Histogram that bins values into _bucket_size sized intervals."""

    # Int. Number of consecutive zeros in list of integer values to determine
    # the cutoff point.
    _NUM_ZEROS = 3

    def __init__(self, bucket_size):
        # Map of 0-indexed bin #int -> count int
        self._values = {}
        self._bucket_size = bucket_size

    def add(self, value):
        """Adds value into self._values."""
        bin_number = self._get_bin_number(value)
        self._increment_bin(bin_number)

    def _get_bin_number(self, value):
        """Returns appropriate bin number for given value."""
        if value < 0:
            raise ValueError('Cannot calculate index for negative value')
        return max(0, (value - 1) // self._bucket_size)

    def _increment_bin(self, n):
        self._values[n] = self._values.get(n, 0) + 1

    def to_list(self):
        """Returns self._values converted into a list, sorted by its keys."""
        try:
            max_key = max(self._values.iterkeys())
            return [self._values.get(n, 0) for n in xrange(0, max_key+1)]
        except ValueError:
            return []

    def to_noise_filtered_list(self):
        """Converts self._values to a list with junk data removed.

        Returns:
            self.to_list(), with junk data removed

        "Junk data" refers to noise in EventEntity data caused by API
        misbehaviors and certain user behavior. Two known issues are:
        1. Youtube video data from event source 'tag-youtube-video' and
           'tag-youtube-milestone' represent user engagement at certain playhead
           positions. Youtube API continues to emit these values even when the
           video has stopped playing, causing a trail of meaningless values in
           the histogram.
        2. Data from event source 'visit-page' logs duration of a page visit.
           If a user keeps the browser open and goes idle, the duration value
           recorded is skewed since the user wasn't engaged. These values tend
           to be significantly larger than more reliable duration values.

        This method filters the long trail of insignificant data by counting
        number of consecutive zeros set in self._NUM_ZEROS and disregarding
        any data after the zeros.

        Example:
            self.to_list() returns [1, 2, 3, 4, 5, 0, 0, 0, 0, 1]
            _NUM_ZEROS = 3

            output = [1, 2, 3, 4, 5]
        """
        zero_counts = 0
        cutoff_index = 0
        values = self.to_list()
        for index, value in enumerate(values):
            if value == 0:
                zero_counts += 1
                if zero_counts == 1:
                    cutoff_index = index
                if zero_counts == self._NUM_ZEROS:
                    return values[:cutoff_index]
            else:
                cutoff_index = 0
                zero_counts = 0
        return values


class XmlWriter(mrs.fileformats.Writer):
    """Writes file in XML format.

    The writer does not use the key from kvpair and expects the value to be a
    list of string representation of XML elements.

    Example:
        kvpair: some_key, ['<row><name>Jane</name></row>',
                           '<row><name>John</name></row>']

        Output:
            <rows>
                <row>
                    <name>Jane</name>
                </row>
                <row>
                    <name>John</name>
                </row>
            </rows>
    """

    ext = 'xml'

    def __init__(self, fileobj, *args, **kwds):
        super(XmlWriter, self).__init__(fileobj, *args, **kwds)
        self.fileobj.write('<rows>')

    def writepair(self, kvpair, **unused_kwds):
        unused_key, values = kvpair
        write = self.fileobj.write
        for value in values:
            write(value)
            write('\n')

    def finish(self):
        self.fileobj.write('</rows>')
        self.fileobj.flush()


class XmlGenerator(MapReduceBase):
    """Generates a XML file from a JSON formatted input file."""

    WRITER_CLASS = XmlWriter

    def map(self, key, value):
        """Converts JSON object to xml.

        Args:
            key: int. line number of the value in Entity file.
            value: str. A line of JSON literal extracted from Entity file.

        Yields:
            A tuple with the string 'key' and a tuple containing line number and
            string representaiton of the XML element.
        """
        json = self.json_parse(value)
        if json:
            root = ElementTree.Element('row')
            transforms.convert_dict_to_xml(root, json)
            yield 'key', (key, ElementTree.tostring(root, encoding='utf-8'))

    def reduce(self, unused_key, values):
        """Sorts the values by line number to keep the order of the document.

        Args:
            unused_key: str. The arbitrary string 'key' set to accumulate all
                values under one key.
            values: list of tuples. Each tuple contains line number and JSON
                literal converted to XML string.

        Yields:
            A list of XML strings sorted by the line number.
        """

        sorted_values = sorted(values, key=lambda x: x[0])
        yield [value[1] for value in sorted_values]


class JsonToXml(MapReduceJob):
    """MapReduce Job that converts JSON formatted Entity files to XML.

    Usage: run the following command from the app root folder.

    python tools/etl/etl.py run tools.etl.mapreduce.JsonToXml \
        /coursename appid server.appspot.com \
        --job_args='path_to_any_Entity_file path_to_output_directory'
    """

    MAPREDUCE_CLASS = XmlGenerator


class CsvWriter(mrs.fileformats.Writer):
    """Writes file in CSV format.

    The default value to be written if the dictionary is missing a key is an
    empty string.

    Example:
        kvpair: (some_key, (['bar', 'foo', 'quz'],
                            [{'foo': 1, 'bar': 2, 'quz': 3},
                            {'bar': 2, 'foo': 3}])

        Output:
            'bar', 'foo', 'quz'
            2, 1, 3
            2, 3, ''
    """

    ext = 'csv'

    def __init__(self, fileobj, *args, **kwds):
        super(CsvWriter, self).__init__(fileobj, *args, **kwds)

    def writepair(self, kvpair, **unused_kwds):
        """Writes list of JSON objects to CSV format.

        Args:
            kvpair: tuple of unused_key, and a tuple of master_list and
                json_list. Master_list is a list that contains all the
                fieldnames across json_list sorted in alphabetical order, and
                json_list is a list of JSON objects.
            **unused_kwds: keyword args that won't be used.
        """
        unused_key, (master_list, json_list) = kvpair
        writer = csv.DictWriter(
            self.fileobj, fieldnames=master_list, restval='')
        writer.writeheader()
        writer.writerows(json_list)


class CsvGenerator(MapReduceBase):
    """Generates a CSV file from a JSON formatted input file."""

    WRITER_CLASS = CsvWriter

    @classmethod
    def _flatten_json(cls, _dict, prefix=''):
        """Flattens dict and contained JSON; encodes all values in utf-8."""
        for key in _dict.keys():
            value = _dict.pop(key)

            _nested = None
            if type(value) == dict:
                _nested = value
            else:
                try:
                    _dict_from_value = transforms.loads(value, strict=False)
                    if _dict_from_value and type(_dict_from_value) == dict:
                        _nested = _dict_from_value
                except:  # pylint: disable=bare-except
                    pass

            if _nested:
                flattened = cls._flatten_json(
                    _nested, prefix=prefix + key + '_')
                _dict.update(flattened)
            else:
                _dict[prefix + key] = unicode(value).encode('utf-8')
        return _dict

    def map(self, unused_key, value):
        """Loads JSON object and flattens it.

        Example:
            json['data']['foo'] = 'bar' -> json['data_foo'] = 'bar', with
            json['data'] removed.

        Args:
            unused_key: int. line number of the value in Entity file.
            value: str. instance of Entity file extracted from file.

        Yields:
            A tuple of string key and flattened dictionary. map() outputs
            constant string 'key' as the key so that all the values can be
            accumulated under one key in reduce(). This accumulation is
            necessary because reduce() must go through the list of all JSON
            literals and determine all existing fieldnames. Then, reduce()
            supplies the master_list of fieldnames to CSVWriter's writepair()
            which uses the list as csv header.
        """
        json = self.json_parse(value)
        if json:
            json = CsvGenerator._flatten_json(json)
            yield 'key', json

    def reduce(self, unused_key, values):
        """Creates a master_list of all the keys present in an Entity file.

        Args:
            unused_key: str. constant string 'key' emitted by map().
            values: a generator over list of json objects.

        Yields:
            A tuple of master_list and list of json objects.
            master_list is a list of all keys present across every json object.
            This list is used to create header for CSV files.
        """
        master_list = []
        values = [value for value in values]
        for value in values:
            for key in value:
                if key not in master_list:
                    master_list.append(key)
        try:
            # Convert integer keys from unicode to ints to be sorted correctly.
            # pylint: disable=unnecessary-lambda
            master_list = sorted(master_list, key=lambda item: int(item))
        except ValueError:
            # String keys cannot be converted into integers..
            master_list = sorted(master_list)
        yield master_list, values


class JsonToCsv(MapReduceJob):
    """MapReduce Job that converts JSON formatted Entity files to CSV format.

    Usage: run the following command from the app root folder.

    python tools/etl/etl.py run tools.etl.mapreduce.JsonToCsv
        /coursename appid server.appspot.com \
        --job_args='path_to_an_Entity_file path_to_output_directory'
    """

    MAPREDUCE_CLASS = CsvGenerator


mrs.fileformats.writer_map['csv'] = CsvWriter
mrs.fileformats.writer_map['json'] = JsonWriter
mrs.fileformats.writer_map['txt'] = TextWriter
mrs.fileformats.writer_map['xml'] = XmlWriter
