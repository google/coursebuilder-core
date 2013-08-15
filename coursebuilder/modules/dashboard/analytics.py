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

"""Classes and methods to create and manage analytics dashboards."""

__author__ = 'Sean Lip (sll@google.com)'

import os

from common import safe_dom
from controllers.utils import ApplicationHandler
from controllers.utils import HUMAN_READABLE_TIME_FORMAT
import jinja2
from models import jobs
from models import transforms
from models import utils
from models.models import Student


class ComputeStudentStats(jobs.DurableJob):
    """A job that computes student statistics."""

    class ScoresAggregator(object):
        """Aggregates scores statistics."""

        def __init__(self):
            # We store all data as tuples keyed by the assessment type name.
            # Each tuple keeps:
            #     (student_count, sum(score))
            self.name_to_tuple = {}

        def visit(self, student):
            if student.scores:
                scores = transforms.loads(student.scores)
                for key in scores.keys():
                    if key in self.name_to_tuple:
                        count = self.name_to_tuple[key][0]
                        score_sum = self.name_to_tuple[key][1]
                    else:
                        count = 0
                        score_sum = 0
                    self.name_to_tuple[key] = (
                        count + 1, score_sum + float(scores[key]))

    class EnrollmentAggregator(object):
        """Aggregates enrollment statistics."""

        def __init__(self):
            self.enrolled = 0
            self.unenrolled = 0

        def visit(self, student):
            if student.is_enrolled:
                self.enrolled += 1
            else:
                self.unenrolled += 1

    def run(self):
        """Computes student statistics."""
        enrollment = self.EnrollmentAggregator()
        scores = self.ScoresAggregator()
        mapper = utils.QueryMapper(
            Student.all(), batch_size=500, report_every=1000)

        def map_fn(student):
            enrollment.visit(student)
            scores.visit(student)

        mapper.run(map_fn)

        data = {
            'enrollment': {
                'enrolled': enrollment.enrolled,
                'unenrolled': enrollment.unenrolled},
            'scores': scores.name_to_tuple}

        return data


class StudentEnrollmentAndScoresHandler(ApplicationHandler):
    """Shows student enrollment analytics on the dashboard."""

    # The key used in the statistics dict that generates the dashboard page.
    # Must be unique.
    name = 'enrollment_and_scores'
    # The class that generates the data to be displayed. It should have a
    # get_stats() method.
    stats_computer = ComputeStudentStats

    def get_markup(self, job):
        """Returns Jinja markup for peer review analytics."""
        template_values = {}
        errors = []
        stats_calculated = False
        update_message = safe_dom.Text('')

        if not job:
            update_message = safe_dom.Text(
                'Enrollment/assessment statistics have not been calculated '
                'yet.')
        else:
            if job.status_code == jobs.STATUS_CODE_COMPLETED:
                stats = transforms.loads(job.output)
                stats_calculated = True

                template_values['enrolled'] = stats['enrollment']['enrolled']
                template_values['unenrolled'] = (
                    stats['enrollment']['unenrolled'])

                scores = []
                total_records = 0
                for key, value in stats['scores'].items():
                    total_records += value[0]
                    avg = round(value[1] / value[0], 1) if value[0] else 0
                    scores.append({'key': key, 'completed': value[0],
                                   'avg': avg})
                template_values['scores'] = scores
                template_values['total_records'] = total_records

                update_message = safe_dom.Text("""
                    Enrollment and assessment statistics were last updated at
                    %s in about %s second(s).""" % (
                        job.updated_on.strftime(HUMAN_READABLE_TIME_FORMAT),
                        job.execution_time_sec))
            elif job.status_code == jobs.STATUS_CODE_FAILED:
                update_message = safe_dom.NodeList().append(
                    safe_dom.Text("""
                        There was an error updating enrollment/assessment
                        statistics. Here is the message:""")
                ).append(
                    safe_dom.Element('br')
                ).append(
                    safe_dom.Element('blockquote').add_child(
                        safe_dom.Element('pre').add_text('\n%s' % job.output)))
            else:
                update_message = safe_dom.Text(
                    'Enrollment and assessment statistics update started at %s'
                    ' and is running now. Please come back shortly.' %
                    job.updated_on.strftime(HUMAN_READABLE_TIME_FORMAT))

        template_values['stats_calculated'] = stats_calculated
        template_values['errors'] = errors
        template_values['update_message'] = update_message

        return jinja2.utils.Markup(self.get_template(
            'basic_analytics.html', [os.path.dirname(__file__)]
        ).render(template_values, autoescape=True))
