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

"""Module providing base types for analytics data sources."""

__author__ = 'Mike Gainer (mgainer@google.com)'


class _DataSource(object):
    """Common base class for all kinds of data sources."""

    @staticmethod
    def required_generators():
        """Tell what long-running jobs (if any) are required for this feed.

        Return either None, a single class, or an array of classes.
        All classes named must derive from DurableJobBase.  When the
        framework calls to the feed display content generator function,
        the jobs will be provided singly as parameters.  E.g., if you
        return [FooGenerator, BarGenerator] here, your fill_values
        method should be declared:

        @staticmethod
        def fill_values(app_context, template_values, foo_job, bar_job):
            ...
            template_values['foo_stuff'] = ....
        """

        return None


class SynchronousQuery(_DataSource):
    """Inherit from this class to indicate your data source is synchronous.

    By synchronous, we mean that when the dashboard display is
    created, we directly generate HTML from a template and parameters,
    as opposed to asynchronously fetching data up to the page (via
    JavaScript) after the page has loaded.
    """

    @staticmethod
    def fill_values(app_context, template_values, foo_job):
        """Set key/value strings for use in HTML template expansion.

        Args:
            app_context: the context taking the request.  This can be
                used to identify the namespace for the request.
            template_values: A hash to be filled in by fill_values.
                Its contents are provided to the template interpreter.
                All sources used by a single analytic contribute to
                the same template_values dict; be careful to avoid
                name collisions.
            foo_job: One parameter for each of the job classes
                returned by required_generators() method in this
                class.  These jobs are passed as separate parameters
                so they can be given meaningful names in your function.
        Returns:
            Return value is ignored.
        """

        raise NotImplementedError(
            'Feed classes which synchronously provide parameters for '
            'expansion into their HTML templates must implement the '
            'fill_values method.')
