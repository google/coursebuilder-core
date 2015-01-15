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

"""Cron job definitions for the review subsystem."""

__author__ = [
    'johncox@google.com (John Cox)',
]

import logging

from controllers import sites
from controllers import utils
from models import courses
from modules.review import review
from google.appengine.api import namespace_manager

_LOG = logging.getLogger('modules.reviews.cron')
logging.basicConfig()


class ExpireOldAssignedReviewsHandler(utils.BaseHandler):
    """Iterates through all units in all courses, expiring old review steps.

    The system will run a maximum of one of these jobs at any given time. This
    is enforced by the 10 minute execution time limit on cron jobs plus the
    scheduler, which is configured to run this every 15 minutes.

    Write operations done by this handler must be atomic since admins may visit
    this page at any time, kicking off any number of runs.
    """

    def get(self):
        """Runs the expiry operation once for each peer-reviwed unit."""
        try:
            self.response.headers['Content-Type'] = 'text/plain'

            # namespace_string -> [{
            #       'id': unit_id_string, 'review_window_mins': int}]
            namespace_to_units = {}  # namespace_string -> [unit_id_strings]
            for context in sites.get_all_courses():
                namespace = context.get_namespace_name()
                namespace_to_units[namespace] = []
                course = courses.Course(None, context)

                for unit in course.get_peer_reviewed_units():
                    namespace_to_units[namespace].append({
                        'review_window_mins': (
                            unit.workflow.get_review_window_mins()),
                        'id': str(unit.unit_id),
                    })

            total_count = 0
            total_expired_count = 0
            total_exception_count = 0
            _LOG.info('Begin expire_old_assigned_reviews cron')

            for namespace, units in namespace_to_units.iteritems():
                start_namespace_message = (
                    ('Begin processing course in namespace "%s"; %s unit%s '
                     'found') % (
                         namespace, len(units), '' if len(units) == 1 else 's'))
                _LOG.info(start_namespace_message)

                for unit in units:
                    begin_unit_message = 'Begin processing unit %s' % unit['id']
                    _LOG.info(begin_unit_message)

                    namespace_manager.set_namespace(namespace)
                    expired_keys, exception_keys = (
                        review.Manager.expire_old_reviews_for_unit(
                            unit['review_window_mins'], unit['id']))

                    unit_expired_count = len(expired_keys)
                    unit_exception_count = len(exception_keys)
                    unit_total_count = unit_expired_count + unit_exception_count
                    total_expired_count += unit_expired_count
                    total_exception_count += total_exception_count
                    total_count += unit_total_count

                    end_unit_message = (
                        'End processing unit %s. Expired: %s, Exceptions: %s, '
                        'Total: %s' % (
                            unit['id'], unit_expired_count,
                            unit_exception_count, unit_total_count))
                    _LOG.info(end_unit_message)

                _LOG.info('Done processing namespace "%s"', namespace)

            end_message = (
                ('End expire_old_assigned_reviews cron. Expired: %s, '
                 'Exceptions : %s, Total: %s') % (
                     total_expired_count, total_exception_count, total_count))
            _LOG.info(end_message)
            self.response.write('OK\n')
        except:  # Hide all errors. pylint: disable=bare-except
            pass
