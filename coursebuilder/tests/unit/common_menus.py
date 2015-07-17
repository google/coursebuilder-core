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

__author__ = [
    'Michael Gainer (mgainer@google.com)'
    'Nick Retallack (nretallack@google.com)'
]

import unittest

from common import menus


can_view = lambda x: True


class MenuTests(unittest.TestCase):

    def _assert_name_order(self, group, expected):
        actual = [t.name for t in group.children]
        self.assertEquals(expected, actual)

    def test_ordering_unordered_sort_stable(self):
        group = menus.MenuGroup('menu', 'Menu')
        menus.MenuItem('a', 'A', group=group, can_view=can_view)
        menus.MenuItem('b', 'B', group=group, can_view=can_view)
        menus.MenuItem('c', 'C', group=group, can_view=can_view)
        menus.MenuItem('d', 'D', group=group, can_view=can_view)
        self._assert_name_order(group, ['a', 'b', 'c', 'd'])

    def test_force_first(self):
        group = menus.MenuGroup('menu', 'Menu')
        menus.MenuItem('a', 'A', group=group, can_view=can_view)
        menus.MenuItem('b', 'B', group=group, can_view=can_view)
        menus.MenuItem('c', 'C', group=group, can_view=can_view)
        menus.MenuItem('d', 'D', group=group, can_view=can_view)
        menus.MenuItem('e', 'E', group=group, can_view=can_view, placement=0)
        self._assert_name_order(group, ['e', 'a', 'b', 'c', 'd'])

    def test_force_last(self):
        group = menus.MenuGroup('menu', 'Menu')
        menus.MenuItem('e', 'E', group=group, can_view=can_view,
            placement=float('inf'))
        menus.MenuItem('a', 'A', group=group, can_view=can_view)
        menus.MenuItem('b', 'B', group=group, can_view=can_view)
        menus.MenuItem('c', 'C', group=group, can_view=can_view)
        menus.MenuItem('d', 'D', group=group, can_view=can_view)
        self._assert_name_order(group, ['a', 'b', 'c', 'd', 'e'])

    def test_force_multiple_first(self):
        group = menus.MenuGroup('menu', 'Menu')
        menus.MenuItem('a', 'A', group=group, can_view=can_view, placement=0)
        menus.MenuItem('b', 'B', group=group, can_view=can_view)
        menus.MenuItem('c', 'C', group=group, can_view=can_view)
        menus.MenuItem('d', 'D', group=group, can_view=can_view)
        menus.MenuItem('e', 'E', group=group, can_view=can_view, placement=0)
        self._assert_name_order(group, ['a', 'e', 'b', 'c', 'd'])

    def test_force_multiple_last(self):
        group = menus.MenuGroup('menu', 'Menu')
        menus.MenuItem('a', 'A', group=group, can_view=can_view,
            placement=float('inf'))
        menus.MenuItem('b', 'B', group=group, can_view=can_view)
        menus.MenuItem('c', 'C', group=group, can_view=can_view)
        menus.MenuItem('d', 'D', group=group, can_view=can_view)
        menus.MenuItem('e', 'E', group=group, can_view=can_view,
            placement=float('inf'))
        self._assert_name_order(group, ['b', 'c', 'd', 'a', 'e'])

    def test_explicit_placements(self):
        group = menus.MenuGroup('menu', 'Menu')
        menus.MenuItem('a', 'A', group=group, can_view=can_view, placement=5000)
        menus.MenuItem('b', 'B', group=group, can_view=can_view, placement=3000)
        menus.MenuItem('c', 'C', group=group, can_view=can_view, placement=1000)
        menus.MenuItem('d', 'D', group=group, can_view=can_view, placement=4000)
        menus.MenuItem('e', 'E', group=group, can_view=can_view, placement=2000)
        self._assert_name_order(group, ['c', 'e', 'b', 'd', 'a'])
