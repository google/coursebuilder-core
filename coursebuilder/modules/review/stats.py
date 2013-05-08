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

from controllers.utils import ApplicationHandler
import jinja2
from models import courses
from models import transforms
from modules.review import peer
from google.appengine.ext import db


class ReviewStatsAggregator(object):
    """Aggregates peer review statistics."""

    def __init__(self):
        # This dict records how many submissions have a given number of
        # completed reviews.
        self.counts_by_completed_reviews = {}

    def visit(self, review_summary):
        datum = review_summary.completed_count
        if datum not in self.counts_by_completed_reviews:
            self.counts_by_completed_reviews[datum] = 1
        else:
            self.counts_by_completed_reviews[datum] += 1


class ComputeReviewStats(object):
    """Methods for computing peer review statistics."""

    @classmethod
    def get_stats(cls):
        """Return the data needed to populate the dashboard analytics view."""
        stats = ReviewStatsAggregator()

        query = db.GqlQuery(
            'SELECT * FROM %s' % peer.ReviewSummary.__name__,
            batch_size=10000)
        for review_summary in query.run():
            stats.visit(review_summary)

        max_completed_reviews = 0
        if stats.counts_by_completed_reviews:
            max_completed_reviews = max(
                stats.counts_by_completed_reviews.keys())

        completed_reviews_array = []
        for i in range(max_completed_reviews + 1):
            if i in stats.counts_by_completed_reviews:
                completed_reviews_array.append(
                    stats.counts_by_completed_reviews[i])
            else:
                completed_reviews_array.append(0)

        return {'submissions_given_completed_reviews': completed_reviews_array}


class PeerReviewStatsHandler(ApplicationHandler):
    """Shows peer review analytics on the dashboard."""

    # The key used in the statistics dict that generates the dashboard page.
    # Must be unique.
    name = 'peer_review_stats'
    # The class that generates the data to be displayed. It should have a
    # get_stats() method.
    stats_computer = ComputeReviewStats

    def get(self, stats):
        """Returns HTML code for peer review analytics."""

        course = courses.Course(self)
        peer_reviewed_units = course.get_peer_reviewed_units()

        serializable_units = []
        for unit in peer_reviewed_units:
            serializable_units.append({
                'stats': stats['submissions_given_completed_reviews'],
                'title': unit.title,
                'unit_id': unit.unit_id,
            })

        return jinja2.utils.Markup(self.get_template(
            'stats.html', [os.path.dirname(__file__)]
        ).render({
            'peer_reviewed_units': peer_reviewed_units,
            'serialized_units': transforms.dumps(serializable_units),
        }, autoescape=True))
