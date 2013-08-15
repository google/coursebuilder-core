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


import os

from common import safe_dom
from controllers.utils import ApplicationHandler
from controllers.utils import HUMAN_READABLE_TIME_FORMAT
import jinja2
from models import courses
from models import jobs
from models import transforms
from models import utils
from modules.review import peer


class ReviewStatsAggregator(object):
    """Aggregates peer review statistics."""

    def __init__(self):
        # This dict records, for each unit, how many submissions have a given
        # number of completed reviews. The format of each key-value pair is
        #     unit_id: {num_reviews: count_of_submissions}
        self.counts_by_completed_reviews = {}

    def visit(self, review_summary):
        unit_id = review_summary.unit_id
        if unit_id not in self.counts_by_completed_reviews:
            self.counts_by_completed_reviews[unit_id] = {}

        count = review_summary.completed_count
        if count not in self.counts_by_completed_reviews[unit_id]:
            self.counts_by_completed_reviews[unit_id][count] = 1
        else:
            self.counts_by_completed_reviews[unit_id][count] += 1


class ComputeReviewStats(jobs.DurableJob):
    """A job for computing peer review statistics."""

    def run(self):
        """Computes peer review statistics."""

        stats = ReviewStatsAggregator()
        mapper = utils.QueryMapper(
            peer.ReviewSummary.all(), batch_size=500, report_every=1000)

        mapper.run(stats.visit)

        completed_arrays_by_unit = {}
        for unit_id in stats.counts_by_completed_reviews:
            max_completed_reviews = max(
                stats.counts_by_completed_reviews[unit_id].keys())

            completed_reviews_array = []
            for i in range(max_completed_reviews + 1):
                if i in stats.counts_by_completed_reviews[unit_id]:
                    completed_reviews_array.append(
                        stats.counts_by_completed_reviews[unit_id][i])
                else:
                    completed_reviews_array.append(0)
            completed_arrays_by_unit[unit_id] = completed_reviews_array

        return {'counts_by_completed_reviews': completed_arrays_by_unit}


class PeerReviewStatsHandler(ApplicationHandler):
    """Shows peer review analytics on the dashboard."""

    # The key used in the statistics dict that generates the dashboard page.
    # Must be unique.
    name = 'peer_review_stats'
    # The class that generates the data to be displayed.
    stats_computer = ComputeReviewStats

    def get_markup(self, job):
        """Returns Jinja markup for peer review statistics."""

        errors = []
        stats_calculated = False
        update_message = safe_dom.Text('')

        course = courses.Course(self)
        serialized_units = []

        if not job:
            update_message = safe_dom.Text(
                'Peer review statistics have not been calculated yet.')
        else:
            if job.status_code == jobs.STATUS_CODE_COMPLETED:
                stats = transforms.loads(job.output)
                stats_calculated = True

                for unit in course.get_peer_reviewed_units():
                    if unit.unit_id in stats['counts_by_completed_reviews']:
                        unit_stats = (
                            stats['counts_by_completed_reviews'][unit.unit_id])
                        serialized_units.append({
                            'stats': unit_stats,
                            'title': unit.title,
                            'unit_id': unit.unit_id,
                        })
                update_message = safe_dom.Text("""
                    Peer review statistics were last updated at
                    %s in about %s second(s).""" % (
                        job.updated_on.strftime(HUMAN_READABLE_TIME_FORMAT),
                        job.execution_time_sec))
            elif job.status_code == jobs.STATUS_CODE_FAILED:
                update_message = safe_dom.NodeList().append(
                    safe_dom.Text("""
                        There was an error updating peer review statistics.
                        Here is the message:""")
                ).append(
                    safe_dom.Element('br')
                ).append(
                    safe_dom.Element('blockquote').add_child(
                        safe_dom.Element('pre').add_text('\n%s' % job.output)))
            else:
                update_message = safe_dom.Text("""
                    Peer review statistics update started at %s and is running
                    now. Please come back shortly.""" % job.updated_on.strftime(
                        HUMAN_READABLE_TIME_FORMAT))

        return jinja2.utils.Markup(self.get_template(
            'stats.html', [os.path.dirname(__file__)]
        ).render({
            'errors': errors,
            'serialized_units': serialized_units,
            'serialized_units_json': transforms.dumps(serialized_units),
            'stats_calculated': stats_calculated,
            'update_message': update_message,
        }, autoescape=True))
