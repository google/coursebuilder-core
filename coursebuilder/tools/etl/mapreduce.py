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

import os
import sys

from xml.etree import ElementTree
from models import transforms

import mrs

from tools.etl import etl_lib


# String. Event source value for YouTube videos in EventEntity.json.
_YOUTUBE_MILESTONE_SOURCE = 'tag-youtube-milestone'
# Int. Value of GCB_VIDEO_TRACKING_CHUNK_SEC in youtube_video.js.
_BUCKET_SIZE_SECONDS = 30
# Int. 3hrs limit on the playhead_position.
_POS_LIMIT = 60 * 60 * 3


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


class MapReduceBase(mrs.MapReduce):
    """Common functionalities of MR jobs combined into one class."""

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
            interm_data, self.reduce, outdir=outdir, format=JsonWriter)
        return output_data


class JsonWriter(mrs.fileformats.Writer):
    """Outputs one JSON literal per line.

    writepair() expects kvpair to be a tuple of unused key and either a list of
    dicts, or a single dict.

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

    def _write_json(self, writer, python_object):
        if isinstance(python_object, dict):
            writer(unicode(
                transforms.dumps(python_object) + '\n').encode('utf-8'))
        elif isinstance(python_object, list):
            for item in python_object:
                self._write_json(writer, item)
        else:
            raise TypeError('Value must be a dict or a list of dicts.')

    def writepair(self, kvpair, **unused_kwds):
        unused_key, value = kvpair
        self._write_json(self.fileobj.write, value)


class Histogram(object):
    """Histogram that bins values into _BUCKET_SIZE_SECONDS sized intervals."""

    def __init__(self):
        # Map of 0-indexed bin #int -> count int
        self._values = {}

    def add(self, value):
        """Adds value into self._values and updates self._max_key."""
        bin_number = self._get_bin_number(value)
        self._increment_bin(bin_number)

    def _get_bin_number(self, value):
        """Returns appropriate bin number for given value."""
        if value < 0:
            raise ValueError('Cannot calculate index for negative value')
        return max(0, (value - 1) // _BUCKET_SIZE_SECONDS)

    def _increment_bin(self, n):
        self._values[n] = self._values.get(n, 0) + 1

    def to_list(self):
        """Returns self._values converted into a list, sorted by its keys."""
        try:
            max_key = max(self._values.iterkeys())
            return [self._values.get(n, 0) for n in xrange(max_key+1)]
        except ValueError:
            return []


class YoutubeHistogramGenerator(MapReduceBase):
    """Generates time histogram of user video engagement.

    Input file: EventEntity JSON file.
    Each event has a 'source' that defines a place in a code where the event
    was recorded. Each event has a 'user_id' to represent an actor who
    triggered the event. The event 'data' is a JSON object and its format and
    content depends on the type of the event. For YouTube video events, 'data'
    is a dictionary with 'video_id', 'instance_id', 'event_id', 'position',
    'data', 'location'.
    """

    def map(self, unused_key, value):
        """Filters out YouTube video data from EventEntity JSON file.

        Args:
            unused_key: int. line number of each EventEntity in file.
            value: str. instance of EventEntity extracted from file.

        Yields:
            A tuple of (video_identifier, time_position) to be passed into
            reduce function.
            Video_identifier is a tuple of YouTube video_id and instance_id,
            and time_position is the video playhead count.
        """
        json = self.json_parse(value)
        if json and json['source'] == _YOUTUBE_MILESTONE_SOURCE:
            data = transforms.loads(json['data'])
            video_identifier = (data['video_id'], data['instance_id'])
            playhead_position = data['position']
            if (playhead_position <= _POS_LIMIT and
                # Youtube API may return NaN if value couldn't be computed.
                playhead_position != float('nan')):
                yield video_identifier, playhead_position

    def reduce(self, key, values):
        """Creates a histogram from time_position values.

        The value of _BUCKET_SIZE_SECONDS comes from the constant
        GCB_VIDEO_TRACKING_CHUNK_SEC in youtube_video.js. This value indicates
        the interval of the milestone events. If GCB_VIDEO_TRACKING_CHUNK_SEC
        changes, _BUCKET_SIZE_SECONDS will have to be updated accordingly.

        Args:
            key: tuple. video_id, video instance id.
            values: a generator over video playhead positions.

        Yields:
            A dictionary with video_id, instance_id, and histogram.
            The time histogram is a list in which each index represents
            sequential milestone events and the corresponding item at each
            index represents the number of users watching the video.

        An example output looks like:
        {'video_id': 123456, 'instance_id': 0, 'histogram': [10, 8, 7, 5, 2, 1]}
        """
        histogram = Histogram()
        for value in values:
            histogram.add(value)
        yield {
            'video_id': key[0],
            'instance_id': key[1],
            'histogram': histogram.to_list()
        }


class YoutubeHistogram(MapReduceJob):
    """MapReduce Job that generates a histogram for user video engagement.

    Usage:
    python etl.py run path.to.mapreduce.VideoHistogram /coursename \
        appid server.appspot.com \
        --job_args='path_to_EventEntity.json path_to_output_directory'
    """

    MAPREDUCE_CLASS = YoutubeHistogramGenerator


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

    def make_reduce_data(self, job, interm_data):
        """Change the outout format to XML."""
        outdir = self.output_dir()
        output_data = job.reduce_data(
            interm_data, self.reduce, outdir=outdir, format=XmlWriter)
        return output_data


class JsonToXml(MapReduceJob):
    """MapReduce Job that converts JSON formatted Entity files to XML.

    Usage:
    python etl.py run path.to.mapreduce.JsonToXml /coursename \
        appid server.appspot.com \
        --job_args='path_to_any_Entity_file path_to_output_directory'
    """

    MAPREDUCE_CLASS = XmlGenerator


mrs.fileformats.writer_map['json'] = JsonWriter
mrs.fileformats.writer_map['xml'] = XmlWriter
