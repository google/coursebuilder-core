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

"""Module providing analytics registry."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import re

from modules.analytics import base_types
from modules.analytics import utils


class Registry(object):
    """Collect and operate on analytics."""

    class _Analytic(object):
        """POD structure summarizing an analytic and its generators/sources."""

        def __init__(self, name, title, html_template_name,
                     data_source_classes):
            self._name = name
            self._title = title
            self._template_name = html_template_name
            self._data_source_classes = data_source_classes

        @property
        def name(self):
            return self._name

        @property
        def title(self):
            return self._title

        @property
        def template_name(self):
            return self._template_name

        @property
        def generator_classes(self):
            ret = set()
            for source_class in self.data_source_classes:
                # Utils holds packagage-private functions common to analytics
                # pylint: disable-msg=protected-access
                ret.update(utils._get_required_generators(source_class))
            return ret

        @property
        def data_source_classes(self):
            return set(self._data_source_classes)

    _analytics = []  # As array for consistent ordering

    @classmethod
    def register(cls, name, title, html_template_name,
                 data_source_classes=None):
        """Register a new analytic.

        This function should be used at module initialization time.  It is
        not anticipated that analytics will be dynamically coming and
        going from the set shown on the dashboard.  (To this end, there is
        no un-register function provided.)

        Args:
            name: Valid Javascript identifier to be used for this analytic
                when generating scripts via templates.

            title: Section title for analytic on Dashboard -> Analytics page.

            html_template_name: Name of a file which contains a Jinja
                template which will be used to generate a chart or graph
                for the analytic.  This can be specified as a path relative
                to the CB installation root
                (e.g. 'modules/my_new_module/my_analytic.html'), or
                relative to any of the data sources or generators used for
                the analytic (meaning you can just use the name of the
                HTML file without any path components if it's in the
                same directory).

            data_source_classes: An optional array of data source classes.
                This should contain only classes inheriting from
                SynchronousQuery.
        Raises:
            ValueError: when any of
            - name is already registered as an analytic
            - name is not a valid JavaScript identifier.
            - data_source_classes contains a type that is not a data source.
        """

        # Mustn't use static mutable [] as default argument; regularize here.
        data_source_classes = data_source_classes or []

        # Sanity check
        if name and not re.match('^[_0-9a-z]+$', name):
            raise ValueError('name must contain only lowercase letters, '
                             'numbers or underscore characters')
        for data_source_class in data_source_classes:
            if (not issubclass(data_source_class,
                               base_types.SynchronousQuery)):
                raise ValueError(
                    'data_source_classes must contain only types '
                    'derived from SynchronousQuery')

        # Register, if we may.
        if cls._find_by_name(name):
            raise ValueError(
                'Analytic %s is already registered' % name)
        cls._analytics.append(Registry._Analytic(
            name, title, html_template_name, data_source_classes))

    @classmethod
    def _run_generators(cls, app_context, generator_classes):
        for generator_class in generator_classes:
            generator_class(app_context).submit()

    @classmethod
    def run_all_generators(cls, app_context):
        """Run all generators for all registered analytics.

        All generators registered as being required by all data sources in
        all analytics are started (if they are not already running).  For
        use from analytics dashboard.

        Args:
            app_context: Used to establish data visibility restrictions.
        """
        cls._run_generators(app_context, cls._all_generator_classes())

    @classmethod
    def any_generator_not_running(cls, app_context):
        """Check whether any generator for any registered analytic is inactive.

        If all generators are running, then calling run_all_generators() is
        pointless, as nothing will change.  This function permits the dashboard
        UI to suppress the run-all button when it would be a no-op.

        Args:
            app_context: Used to establish data visibility restrictions.
        Returns:
            True if all generators are queued or running; False otherwise.
        """
        for generator_class in cls._all_generator_classes():
            if not generator_class(app_context).is_active():
                return True
        return False

    @classmethod
    def run_generators_for_analytic(cls, app_context, name):
        """Run all generators for a specific registered analytic.

        All generators registered as being required for all data sources for
        the named analytic are started (if they are not already running).
        Intended for use from the analytics dashboard.

        Args:
            app_context: Used to establish data visibility restrictions.
            name: Name the analytic for which to run generators.  Should match
                the name with which it was registered.
        """

        analytic = cls._find_by_name(name)
        if analytic:
            cls._run_generators(app_context, analytic.generator_classes)

    @classmethod
    def cancel_generators_for_analytic(cls, app_context, name):
        """Cancel all generators for a specific registered analytic.

        All generators registered as being required for all data sources
        for the named analytic are requested to stop (if they are not
        already stopped).  Note that this is best-effort, and necessarily
        races with actual job completion.  Intended for use from the
        analytics dashboard.

        Args:
            app_context: Used to establish data visibility restrictions.
            name: Name the analytic for which to run generators.  Should match
                the name with which it was registered.
        """

        analytic = cls._find_by_name(name)
        if analytic:
            for generator_class in analytic.generator_classes:
                generator_class(app_context).cancel()

    @classmethod
    def _for_testing_only_clear(cls):
        cls._analytics = []

    @classmethod
    def _get_analytics(cls):
        return cls._analytics

    @classmethod
    def _all_generator_classes(cls):
        generator_classes = set()
        for analytic in cls._analytics:
            generator_classes.update(analytic.generator_classes)
        return generator_classes

    @classmethod
    def _find_by_name(cls, name):
        matches = [a for a in cls._analytics if a.name == name]
        return matches[0] if matches else None
