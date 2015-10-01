# Copyright 2012 Google Inc. All Rights Reserved.
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

"""Classes for displaying peer review analytics."""

__author__ = 'Sean Lip (sll@google.com)'

from models import analytics
from models import courses
from models import data_sources
from models import jobs
from models import transforms
from modules.dashboard import dashboard
from modules.review import peer


class PeerReviewStatsGenerator(jobs.AbstractCountingMapReduceJob):

    @staticmethod
    def get_description():
        return 'peer review'

    def entity_class(self):
        return peer.ReviewSummary

    @staticmethod
    def map(review_summary):
        key = '%s:%s' % (review_summary.unit_id, review_summary.completed_count)
        yield (key, 1)


class PeerReviewStatsSource(data_sources.SynchronousQuery):

    @staticmethod
    def required_generators():
        return [PeerReviewStatsGenerator]

    @staticmethod
    def fill_values(app_context, template_values, job):
        # What we want to produce as output is a list of review results for
        # each unit, ordered by where the unit appears in the course.
        # For each unit, we produce a dict of {unit_id, title, stats}
        # The unit_id and title are from the unit itself.
        #
        # The 'stats' item is an array.  In the 0th position of the
        # array, we give the number of peer reviews requests that have
        # had 0 completed responses.  In the 1th position, those with
        # 1 response, and so on.
        # The 'stats' array in each unit's dict must be the same length,
        # and thus is right-padded with zeroes as appropriate.

        # First, generate a stats list for each unit.  This will have
        # a ragged right edge.
        counts_by_unit = {}
        max_completed_count = 0
        for unit_and_count, quantity in jobs.MapReduceJob.get_results(job):

            # Burst values
            unit, completed_count = unit_and_count.rsplit(':')
            completed_count = int(completed_count)
            quantity = int(quantity)
            max_completed_count = max(completed_count, max_completed_count)

            # Ensure the array for the unit exists and is long enough.
            unit_stats = counts_by_unit[unit] = counts_by_unit.get(unit, [])
            unit_stats.extend([0] * (completed_count - len(unit_stats) + 1))

            # Install the quantity of reviews with N responses for this unit.
            unit_stats[completed_count] = quantity

        # Fix the ragged right edge by padding all arrays out to a length
        # corresponding to the maximum number of completed responses for
        # any peer-review request.
        for unit_stats in counts_by_unit.values():
            unit_stats.extend([0] * (max_completed_count - len(unit_stats) + 1))

        # Now march through the units, in course order and generate the
        # {unit_id, title, stats} dicts used for display.
        serialized_units = []
        course = courses.Course(None, app_context=app_context)
        for unit in course.get_peer_reviewed_units():
            if unit.unit_id in counts_by_unit:
                serialized_units.append({
                    'stats': counts_by_unit[unit.unit_id],
                    'title': unit.title,
                    'unit_id': unit.unit_id,
                })
        template_values.update({
            'serialized_units': serialized_units,
            'serialized_units_json': transforms.dumps(serialized_units),
        })


def register_analytic():
    data_sources.Registry.register(PeerReviewStatsSource)
    name = 'peer_review'
    title = 'Peer review assignments'
    peer_review = analytics.Visualization(
        name, title, 'stats.html',
        data_source_classes=[PeerReviewStatsSource])
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'analytics', name, title, action=name,
        contents=analytics.TabRenderer([peer_review]),
        placement=2000, sub_group_name=name)
