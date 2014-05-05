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

"""Unit tests for common.tags."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import unittest

from common import utils


class CommonUnitTests(unittest.TestCase):

    # --------------------------- String-to-list.
    def test_list_parsing(self):
        # pylint: disable-msg=protected-access
        self.assertListEqual(['foo'], utils.text_to_list('foo'))
        self.assertListEqual(['foo'], utils.text_to_list(' foo'))
        self.assertListEqual(['foo'], utils.text_to_list('foo '))
        self.assertListEqual(['foo'], utils.text_to_list(' foo '))

        self.assertListEqual(['foo'], utils.text_to_list('foo\t'))
        self.assertListEqual(['foo'], utils.text_to_list('\tfoo'))
        self.assertListEqual(['foo'], utils.text_to_list('\tfoo\t'))

        self.assertListEqual(['foo'], utils.text_to_list('foo '))
        self.assertListEqual(['foo'], utils.text_to_list('    foo'))
        self.assertListEqual(['foo'], utils.text_to_list('    foo     '))

        self.assertListEqual(['foo'], utils.text_to_list('foo\n'))
        self.assertListEqual(['foo'], utils.text_to_list('\nfoo'))
        self.assertListEqual(['foo'], utils.text_to_list('\nfoo\n'))

        self.assertListEqual(['foo'], utils.text_to_list('foo,'))
        self.assertListEqual(['foo'], utils.text_to_list(',foo'))
        self.assertListEqual(['foo'], utils.text_to_list(',foo,'))

        self.assertListEqual(['foo'], utils.text_to_list(' foo ,\n'))
        self.assertListEqual(['foo'], utils.text_to_list('\tfoo,\t\n'))
        self.assertListEqual(['foo'], utils.text_to_list(',foo,\n'))

        self.assertListEqual(['foo'],
                             utils.text_to_list(
                                 '[foo]',
                                 utils.BACKWARD_COMPATIBLE_SPLITTER))
        self.assertListEqual(['foo'],
                             utils.text_to_list(
                                 '[foo],',
                                 utils.BACKWARD_COMPATIBLE_SPLITTER))
        self.assertListEqual(['foo'],
                             utils.text_to_list(
                                 '[foo], ', utils.BACKWARD_COMPATIBLE_SPLITTER))
        self.assertListEqual(['foo'],
                             utils.text_to_list(
                                 '[foo],\n',
                                 utils.BACKWARD_COMPATIBLE_SPLITTER))
        self.assertListEqual(['foo'],
                             utils.text_to_list(
                                 '[foo], \n',
                                 utils.BACKWARD_COMPATIBLE_SPLITTER))

        self.assertListEqual(['foo', 'bar'],
                             utils.text_to_list('foo bar'))
        self.assertListEqual(['foo', 'bar'],
                             utils.text_to_list(' foo bar'))
        self.assertListEqual(['foo', 'bar'],
                             utils.text_to_list('foo bar '))

        self.assertListEqual(['foo', 'bar'],
                             utils.text_to_list('foo\tbar'))
        self.assertListEqual(['foo', 'bar'],
                             utils.text_to_list('\tfoo\tbar'))
        self.assertListEqual(['foo', 'bar'],
                             utils.text_to_list('foo\tbar\t'))

        self.assertListEqual(['foo', 'bar'],
                             utils.text_to_list('foo\nbar\n'))
        self.assertListEqual(['foo', 'bar'],
                             utils.text_to_list('\nfoo\nbar\n'))
        self.assertListEqual(['foo', 'bar'],
                             utils.text_to_list('\n foo\n bar\n'))
        self.assertListEqual(['foo', 'bar'],
                             utils.text_to_list(' \n foo \n bar \n'))

        self.assertListEqual(['foo', 'bar'],
                             utils.text_to_list(
                                 '[foo][bar]',
                                 utils.BACKWARD_COMPATIBLE_SPLITTER))
        self.assertListEqual(['foo', 'bar'],
                             utils.text_to_list(
                                 ' [foo] [bar] ',
                                 utils.BACKWARD_COMPATIBLE_SPLITTER))
        self.assertListEqual(['foo', 'bar'],
                             utils.text_to_list(
                                 '\n[foo]\n[bar]\n',
                                 utils.BACKWARD_COMPATIBLE_SPLITTER))
        self.assertListEqual(['foo', 'bar'],
                             utils.text_to_list(
                                 '\n,[foo],\n[bar],\n',
                                 utils.BACKWARD_COMPATIBLE_SPLITTER))

    def test_none_split(self):
        self.assertListEqual([], utils.text_to_list(None))

    def test_empty_split(self):
        self.assertListEqual([], utils.text_to_list(''))

    def test_all_separators_split(self):
        self.assertListEqual([], utils.text_to_list('  ,,, \t\t\n\t '))

    def test_one_item_split(self):
        self.assertListEqual(['x'], utils.text_to_list('x'))

    def test_join_none(self):
        self.assertEquals('', utils.list_to_text(None))

    def test_join_empty(self):
        self.assertEquals('', utils.list_to_text([]))

    def test_join_one(self):
        self.assertEquals('x', utils.list_to_text(['x']))

    def test_join_two(self):
        self.assertEquals('x y', utils.list_to_text(['x', 'y']))

    def test_join_split(self):
        l = ['a', 'b', 'c']
        self.assertListEqual(l, utils.text_to_list(utils.list_to_text(l)))

    def test_split_join(self):
        text = 'a b c'
        self.assertEquals(text, utils.list_to_text(utils.text_to_list(text)))
