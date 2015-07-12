# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Unit tests for the Dashboard module."""

__author__ = 'Michael Gainer (mgainer@google.com)'

import unittest

from modules.dashboard import tabs


class TabTests(unittest.TestCase):

    def tearDown(self):
        tabs.Registry._tabs_by_group.clear()
        super(TabTests, self).tearDown()

    def _assert_name_order(self, expected):
        actual = [t.name for t in tabs.Registry.get_tab_group('group')]
        self.assertEquals(expected, actual)

    def test_ordering_unordered_sort_stable(self):
        tabs.Registry.register('group', 'a', 'A')
        tabs.Registry.register('group', 'b', 'B')
        tabs.Registry.register('group', 'c', 'C')
        tabs.Registry.register('group', 'd', 'D')
        self._assert_name_order(['a', 'b', 'c', 'd'])

    def test_force_first(self):
        tabs.Registry.register('group', 'a', 'A')
        tabs.Registry.register('group', 'b', 'B')
        tabs.Registry.register('group', 'c', 'C')
        tabs.Registry.register('group', 'd', 'D')
        tabs.Registry.register(
            'group', 'e', 'E',
            placement=tabs.Placement.BEGINNING)
        self._assert_name_order(['e', 'a', 'b', 'c', 'd'])

    def test_force_last(self):
        tabs.Registry.register(
            'group', 'e', 'E',
            placement=tabs.Placement.END)
        tabs.Registry.register('group', 'a', 'A')
        tabs.Registry.register('group', 'b', 'B')
        tabs.Registry.register('group', 'c', 'C')
        tabs.Registry.register('group', 'd', 'D')
        self._assert_name_order(['a', 'b', 'c', 'd', 'e'])

    def test_force_multiple_first(self):
        tabs.Registry.register(
            'group', 'a', 'A',
            placement=tabs.Placement.BEGINNING)
        tabs.Registry.register('group', 'b', 'B')
        tabs.Registry.register('group', 'c', 'C')
        tabs.Registry.register('group', 'd', 'D')
        tabs.Registry.register(
            'group', 'e', 'E',
            placement=tabs.Placement.BEGINNING)
        self._assert_name_order(['a', 'e', 'b', 'c', 'd'])

    def test_force_multiple_last(self):
        tabs.Registry.register(
            'group', 'a', 'A',
            placement=tabs.Placement.END)
        tabs.Registry.register('group', 'b', 'B')
        tabs.Registry.register('group', 'c', 'C')
        tabs.Registry.register('group', 'd', 'D')
        tabs.Registry.register(
            'group', 'e', 'E',
            placement=tabs.Placement.END)
        self._assert_name_order(['b', 'c', 'd', 'a', 'e'])

    def test_complex(self):
        tabs.Registry.register(
            'group', 'a', 'A',
            placement=tabs.Placement.END)
        tabs.Registry.register(
            'group', 'b', 'B',
            placement=tabs.Placement.MIDDLE)
        tabs.Registry.register(
            'group', 'c', 'C',
            placement=tabs.Placement.BEGINNING)
        tabs.Registry.register(
            'group', 'd', 'D',
            placement=tabs.Placement.MIDDLE)
        tabs.Registry.register(
            'group', 'e', 'E',
            placement=tabs.Placement.BEGINNING)
        self._assert_name_order(['c', 'e', 'b', 'd', 'a'])
