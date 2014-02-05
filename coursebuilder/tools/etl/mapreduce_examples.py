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

"""Example of custom MapReduce jobs."""

__author__ = [
    'juliaoh@google.com (Julia Oh)',
]

import sys

import mapreduce

from models import transforms

# Int. Longest GeoMOOC video is ~8 minutes.
_POS_LIMIT_SECONDS = 60 * 8
# Str. Constant str key to accumulate all values under one key in reduce.
_SUM = 'sum'


class CsvStudentEventAccumulationPipeline(mapreduce.CsvGenerator):
    """Example MapReduce pipeline class for histogram of event instance counts.

    This MR pipeline:
        1. Takes in EventEntity as input source.
        2. Counts the total number of event instances per user.
        3. Aggregates event counts across all users.
        4. Creates a histogram from aggregated event counts.
        5. Flattens the histogram.
        6. Format the histogram into CSV.
    """
    # List of sources of Youtube video data in EventEntity.
    _VIDEO_SOURCES = [
        'tag-youtube-milestone',
        'tag-youtube-event'
    ]

    def run(self, job):
        """Runs the mapreduce pipeline job."""
        # Validate input source and output directory. mrs. MapReduce framework
        # expects the value 1 if the job fails. If the input source is empty or
        # the output directory cannot be found, the job is a failure and must
        # return 1.
        source = self.input_data(job)
        if not source:
            return 1
        outdir = self.output_dir()
        if not outdir:
            return 1

        # Set the configuration for pipeline.

        # First MapReduce phase: filter out event data and aggregate by user
        # key.
        user_to_event_instance_count = job.map_data(
            source, self.map_userid_to_1)
        source.close()
        total_event_counts_per_user = job.reduce_data(
            user_to_event_instance_count, self.sum_event_instances_per_user)
        user_to_event_instance_count.close()

        # Second MapReduce phase: Create a histogram with aggregated data.
        aggregated_event_counts = job.map_data(
            total_event_counts_per_user,
            self.map_all_event_counts_to_single_key
        )
        total_event_counts_per_user.close()
        histogram = job.reduce_data(
            aggregated_event_counts,
            self.create_histogram_from_aggregated_event_counts
        )
        aggregated_event_counts.close()

        # Third MapReduce phase: Flatten the data and format it to CSV. This
        # phase calls the map() and reduce() functions defined in CsvGenerator
        # class.
        flattened_histogram = job.map_data(histogram, self.map)
        histogram.close()
        histogram_csv = job.reduce_data(
            flattened_histogram, self.reduce, format=mapreduce.CsvWriter,
            outdir=outdir)
        flattened_histogram.close()
        histogram_csv.close()

        # Run the job with above configurations. job.wait() does not return any
        # value until the entire job is done. Partial progress of each phases
        # will be printed while the job is running.
        ready = []
        while not ready:
            ready = job.wait(histogram_csv, timeout=2.0)
            first_map_percent = 100 * job.progress(user_to_event_instance_count)
            first_reduce_percent = 100 * job.progress(
                total_event_counts_per_user)
            second_map_percent = 100 * job.progress(aggregated_event_counts)
            second_reduce_percent = 100 * job.progress(histogram)
            third_map_percent = 100 * job.progress(flattened_histogram)
            third_reduce_percent = 100 * job.progress(histogram_csv)
            string_map = {
                'map1_name': self.map_userid_to_1.__name__,
                'map1_progress': first_map_percent,
                'reduce1_name': self.sum_event_instances_per_user.__name__,
                'reduce1_progress': first_reduce_percent,
                'map2_name': self.map_all_event_counts_to_single_key.__name__,
                'map2_progress': second_map_percent,
                'reduce2_name': (
                    self.create_histogram_from_aggregated_event_counts.__name__
                ),
                'reduce2_progress': second_reduce_percent,
                'map3_name': self.map.__name__,
                'map3_progress': third_map_percent,
                'reduce3_name': self.reduce.__name__,
                'reduce3_progress': third_reduce_percent
            }
            print (
                '%(map1_name)s: %(map1_progress).1f complete. \n'
                '%(reduce1_name)s: %(reduce1_progress).1f complete. \n'
                '%(map2_name)s: %(map2_progress).1f complete. \n'
                '%(reduce2_name)s: %(reduce2_progress).1f complete. \n'
                'csv_%(map3_name)s: %(map3_progress).1f complete. \n'
                'csv_%(reduce3_name)s: %(reduce3_progress).1f complete. \n' %
                string_map
            )
            sys.stdout.flush()
        return 0

    def map_userid_to_1(self, unused_key, value):
        """Maps user_id to value of 1.

        Args:
            unused_key: int. Line number of EventEntity JSON object in file.
            value: str. Instance of EventEntity extracted from file.

        Yields:
            A tuple of (user_id, 1).
            Value of 1 represents one instance of event for the user.
        """
        json = self.json_parse(value)
        if json and json['user_id']:
            if json['source'] in self._VIDEO_SOURCES:
                video_data = transforms.loads(json['data'])
                if video_data['position'] > _POS_LIMIT_SECONDS:
                    # Filter bad data from YouTube API.
                    return
            yield json['user_id'], 1

    def sum_event_instances_per_user(self, unused_key, values):
        """Sums up number of entity instances per student.

        Args:
            unused_key: str. Represents user_id.
            values: An iterator over entity instance counts per student.

        Yields:
            A dict with key value pair as:
                key: constant string literal 'sum'
                value: int. Total number of entity instances.
        """
        yield {_SUM: sum(values)}

    def map_all_event_counts_to_single_key(self, unused_key, value):
        yield _SUM, value[_SUM]

    def create_histogram_from_aggregated_event_counts(self, unused_key, values):
        """Creates a histogram from event entity instance counts.

        Args:
            unused_key: str. Constant string 'key' emitted by mapper2.
            values: An iterator over list of integer event instance counts.

        Yields:
            A serialized JSON representation of python dictionary. The keys of
            the python dict are indices of the histogram interval, and the
            corresponding values are number of events that are in that interval.

        An example output looks like: {0: 10, 1: 15, 2: 100}
        """
        # Histogram bucket size is 50 events.
        histogram = mapreduce.Histogram(50)
        for value in values:
            histogram.add(value)
        yield transforms.dumps(
            {index: value for index, value in enumerate(
                histogram.to_noise_filtered_list())})


class CsvStudentEventsHistogram(mapreduce.MapReduceJob):
    """MapReduce Job that generates a histogram for event counts per student.

    Usage:
    python etl.py run tools.etl.mapreduce_examples.StudentEventsHistogram \
        /coursename appid server.appspot.com \
        --job_args='path_to_EventEntity.json path_to_output_directory'
    """

    MAPREDUCE_CLASS = CsvStudentEventAccumulationPipeline


class StudentDurationAccumulationPipeline(mapreduce.MapReduceBase):
    """Sums up amount of time spent on course per student.

        This pipeline:
            1. Takes an EventEntity file as input.
            2. Sum up all valid page-visit duration values per user.
            3. Aggregate summed up duration values across all users.
            4. Create a histogram with these values.
    """

    # Str. Source of event in EventEntity generated during a page visit.
    _VISIT_PAGE = 'visit-page'
    # Int. A hard limit for duration value on visit-page events to filter
    # misleading data. If a user keeps the browser open and goes idle, duration
    # values can get very large.
    _DURATION_MINUTES_LIMIT = 30

    def run(self, job):
        """Runs the mapreduce pipeline job."""
        # Validate input source and output directory.
        source = self.input_data(job)
        if not source:
            return 1
        outdir = self.output_dir()
        if not outdir:
            return 1

        # Set the configuration for pipeline.

        # First MapReduce phase: filter out page-visit duration values and
        # accumulate under user key.
        user_to_duration = job.map_data(source, self.map_user_to_duration)
        source.close()
        user_to_total_duration = job.reduce_data(
            user_to_duration, self.sum_total_duration_per_user)
        user_to_duration.close()

        # Second MapReduce phase: Create a histogram with aggregated duration
        # values from all users.
        aggregated_duration_values = job.map_data(
            user_to_total_duration,
            self.map_all_user_duration_total_to_single_key
        )
        user_to_total_duration.close()
        histogram = job.reduce_data(
            aggregated_duration_values,
            self.create_histogram_from_duration_distribution,
            outdir=outdir,
            format=mapreduce.JsonWriter
        )
        aggregated_duration_values.close()
        histogram.close()

        # Run the job with above configurations.
        ready = []
        while not ready:
            ready = job.wait(histogram, timeout=2.0)
            first_map_percent = 100 * job.progress(user_to_duration)
            first_reduce_percent = 100 * job.progress(user_to_total_duration)
            second_map_percent = 100 * job.progress(aggregated_duration_values)
            second_reduce_percent = 100 * job.progress(histogram)
            string_map = {
                'map1_name': self.map_user_to_duration.__name__,
                'map1_progress': first_map_percent,
                'reduce1_name': self.sum_total_duration_per_user.__name__,
                'reduce1_progress': first_reduce_percent,
                'map2_name': (
                    self.map_all_user_duration_total_to_single_key.__name__
                ),
                'map2_progress': second_map_percent,
                'reduce2_name': (
                    self.create_histogram_from_duration_distribution.__name__
                ),
                'reduce2_progress': second_reduce_percent
            }
            print (
                '%(map1_name)s: %(map1_progress).1f complete. \n'
                '%(reduce1_name)s: %(reduce1_progress).1f complete. \n'
                '%(map2_name)s: %(map2_progress).1f complete. \n'
                '%(reduce2_name)s: %(reduce2_progress).1f complete. \n' %
                string_map
            )
            sys.stdout.flush()
        return 0

    def map_user_to_duration(self, unused_key, value):
        """Maps user_id to duration value in 'visit-page' events.

        Args:
            unused_key: int. Line number of EventEntity JSON object in file.
            value: str. Instance of EventEntity extracted from file.

        Yields:
            A tuple of (user_id, valid duration value in minutes).
            Valid duration value is defined as positive integer duration values
            that are less than _DURATION_MINUTES_LIMIT. Duration values are
            validated to filter noisy data.
        """
        json = self.json_parse(value)
        if json and json['user_id'] and json['source'] == self._VISIT_PAGE:
            event_data = transforms.loads(json['data'])
            # Convert duration in milliseconds to minutes.
            duration_minutes = event_data['duration'] // (1000 * 60)
            if (duration_minutes <= self._DURATION_MINUTES_LIMIT and
                duration_minutes > 0):
                yield json.pop('user_id'), duration_minutes

    def sum_total_duration_per_user(self, unused_key, values):
        """Sums up number of entity instances per student.

        Args:
            unused_key: str. Represents user_id.
            values: An iterator over entity instance counts per student.

        Yields:
            A dict with key value pair as:
                key: constant string literal 'sum'
                value: int. Total number of entity instances.
        """
        yield {_SUM: sum(values)}

    def map_all_user_duration_total_to_single_key(self, unused_key, value):
        yield _SUM, value[_SUM]

    def create_histogram_from_duration_distribution(self, unused_key, values):
        """Creates a histogram from summed up duration values.

        Args:
            unused_key: str. Constant string 'sum' emitted by
                map_all_user_duration_total_to_single_key().
            values: An iterator over list of summed up duration values.

        Yields:
            A serialized JSON representation of python dictionary. The keys of
            the python dict are indices of the histogram interval, and the
            corresponding values are number of summed up duration values that
            are in that interval index.

        An example output looks like:
            duration_values = [50, 65, 100, 130]
            histogram bucket_size = 60

            output: "{0: 1, 1: 2, 2: 1}"
        """
        # Histogram bucket size is one hour.
        histogram = mapreduce.Histogram(60)
        for value in values:
            histogram.add(value)
        yield {index: value for index, value in enumerate(
            histogram.to_noise_filtered_list())}


class StudentPageDurationHistogram(mapreduce.MapReduceJob):
    """MapReduce Job that generates a histogram for time spent on course pages.

    Usage:
    python etl.py run \
        tools.etl.mapreduce_examples.StudentPageDurationHistogram \
        /coursename appid server.appspot.com \
        --job_args='path_to_EventEntity.json path_to_output_directory'
    """

    MAPREDUCE_CLASS = StudentDurationAccumulationPipeline


class WordCount(mapreduce.MapReduceBase):
    """Counts word frequency in input.

    Output is plain text of the format:

    word1: count1
    word2: count2
    ...
    wordn: countn
    """

    # Since JSON is our usual interchange format, mapreduce.JsonWriter is our
    # default output writer. For this canonical example, however, we'll override
    # this and emit plain text instead.
    WRITER_CLASS = mapreduce.TextWriter

    def map(self, unused_key, value):
        # value is one line of the input file. We break it into tokens and
        # convert each token to lowercase in order to treat 'To' and 'to' as
        # equivalent.
        tokens = [x.lower() for x in value.split()]
        for token in tokens:
            # Both map and reduce yield rather than return. map yields a
            # (key, value) 2-tuple. In this case, key is the token and value is
            # always 1, indicating that we've seen the token once per
            # occurrence.
            yield token, 1

    def reduce(self, key, values):
        # key will be a token and values will be a list of 1s -- one for each
        # time map saw the token. Like map, reduce yields rather than returning.
        # In this case we yield a plain string containing the token and the sum
        # of its 1s for the WRITER_CLASS to output.
        yield '%s: %s' % (key, sum(values))


class WordCountJob(mapreduce.MapReduceJob):
    """MapReduce Job that illustrates simple word count of input.

    Usage:
    python etl.py run \
        tools.etl.mapreduce_examples.WordCount \
        /coursename appid server.appspot.com \
        --job_args='path/to/input.file path/to/output/directory'
    """

    MAPREDUCE_CLASS = WordCount


class YoutubeHistogramGenerator(mapreduce.MapReduceBase):
    """Generates time histogram of user video engagement.

    Input file: EventEntity JSON file.
    Each event has a 'source' that defines a place in a code where the event
    was recorded. Each event has a 'user_id' to represent an actor who
    triggered the event. The event 'data' is a JSON object and its format and
    content depends on the type of the event. For YouTube video events, 'data'
    is a dictionary with 'video_id', 'instance_id', 'event_id', 'position',
    'data', 'location'.
    """

    # String. Event source value for YouTube videos in EventEntity.json.
    _YOUTUBE_MILESTONE_SOURCE = 'tag-youtube-milestone'

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
        if json and json['source'] == self._YOUTUBE_MILESTONE_SOURCE:
            data = transforms.loads(json['data'])
            video_identifier = (data['video_id'], data['instance_id'])
            playhead_position = data['position']
            if (playhead_position <= _POS_LIMIT_SECONDS and
                # Youtube API may return NaN if value couldn't be computed.
                playhead_position != float('nan')):
                yield video_identifier, playhead_position

    def reduce(self, key, values):
        """Creates a histogram from time_position values.

        The value of _BUCKET_SIZE comes from the constant
        GCB_VIDEO_TRACKING_CHUNK_SEC in youtube_video.js. This value indicates
        the interval of the milestone events. If GCB_VIDEO_TRACKING_CHUNK_SEC
        changes, _BUCKET_SIZE will have to be updated accordingly.

        Args:
            key: tuple. video_id, video instance id.
            values: An iterator over integer video playhead positions.

        Yields:
            A dictionary with video_id, instance_id, and histogram.
            The time histogram is a list in which each index represents
            sequential milestone events and the corresponding item at each
            index represents the number of users watching the video.

        An example output looks like:
        {'video_id': 123456, 'instance_id': 0, 'histogram': [10, 8, 7, 5, 2, 1]}
        """
        # Bucket size is 30 seconds, the value of GCB_VIDEO_TRACKING_CHUNK_SEC
        # in youtube_video.js.
        histogram = mapreduce.Histogram(30)
        for value in values:
            histogram.add(value)
        yield {
            'video_id': key[0],
            'instance_id': key[1],
            'histogram': histogram.to_list()
        }


class YoutubeHistogram(mapreduce.MapReduceJob):
    """MapReduce job that generates a histogram for user video engagement.

    Usage: run the following command from the app root folder.

    python tools/etl/etl.py run tools.etl.mapreduce_examples.YoutubeHistogram \
        /coursename appid server.appspot.com \
        --job_args='path_to_EventEntity.json path_to_output_directory'
    """

    MAPREDUCE_CLASS = YoutubeHistogramGenerator
