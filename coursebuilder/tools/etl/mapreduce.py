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

    def writepair(self, kvpair, **unused_kwds):
        unused_key, value = kvpair
        write = self.fileobj.write
        write(unicode(value).encode('utf-8'))
        write('\n')


class EventFlattener(MapReduceBase):
    """Flattens JSON event data.

    Input file: EventEntity JSON file.
    Each event has a 'source' that defines a place in a code where the event was
    recorded. Each event has a 'user_id' to represent an actor who triggered
    the event. The event 'data' is a JSON object.
    """

    def _flatten_data(self, json):
        # json['data']['foo'] = 'bar' -> json['data_foo'] = 'bar', with
        # json['data'] removed.
        for k, v in transforms.loads(json.pop('data')).iteritems():
            json['data_' + k] = v
        return json

    def map(self, key, value):
        """Maps key string, value string -> key string, flattened_json_dict."""
        json = self.json_parse(value)
        if json:
            if json.get('data'):
                json = self._flatten_data(json)
            yield key, json

    def reduce(self, unused_key, values):
        yield [value for value in values][0]


class FlattenEvents(MapReduceJob):
    """MapReduce Job that flattens EventEntities.

    Usage:
    python etl.py run path.to.mapreduce.FlattenEvents /coursename \
        appid server.appspot.com \
        --job_args='path_to_EventEntity.json path_to_output_directory'
    """

    MAPREDUCE_CLASS = EventFlattener


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
            A string representation of JSON dictionary with video_id,
            instance_id, and histogram.
            The time histogram is a list in which each index represents
            sequential milestone events and the corresponding item at each
            index represents the number of users watching the video.

        An example output looks like:
        {'video_id': 123456, 'instance_id': 0, 'histogram': [10, 8, 7, 5, 2, 1]}
        """
        histogram = Histogram()
        for value in values:
            histogram.add(value)
        yield transforms.dumps({'video_id': key[0], 'instance_id': key[1],
                                'histogram': histogram.to_list()})


class YoutubeHistogram(MapReduceJob):
    """MapReduce Job that generates a histogram for user video engagement.

    Usage:
    python etl.py run path.to.mapreduce.VideoHistogram /coursename \
        appid server.appspot.com \
        --job_args='path_to_EventEntity.json path_to_output_directory'
    """

    MAPREDUCE_CLASS = YoutubeHistogramGenerator


mrs.fileformats.writer_map['json'] = JsonWriter
