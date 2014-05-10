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

        def __init__(self, group, name, title, contents):
            if not re.match('^[a-z0-9_]+$', name):
                raise ValueError('Sub-tabs under Dashboard must '
                                 'have names consisting only of lowercase '
                                 'letters, numbers, and underscore.')
            self._group = group
            self._name = name
            self._title = title
            self._contents = contents

        @property
        def group(self):
            return self._group

        @property
        def name(self):
            return self._name

        @property
        def title(self):
            return self._title

        @property
        def contents(self):
            return self._contents

    _tabs_by_group = {}

    @classmethod
    def register(cls, group_name, tab_name, tab_title, contents=None):
        if cls.get_tab(group_name, tab_name):
            raise ValueError(
                'There is already a sub-tab named "%s" ' % tab_name +
                'registered in group %s.' % group_name)
        tab = cls._Tab(group_name, tab_name, tab_title, contents)
        cls._tabs_by_group.setdefault(group_name, []).append(tab)

    @classmethod
    def get_tab(cls, group_name, tab_name):
        matches = [tab for tab in cls._tabs_by_group.get(group_name, [])
                   if tab.name == tab_name]
        return matches[0] if matches else None

    @classmethod
    def get_tab_group(cls, group_name):
        return cls._tabs_by_group.get(group_name, None)
