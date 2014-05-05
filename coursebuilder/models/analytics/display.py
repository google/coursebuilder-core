# Copyright 2014 Google Inc. All Rights Reserved.
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

"""Module providing analytics display as HTML/JS."""

__author__ = 'Mike Gainer (mgainer@google.com)'

from common import safe_dom
from controllers import utils
from models import data_sources
from models import jobs
from models.analytics import utils as analytics_utils
from modules.mapreduce import mapreduce_module


def _generate_display_html(template_renderer, xsrf, app_context, analytics):
    # Package-protected: pylint: disable-msg=protected-access

    # First, load jobs for all generators required for an analytic.
    # Jobs may directly contain small results, just hold references to
    # larger results, or both.
    any_generator_not_running = False
    data_source_jobs = {}
    for generator_class in analytics_utils._generators_for_analytics(analytics):
        job = generator_class(app_context).load()
        data_source_jobs[generator_class] = job
        if not job or job.has_finished:
            any_generator_not_running = True

    # Generate HTML section for each analytic.
    html_sections = []
    for analytic in analytics:
        html_sections.extend(_generate_analytic_section(
            template_renderer, xsrf, app_context, analytic, data_source_jobs))

    # Generate page content
    token = data_sources.utils.generate_data_source_token(xsrf)
    names_of_analytics_with_generators = []
    for analytic in analytics:
        if analytics_utils._generators_for_analytics([analytic]):
            names_of_analytics_with_generators.append(analytic.name)
    return template_renderer.render(
        None, 'models/analytics/display.html',
        {
            'data_source_token': token,
            'sections': html_sections,
            'any_generator_not_running': any_generator_not_running,
            'xsrf_token_run': xsrf.create_xsrf_token('run_analytics'),
            'analytics': names_of_analytics_with_generators,
            'r': template_renderer.get_current_url(),
        })


def _generate_analytic_section(template_renderer, xsrf, app_context,
                               analytic, data_source_jobs):
    html_sections = []

    # Collect statuses of generators and build a display messages for each.
    generator_status_messages = []
    any_generator_still_running = False
    all_generators_completed_ok = True
    all_generators_have_ever_run = True
    for generator_class in analytic.generator_classes:
        job = data_source_jobs[generator_class]
        if job is None:
            all_generators_have_ever_run = False
            all_generators_completed_ok = False
        elif job.status_code != jobs.STATUS_CODE_COMPLETED:
            all_generators_completed_ok = False
            if not job.has_finished:
                any_generator_still_running = True
        generator_status_messages.append(
            _get_generator_status_message(generator_class, job).append(
                _get_pipeline_link(xsrf, app_context, generator_class, job)))

    # <h3> title block.
    html_sections.append(safe_dom.Element('h3').add_text(analytic.title))
    html_sections.append(safe_dom.Element('br'))

    # If this source wants to generate inline values for its template,
    # and all generators that this source depends are complete (or zero
    # generators are depended on) then-and-only-then allow the source
    # to generate template values
    if all_generators_completed_ok:
        template_values = {'analytic': analytic.name}
        for source_class in analytic.data_source_classes:
            if issubclass(source_class, data_sources.SynchronousQuery):
                required_generator_classes = (
                    # Utils has package-private functions common to analytics
                    # pylint: disable-msg=protected-access
                    analytics_utils._get_required_generators(source_class))
                synchronous_query_jobs = []
                for generator_class in required_generator_classes:
                    synchronous_query_jobs.append(
                        data_source_jobs[generator_class])
                source_class.fill_values(app_context, template_values,
                                         *synchronous_query_jobs)

        html_sections.append(template_renderer.render(
                analytic, analytic.template_name, template_values))

    # Boilerplate content for each analytic's required generators
    html_sections.append(template_renderer.render(
        None, 'models/analytics/common_footer.html',
        {
            'analytic': analytic.name,
            'any_generator_still_running': any_generator_still_running,
            'all_generators_have_ever_run': all_generators_have_ever_run,
            'status_messages': generator_status_messages,
            'xsrf_token_run': xsrf.create_xsrf_token('run_analytics'),
            'xsrf_token_cancel': xsrf.create_xsrf_token('cancel_analytics'),
            'r': template_renderer.get_current_url(),
        }))
    return html_sections


def _get_generator_status_message(generator_class, job):
    message = safe_dom.NodeList()

    generator_description = generator_class.get_description()
    if job is None:
        message.append(safe_dom.Text(
            'Statistics for %s have not been calculated yet' %
            generator_description))
    elif job.status_code == jobs.STATUS_CODE_COMPLETED:
        message.append(safe_dom.Text(
            'Statistics for %s were last updated at %s in about %s sec.' % (
                generator_description,
                job.updated_on.strftime(utils.HUMAN_READABLE_TIME_FORMAT),
                job.execution_time_sec)))
    elif job.status_code == jobs.STATUS_CODE_FAILED:
        message.append(safe_dom.Text(
            'There was an error updating %s ' % generator_description +
            'statistics.  Error msg:'))
        message.append(safe_dom.Element('br'))
        if issubclass(generator_class, jobs.MapReduceJob):
            error_message = jobs.MapReduceJob.get_error_message(job)
        else:
            error_message = job.output
        message.append(safe_dom.Element('blockquote').add_child(
            safe_dom.Element('pre').add_text(error_message)))
    else:
        message.append(safe_dom.Text(
            'Job for %s statistics started at %s and is running now.' % (
               generator_description,
               job.updated_on.strftime(utils.HUMAN_READABLE_TIME_FORMAT))))
    return message


def _get_pipeline_link(xsrf, app_context, generator_class, job):
    ret = safe_dom.NodeList()
    if (not issubclass(generator_class, jobs.MapReduceJob) or
        # Don't give access to the pipeline details UI unless someone
        # has actively intended to provide access.  The UI allows you to
        # kill jobs, and we don't want naive users stumbling around in
        # there without adult supervision.
        not mapreduce_module.GCB_ENABLE_MAPREDUCE_DETAIL_ACCESS.value or

        # Status URL may not be available immediately after job is launched;
        # pipeline setup is done w/ 'yield', and happens a bit later.
        not job or not jobs.MapReduceJob.has_status_url(job)):
        return ret

    if job.has_finished:
        link_text = 'View completed job run details'
    else:
        link_text = 'Check status of job'

    status_url = jobs.MapReduceJob.get_status_url(
        job, app_context.get_namespace_name(),
        xsrf.create_xsrf_token(mapreduce_module.XSRF_ACTION_NAME))
    ret.append(safe_dom.Text('    '))
    ret.append(safe_dom.A(status_url, target='_blank').add_text(link_text))
    return ret
