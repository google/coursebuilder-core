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


class PeerReviewStats(ApplicationHandler):
    """Shows peer review analytics on the dashboard."""

    def get(self):
        """Returns HTML code for peer review analytics."""

        course = courses.Course(self)
        peer_reviewed_units = course.get_peer_reviewed_units()

        serializable_units = []
        for unit in peer_reviewed_units:
            serializable_units.append({
                'unit_id': unit.unit_id,
                # TODO(sll): Replace this with the correct counts when the
                # backend is finished.
                'stats': [600, 43, 12, 10, 2],
                'title': unit.title,
            })

        return jinja2.utils.Markup(self.get_template(
            'review_stats.html', [os.path.dirname(__file__)]
        ).render({
            'peer_reviewed_units': peer_reviewed_units,
            'serialized_units': transforms.dumps(serializable_units),
        }, autoescape=True))
