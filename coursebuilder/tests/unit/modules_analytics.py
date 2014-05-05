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


"""Unit tests for the anaytics internals in modules/analytics/*.py."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import datetime
import unittest

import jinja2

from common import jinja_utils
from models import jobs
from modules.analytics import analytics

#-------------------------------------------------------------------------------
# Mock objects to simulate models/jobs subsystem


class MockAppContext(object):

    def __init__(self, namespace_name):
        self._namespace_name = namespace_name

    def get_namespace_name(self):
        return self._namespace_name


class MockJobEntity(object):

    def __init__(self, status=jobs.STATUS_CODE_STARTED, output=None):
        self._status = status
        self._output = output
        self._updated_on = datetime.datetime.utcnow()

    def complete(self, output):
        self._complete(output, jobs.STATUS_CODE_COMPLETED)

    def fail(self, output):
        self._complete(output, jobs.STATUS_CODE_FAILED)

    def _complete(self, output, status):
        self._output = output
        self._status = status
        now = datetime.datetime.utcnow()
        self._execution_time_sec = int((now - self._updated_on).total_seconds())
        self._updated_on = now

    def start(self):
        self._status = jobs.STATUS_CODE_STARTED
        self._updated_on = datetime.datetime.utcnow()

    @property
    def output(self):
        return self._output

    @property
    def status_code(self):
        return self._status

    @property
    def has_finished(self):
        return self._status in (
            jobs.STATUS_CODE_COMPLETED, jobs.STATUS_CODE_FAILED)

    @property
    def updated_on(self):
        return self._updated_on

    @property
    def execution_time_sec(self):
        return self._execution_time_sec


class MockJobBase(jobs.DurableJobBase):

    _jobs = {}  # Mock persistent store

    @classmethod
    def clear_jobs(cls):
        cls._jobs.clear()

    def __init__(self, app_context):
        super(MockJobBase, self).__init__(app_context)

    def submit(self):
        job = self.load()
        if not job:
            job = self._create_job()
        if job.has_finished:
            job.start()

    def load(self):
        return self._jobs.get(self._get_name(), None)

    @classmethod
    def _create_job(cls):
        job = MockJobEntity()
        cls._jobs[cls._get_name()] = job
        return job

    @classmethod
    def _get_name(cls):
        return cls.__name__

    def cancel(self):
        job = self.load()
        if job and not job.has_finished:
            job.fail('Canceled')

#-------------------------------------------------------------------------------
# Mock objects to simulate page-display level constructs


class MockXsrfCreator(object):

    def create_xsrf_token(self, action):
        return 'xsrf_' + action


class MockHandler(object):

    def __init__(self, app_context):
        self._templates = {}
        self._app_context = app_context

    def get_template(self, template_name, template_dirs):
        jinja_environment = jinja_utils.create_jinja_environment(
            loader=jinja2.FileSystemLoader(template_dirs))
        return jinja_environment.get_template(template_name)

    @property
    def app_context(self):
        return self._app_context


#-------------------------------------------------------------------------------
# Generators and data source classes for use in analytics.


class GenOne(MockJobBase):

    @staticmethod
    def get_description():
        return 'gen one'


class GenTwo(MockJobBase):

    @staticmethod
    def get_description():
        return 'gen two'


class GenThree(MockJobBase):

    @staticmethod
    def get_description():
        return 'gen three'


class NoGenSource(analytics.SynchronousQuery):

    @staticmethod
    def fill_values(app_context, template_values):
        template_values['no_gen_source'] = 'no_gen_value'


class OneGenSource(analytics.SynchronousQuery):

    @staticmethod
    def required_generators():
        return GenOne

    @staticmethod
    def fill_values(app_context, template_values, gen_one_job):
        template_values['one_gen_source_gen_one'] = (
            gen_one_job.output)


class TwoGenSource(analytics.SynchronousQuery):

    @staticmethod
    def required_generators():
        return [GenOne, GenTwo]

    @staticmethod
    def fill_values(app_context, template_values, gen_one_job, gen_two_job):
        template_values['two_gen_source_gen_one'] = (
            gen_one_job.output)
        template_values['two_gen_source_gen_two'] = (
            gen_two_job.output)


class ThreeGenSource(analytics.SynchronousQuery):

    @staticmethod
    def required_generators():
        return [GenOne, GenTwo, GenThree]

    @staticmethod
    def fill_values(app_context, template_values, gen_one_job, gen_two_job,
                    gen_three_job):
        template_values['three_gen_source_gen_one'] = (
            gen_one_job.output)
        template_values['three_gen_source_gen_two'] = (
            gen_two_job.output)
        template_values['three_gen_source_gen_three'] = (
            gen_three_job.output)


#-------------------------------------------------------------------------------
# Actual tests.


class AnalyticsTests(unittest.TestCase):

    def setUp(self):
        MockJobBase.clear_jobs()
        analytics.Registry._for_testing_only_clear()
        self._mock_app_context = MockAppContext('testing')
        self._mock_handler = MockHandler(self._mock_app_context)
        self._mock_xsrf = MockXsrfCreator()

    def _generate_analytics_page(self):
        sections = analytics.generate_display_html(
            self._mock_handler, self._mock_xsrf)
        renderer = analytics._TemplateRenderer(self._mock_handler)
        return renderer.render(
            None,
            'tests/unit/modules_analytics_dashboard.html',
            {'sections': sections})

    def test_illegal_name(self):
        with self.assertRaisesRegexp(ValueError, 'name must contain'):
            analytics.Registry.register('A', 'Foo', 'foo.html')
        with self.assertRaisesRegexp(ValueError, 'name must contain'):
            analytics.Registry.register(' ', 'Foo', 'foo.html')
        with self.assertRaisesRegexp(ValueError, 'name must contain'):
            analytics.Registry.register('#', 'Foo', 'foo.html')

    def test_illegal_generator(self):
        with self.assertRaisesRegexp(ValueError, 'data_source_classes'):
            analytics.Registry.register('foo', 'foo', 'foo', [MockHandler])

    def test_run_all_with_no_analytics_does_not_crash(self):
        analytics.Registry.run_all_generators(self._mock_app_context)

    def test_check_all_with_no_analytics_does_not_crash(self):
        self.assertFalse(analytics.Registry.any_generator_not_running(
            self._mock_app_context))

    def test_run_generator_for_unknown_analytics_does_not_crash(self):
        analytics.Registry.run_generators_for_analytic(
            self._mock_app_context, 'foo')

    def test_cancel_generator_for_unknown_analytics_does_not_crash(self):
        analytics.Registry.cancel_generators_for_analytic(
            self._mock_app_context, 'foo')

    def test_run_generator_for_analytic_with_none_does_not_crash(self):
        name = 'no_generator'
        analytics.Registry.register(
            name, name, 'modules_analytics_section.html', [NoGenSource])
        analytics.Registry.run_generators_for_analytic(
            self._mock_app_context, name)

    def test_cancel_generator_for_analytic_with_none_does_not_crash(self):
        name = 'no_generator'
        analytics.Registry.register(
            name, name, 'modules_analytics_section.html', [NoGenSource])
        analytics.Registry.cancel_generators_for_analytic(
            self._mock_app_context, name)

    def test_no_generator_display(self):
        name = 'no_generator'
        analytics.Registry.register(
            name, name, 'modules_analytics_section.html', [NoGenSource])
        result = self._generate_analytics_page()

        # Statistic reports result to page
        self.assertIn('no_generator_no_gen_source: "no_gen_value"', result)
        # Statistic does not have a run/cancel button; it has no generators
        # which depend on jobs.
        self.assertNotIn('gdb-run-analytic-simple', result)
        self.assertNotIn('gdb-cancel-analytic-simple', result)

    def test_generator_run_cancel_state_display(self):
        name = 'foo'
        analytics.Registry.register(
            name, name, 'modules_analytics_section.html', [OneGenSource])

        result = self._generate_analytics_page()
        self.assertIn('Statistics for gen one have not been', result)
        self.assertIn('  Run Jobs', result)
        self.assertIn('action=run_analytic', result)
        self.assertTrue(analytics.Registry.any_generator_not_running(
            self._mock_app_context))

        analytics.Registry.run_generators_for_analytic(
            self._mock_app_context, name)
        result = self._generate_analytics_page()
        self.assertIn('Job for gen one statistics started at', result)
        self.assertIn('Cancel Jobs', result)
        self.assertIn('action=cancel_analytic', result)
        self.assertFalse(analytics.Registry.any_generator_not_running(
            self._mock_app_context))

        analytics.Registry.cancel_generators_for_analytic(
            self._mock_app_context, name)
        result = self._generate_analytics_page()
        self.assertIn('There was an error updating gen one statistics', result)
        self.assertIn('<pre>Canceled</pre>', result)
        self.assertIn('Re-Run Jobs', result)
        self.assertIn('action=run_analytic', result)
        self.assertTrue(analytics.Registry.any_generator_not_running(
            self._mock_app_context))

        analytics.Registry.run_generators_for_analytic(
            self._mock_app_context, name)
        result = self._generate_analytics_page()
        self.assertIn('Job for gen one statistics started at', result)
        self.assertIn('Cancel Jobs', result)
        self.assertIn('action=cancel_analytic', result)
        self.assertFalse(analytics.Registry.any_generator_not_running(
            self._mock_app_context))

        GenOne(self._mock_app_context).load().complete('run_state_display')
        result = self._generate_analytics_page()
        self.assertIn('Statistics for gen one were last updated at', result)
        self.assertIn('in about 0 sec', result)
        self.assertIn('Re-Run Jobs', result)
        self.assertIn('action=run_analytic', result)
        self.assertIn('foo_one_gen_source_gen_one: "run_state_display"', result)
        self.assertTrue(analytics.Registry.any_generator_not_running(
            self._mock_app_context))

    def test_run_all_generators(self):
        name = 'foo'
        analytics.Registry.register(
            name, name, 'modules_analytics_section.html', [OneGenSource])

        result = self._generate_analytics_page()
        self.assertIn('Statistics for gen one have not been calculated yet',
                      result)
        self.assertIn('  Run Jobs', result)
        self.assertIn('action=run_analytic', result)

        analytics.Registry.run_all_generators(self._mock_app_context)
        result = self._generate_analytics_page()
        self.assertIn('Job for gen one statistics started at', result)
        self.assertIn('Cancel Jobs', result)
        self.assertIn('action=cancel_analytic', result)

    def test_multiple_analytics_multiple_generators_multiple_sources(self):
        analytics.Registry.register(
            'trivial', 'Trivial Statistics', 'modules_analytics_section.html',
            [NoGenSource])
        analytics.Registry.register(
            'simple', 'Simple Statistics', 'modules_analytics_section.html',
            [OneGenSource])
        analytics.Registry.register(
            'complex', 'Complex Statistics', 'modules_analytics_section.html',
            [NoGenSource, OneGenSource, TwoGenSource, ThreeGenSource])

        analytics.Registry.run_all_generators(self._mock_app_context)
        self.assertFalse(analytics.Registry.any_generator_not_running(
            self._mock_app_context))

        # Verify that not-all generators are running, but that 'complex'
        # is still not reporting data, as the generator it's relying on
        # (GenThree) is still running.
        GenOne(self._mock_app_context).load().complete('gen_one_data')
        GenTwo(self._mock_app_context).load().complete('gen_two_data')
        result = self._generate_analytics_page()
        self.assertIn('simple_one_gen_source_gen_one: "gen_one_data"', result)
        self.assertIn('Statistics for gen one were last updated', result)
        self.assertIn('Statistics for gen two were last updated', result)
        self.assertIn('Job for gen three statistics started at', result)
        self.assertTrue(analytics.Registry.any_generator_not_running(
            self._mock_app_context))
        self.assertNotIn('complex_three_gen_source', result)

        # Finish last generator; should now have all data from all sources.
        GenThree(self._mock_app_context).load().complete('gen_three_data')
        result = self._generate_analytics_page()
        self.assertIn('trivial_no_gen_source: "no_gen_value"', result)
        self.assertIn('simple_one_gen_source_gen_one: "gen_one_data"', result)
        self.assertIn('complex_no_gen_source: "no_gen_value"', result)
        self.assertIn('complex_one_gen_source_gen_one: "gen_one_data"', result)
        self.assertIn('complex_two_gen_source_gen_one: "gen_one_data"', result)
        self.assertIn('complex_two_gen_source_gen_two: "gen_two_data"', result)
        self.assertIn('complex_three_gen_source_gen_one: "gen_one_data"',
                      result)
        self.assertIn('complex_three_gen_source_gen_two: "gen_two_data"',
                      result)
        self.assertIn('complex_three_gen_source_gen_three: "gen_three_data"',
                      result)

        # Verify that we _don't_ have data for sections that didn't specify
        # that source.
        self.assertIn('trivial_one_gen_source_gen_one: ""', result)
        self.assertIn('simple_no_gen_source: ""', result)

        # We should have all headers
        self.assertIn('<h3>Trivial Statistics</h3>', result)
        self.assertIn('<h3>Simple Statistics</h3>', result)
        self.assertIn('<h3>Complex Statistics</h3>', result)

        # And submission forms for analytics w/ generators
        self.assertNotIn('<input type="hidden" name="analytic" value="trivial"',
                         result)
        self.assertIn('<input type="hidden" name="analytic" value="simple"',
                      result)
        self.assertIn('<input type="hidden" name="analytic" value="complex"',
                      result)
