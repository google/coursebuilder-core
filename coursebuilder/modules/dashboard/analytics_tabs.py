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

"""Registration of sub-tabs for under Dashboard > Analytics."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import re


class Registry(object):

    class _Tab(object):

        def __init__(self, name, title, analytics):
            if not re.match('^[a-z0-9_]+$', name):
                raise ValueError('Sub-tabs under Dashboard->Analytics must '
                                 'have names consisting only of lowercase '
                                 'letters, numbers, and underscore.')
            if len(analytics) < 1:
                raise ValueError('Sub-tabs under Dashboard->Analytics must '
                                 'contain at least one analytic.')

            self._name = name
            self._title = title
            self._analytics = analytics

        @property
        def name(self):
            return self._name

        @property
        def title(self):
            return self._title

        @property
        def analytics(self):
            return self._analytics

    _tabs = []

    @classmethod
    def register(cls, tab_name, tab_title, analytics):
        if cls._get_tab(tab_name):
            raise ValueError(
                'There is already an analytics sub-tab named "%s" registered.' %
                tab_name)
        cls._tabs.append(cls._Tab(tab_name, tab_title, analytics))

    @classmethod
    def _get_tab(cls, name):
        matches = [tab for tab in cls._tabs if tab.name == name]
        return matches[0] if matches else None

    @classmethod
    def _get_registered_tabs(cls):
        return cls._tabs

    @classmethod
    def _get_default_tab_name(cls):
        return cls._tabs[0].name
