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

"""Module providing visualizations display as HTML/JS."""

__author__ = 'Mike Gainer (mgainer@google.com)'

from common import safe_dom
from controllers import utils
from models import data_sources
from models import jobs
from models import transforms
from models.analytics import utils as analytics_utils
from modules.mapreduce import mapreduce_module

from google.appengine.api import app_identity


def _generate_display_html(template_renderer, xsrf, app_context,
                           visualizations):
    # Package-protected: pylint: disable=protected-access

    # First, load jobs for all generators required for an visualization.
    # Jobs may directly contain small results, just hold references to
    # larger results, or both.
    any_generators = False
    any_generator_running = False
    data_source_jobs = {}
    for generator_class in analytics_utils._generators_for_visualizations(
        visualizations):
        any_generators = True
        job = generator_class(app_context).load()
        data_source_jobs[generator_class] = job
        if job and not job.has_finished:
            any_generator_running = True

    # Generate HTML section for each visualization.
    html_sections = []
    for v in visualizations:
        html_sections.extend(_generate_visualization_section(
            template_renderer, xsrf, app_context, v, data_source_jobs))

    # Generate JS to pull contents of data-sources up to page and feed it
    # to visualization functions.
    html_sections.extend(_generate_data_source_script(template_renderer,
                                                      visualizations, xsrf))

    # Generate page content
    names_of_visualizations_with_generators = []
    for visualization in visualizations:
        if analytics_utils._generators_for_visualizations([visualization]):
            names_of_visualizations_with_generators.append(visualization.name)
    rest_sources = []
    has_pagination = False  # True if any data_source has chunk size > 0
    for rdsc in analytics_utils._rest_data_source_classes(visualizations):
        rest_sources.append({
            'name': rdsc.get_name(),
            'title': rdsc.get_title(),
            'chunk_size': rdsc.get_default_chunk_size(),
        })
        has_pagination = has_pagination or rdsc.get_default_chunk_size()

    bucket_name = app_identity.get_default_gcs_bucket_name()
    has_google_cloud_services_default_bucket = (bucket_name is not None)

    return template_renderer.render(
        None, 'models/analytics/display.html',
        {
            'sections': html_sections,
            'any_generators': any_generators,
            'any_generator_running': any_generator_running,
            'xsrf_token_run': xsrf.create_xsrf_token('run_visualizations'),
            'xsrf_token_cancel': xsrf.create_xsrf_token(
                'cancel_visualizations'),
            'visualizations': names_of_visualizations_with_generators,
            'rest_sources': rest_sources,
            'r': template_renderer.get_current_url(),
            'has_pagination': has_pagination,
            'has_google_cloud_services_default_bucket':
                has_google_cloud_services_default_bucket
        })


def _generate_visualization_section(template_renderer, xsrf, app_context,
                                    visualization, data_source_jobs):
    html_sections = []

    # Collect statuses of generators and build a display messages for each.
    generator_status_messages = []
    any_generator_still_running = False
    all_generators_completed_ok = True
    for generator_class in visualization.generator_classes:
        job = data_source_jobs[generator_class]
        if job is None:
            all_generators_completed_ok = False
        elif job.status_code != jobs.STATUS_CODE_COMPLETED:
            all_generators_completed_ok = False
            if not job.has_finished:
                any_generator_still_running = True
        generator_status_messages.append(
            get_generator_status_message(generator_class, job).append(
                get_pipeline_link(xsrf, app_context, generator_class, job)))

    # If this source wants to generate inline values for its template,
    # and all generators that this source depends are complete (or zero
    # generators are depended on) then-and-only-then allow the source
    # to generate template values
    visualization_content = None
    if all_generators_completed_ok:
        template_values = {'visualization': visualization.name}
        for source_class in visualization.data_source_classes:
            if issubclass(source_class, data_sources.SynchronousQuery):
                required_generator_classes = (
                    source_class.required_generators())
                synchronous_query_jobs = []
                for generator_class in required_generator_classes:
                    synchronous_query_jobs.append(
                        data_source_jobs[generator_class])
                source_class.fill_values(app_context, template_values,
                                         *synchronous_query_jobs)

        visualization_content = template_renderer.render(
            visualization, visualization.template_name, template_values)

    html_sections.append(template_renderer.render(
        None, 'models/analytics/section.html',
        {
            'title':visualization.title,
            'visualization': visualization.name,
            'any_generator_still_running': any_generator_still_running,
            'status_messages': generator_status_messages,
            'xsrf_token_run': xsrf.create_xsrf_token('run_visualizations'),
            'xsrf_token_cancel': xsrf.create_xsrf_token(
                'cancel_visualizations'),
            'r': template_renderer.get_current_url(),
            'visualization_content':visualization_content,
        }))

    return html_sections


def get_generator_status_message(generator_class, job):
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
                job.updated_on.strftime(utils.HUMAN_READABLE_DATETIME_FORMAT),
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
        message.append(
            safe_dom.Element('div', className='gcb-message').add_child(
                safe_dom.Element('pre').add_text(error_message)))
    else:
        message.append(safe_dom.Text(
            'Job for %s statistics started at %s and is running now.' % (
               generator_description,
               job.updated_on.strftime(utils.HUMAN_READABLE_DATETIME_FORMAT))))
    return message


def get_pipeline_link(xsrf, app_context, generator_class, job):
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


def _generate_data_source_script(template_renderer, visualizations, xsrf):

    # Build list of {visualization name, [depended-upon data source names]}
    display_visualizations = {}
    for v in visualizations:
        rest_sources = [rsc.get_name() for rsc in v.rest_data_source_classes]
        if rest_sources:
            display_visualizations[v.name] = {
                'callback_name': v.name,
                'restSources': rest_sources,
                'restSourcesNotYetSeen': {
                    rest_source: True for rest_source in rest_sources}}
    if not display_visualizations:
        return []

    # Build list of {data source name, [dependent visualization names]}
    display_rest_sources = {}
    # pylint: disable=protected-access
    for rdsc in analytics_utils._rest_data_source_classes(visualizations):
        v_names = []
        for v in visualizations:
            if rdsc in v.rest_data_source_classes:
                v_names.append(v.name)
        display_rest_sources[rdsc.get_name()] = {
            'currentPage': -1,
            'pages': [],
            'crossfilterDimensions': [],
            'sourceContext': None,
            'visualizations': v_names}

    env = {
        'href': template_renderer.get_base_href(),
        'visualizations': display_visualizations,
        'restSources': display_rest_sources,
        'dataSourceToken': data_sources.utils.generate_data_source_token(xsrf),
        }
    return [template_renderer.render(
        None, 'models/analytics/rest_visualizations.html',
        {'env': transforms.dumps(env)})]
