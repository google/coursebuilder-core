# coding: utf-8
# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Runs all unit tests."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import sys
import unittest
import appengine_config
from common import caching
from common import xcontent
from controllers import sites
from models import config
from models import content
from models import courses
from models import vfs
from modules.review import domain
from tests import suite
from tools import verify
from tools.etl import etl


class ShouldHaveFailedByNow(Exception):
    """Special exception raised when a prior method did not raise."""
    pass


def assert_fails(function):
    """Checks that function invocation raises an exception."""
    try:
        function()
        raise ShouldHaveFailedByNow(
            'Expected to fail: %s().' % function.__name__)
    except ShouldHaveFailedByNow as e:
        raise e
    except Exception:  # pylint: disable=broad-except
        pass


class DeepDictionaryMergeTest(suite.TestBase):

    def test_both_empty_merge(self):
        tgt = {}
        src = {}
        r = courses.deep_dict_merge(tgt, src)
        self.assertEqual({}, r)

    def test_src_empty_merge(self):
        tgt = {'a': {'b': 2}, 'c': None}
        src = {}
        r = courses.deep_dict_merge(tgt, src)
        self.assertEqual(tgt, r)

    def test_tgt_empty_merge(self):
        tgt = {}
        src = {'a': 1}
        r = courses.deep_dict_merge(tgt, src)
        self.assertEqual(src, r)

    def test_non_recursive_merge(self):
        tgt = {'a': 1, 'b': 2, 'd': 4}
        src = {'a': 1, 'b': 22, 'c': 3}
        r = courses.deep_dict_merge(tgt, src)
        e = {'a': 1, 'b': 2, 'c': 3, 'd': 4}
        self.assertEqual(e, r)

    def test_recursive_merge(self):
        tgt = {'a': {'b': 1}}
        src = {'a': 1, 'c': {'d': 4}}
        r = courses.deep_dict_merge(tgt, src)
        e = {'a': {'b': 1}, 'c': {'d': 4}}
        self.assertEqual(e, r)


class EtlRetryTest(suite.TestBase):

    def setUp(self):
        super(EtlRetryTest, self).setUp()
        self.ceiling = 2
        self.retries = 0

    def test_delegates_args_and_returns(self):
        @etl._retry()
        def fn(unused_arg, unused_kwarg=None):
            return 'value'
        self.assertEqual('value', fn('arg', unused_kwarg='unused_kwarg'))

    def test_retries_and_then_succeeds_before_hitting_retry_limit(self):
        @etl._retry()
        def fail_then_succeed():
            self.retries += 1
            if self.retries < self.ceiling:
                raise Exception
        fail_then_succeed()
        self.assertEqual(self.ceiling, self.retries)

    def test_retries_specified_number_of_times_then_throws(self):
        @etl._retry()
        def fail():
            self.retries += 1
            raise Exception
        self.assertRaises(Exception, fail)
        self.assertEqual(etl._RETRIES, self.retries)


class ReviewModuleDomainTests(suite.TestBase):

    def test_review_step_predicates(self):
        step = domain.ReviewStep()

        self.assertFalse(step.is_assigned)
        step._state = domain.REVIEW_STATE_ASSIGNED
        self.assertTrue(step.is_assigned)

        self.assertFalse(step.is_completed)
        step._state = domain.REVIEW_STATE_COMPLETED
        self.assertTrue(step.is_completed)

        self.assertFalse(step.is_expired)
        step._state = domain.REVIEW_STATE_EXPIRED
        self.assertTrue(step.is_expired)


class SwapTestObject(object):

    def __init__(self):
        self.member = 'member_value'

    def method(self):
        return 'method_value'


class SuiteTestCaseTest(suite.TestBase):
    """Sanity check of Suite.TestBase utilities."""

    def setUp(self):
        super(SuiteTestCaseTest, self).setUp()
        self.swap_test_object = SwapTestObject()
        self.old_member = self.swap_test_object.member
        self.old_method = self.swap_test_object.method

    def tearDown(self):
        super(SuiteTestCaseTest, self).tearDown()
        self.assert_unswapped()

    def assert_unswapped(self):
        self.assertIs(self.old_member, self.swap_test_object.member)
        self.assertEqual(self.old_method(), self.swap_test_object.method())

    def test_swaps_against_different_symbols_apply_and_are_unswappable(self):
        self.assertEqual('member_value', self.swap_test_object.member)
        self.assertEqual('method_value', self.swap_test_object.method())
        self.swap(self.swap_test_object, 'member', 'new_member_value')
        self.swap(self.swap_test_object, 'method', lambda: 'new_method_value')
        self.assertEqual('new_member_value', self.swap_test_object.member)
        self.assertEqual('new_method_value', self.swap_test_object.method())
        self._unswap_all()
        self.assert_unswapped()

    def test_tear_down_unswapps_automatically(self):
        # Create a swap to for tearDown to unswap via assert_unswapped.
        self.swap(self.swap_test_object, 'member', 'new_member_value')
        self.assertEqual('new_member_value', self.swap_test_object.member)

    def test_unswap_restores_original_after_multiple_swaps(self):
        self.assertEqual('method_value', self.swap_test_object.method())
        self.swap(self.swap_test_object, 'method', lambda: 'first_swap')
        self.swap(self.swap_test_object, 'method', lambda: 'second_swap')
        self.assertEqual('second_swap', self.swap_test_object.method())
        self._unswap_all()
        self.assert_unswapped()


class InvokeExistingUnitTest(suite.TestBase):
    """Run all units tests declared elsewhere."""

    def test_existing_unit_tests(self):
        """Run all units tests declared elsewhere."""
        vfs.run_all_unit_tests()
        sites.run_all_unit_tests()
        config.run_all_unit_tests()
        verify.run_all_unit_tests()
        content.run_all_unit_tests()
        xcontent.run_all_unit_tests()
        caching.run_all_unit_tests()

    def test_string_encoding(self):
        """Test our understanding of Python string encoding aspects.

        We were quite naive to believe Python solves all string encoding issues
        automatically. That is not completely true and we have to do a lot of
        manual work to get it right. Here we capture some of the patterns.
        """
        original_encoding = sys.getdefaultencoding()

        # Test with 'ascii' default encoding. Note that GAE runs in 'ascii',
        # and not in 'utf-8'. There is no way to override this currently.
        appengine_config.gcb_force_default_encoding('ascii')

        # Note that Python bravely ignores the file encoding declaration
        # 'coding: utf-8' at the top of this file. The intuitive behavior would
        # be to change the default encoding to 'utf-8' for all the code running
        # in the scope of this file.

        # Initialization.
        test_1 = 'My Test Title Мой заголовок теста'
        test_2 = u'My Test Title Мой заголовок теста'

        # Types.
        assert isinstance(test_1, str)
        assert isinstance(test_2, unicode)
        assert test_1 != test_2

        # Conversions.
        assert_fails(lambda: unicode(test_1))
        assert unicode(test_1, 'utf-8')
        assert isinstance(unicode(test_1, 'utf-8'), unicode)
        assert unicode(test_1, 'utf-8') == test_2

        # Expressions.
        assert_fails(lambda: test_1 + test_2)
        assert_fails(lambda: '%s %s' % (test_1, test_2))
        assert_fails(lambda: u'%s %s' % (test_1, test_2))  # Why does it fail?
        assert_fails(lambda: ''.join([test_1, test_2]))
        assert_fails(lambda: u''.join([test_1, test_2]))  # Why does it fail?
        ''.join([unicode(test_1, 'utf-8'), test_2])

        # Test with 'utf-8' default encoding.
        appengine_config.gcb_force_default_encoding('utf-8')

        # Initialization.
        test_1 = 'My Test Title Мой заголовок теста'
        test_2 = u'My Test Title Мой заголовок теста'

        # Types.
        assert isinstance(test_1, str)  # How can this be true?
        assert isinstance(test_2, unicode)
        assert test_1 == test_2  # Note '!=' above, and '==' here. Who knew!!!

        # Conversions.
        assert unicode(test_1) == test_2
        assert unicode(test_1, 'utf-8') == test_2

        # Expressions.
        assert test_1 + test_2
        assert '%s %s' % (test_1, test_2)
        assert u'%s %s' % (test_1, test_2)

        # Clean up.
        appengine_config.gcb_force_default_encoding(original_encoding)

    def test_dict_merge(self):
        real_values = {'foo': 'bar', 'baz': {'alice': 'john'}}
        real_original = dict(real_values.items())
        default_values = {'foo': 'baz', 'baz': {'alice': 'ana', 'bob': 'sue'}}
        default_original = dict(default_values.items())

        # Check merge.
        assert {'foo': 'bar', 'baz': {'bob': 'sue', 'alice': 'john'}} == (
            courses.deep_dict_merge(real_values, default_values))

        # Check originals dicts are intact.
        assert real_original == real_values
        assert default_original == default_values

        # Check merge into an empty dict.
        assert (courses.DEFAULT_COURSE_YAML_DICT ==
                courses.deep_dict_merge(
                    {}, courses.DEFAULT_COURSE_YAML_DICT))

        # Check value does not merge into dictionary.
        real_values = {'foo': 'bar'}
        default_values = {'foo': {'bar': 'baz'}}
        assert {'foo': 'bar'} == (
            courses.deep_dict_merge(real_values, default_values))

        # Test array element.
        real_values = {'foo': [1, 2, 3]}
        default_values = {'baz': [4, 5, 6]}
        assert {'foo': [1, 2, 3], 'baz': [4, 5, 6]} == (
            courses.deep_dict_merge(real_values, default_values))

    def test_app_context_equals(self):
        app_context_a = sites.ApplicationContext(
            'course', '/slug_a', '/', 'ns_a', None)
        app_context_b = sites.ApplicationContext(
            'course', '/slug_a', '/', 'ns_a', None)
        app_context_c = sites.ApplicationContext(
            'course', '/slug_c', '/', 'ns_c', None)
        app_context_ad = sites.ApplicationContext(
            'course', '/slug_d', '/', 'ns_a', None)
        app_context_af = sites.ApplicationContext(
            'course', '/slug_a', '/', 'ns_f', None)

        self.assertFalse(app_context_a is app_context_b)

        self.assertTrue(app_context_a == app_context_b)
        self.assertFalse(app_context_a != app_context_b)

        self.assertTrue(app_context_a != app_context_c)
        self.assertFalse(app_context_a == app_context_c)

        self.assertTrue(app_context_a != app_context_ad)
        self.assertFalse(app_context_a == app_context_ad)

        self.assertTrue(app_context_a != app_context_af)
        self.assertFalse(app_context_a == app_context_af)

        self.assertTrue(app_context_a != None)
        self.assertFalse(app_context_a == None)

    def test_app_context_affinity(self):
        app_context_a = sites.ApplicationContext(
            'course', '/slug_a', '/', 'ns_a', None)
        app_context_b = sites.ApplicationContext(
            'course', '/slug_a', '/', 'ns_a', None)
        app_context_c = sites.ApplicationContext(
            'course', '/slug_c', '/', 'ns_c', None)

        class MySingleton(caching.RequestScopedSingleton):

            def __init__(self, app_context):
                self.app_context = app_context

        # this tests creation of a fresh new singleton for an app_context
        cache_a_1 = MySingleton.instance(app_context_a)
        cache_a_2 = MySingleton.instance(app_context_a)
        self.assertTrue(cache_a_1.app_context is app_context_a)
        self.assertTrue(cache_a_2.app_context is app_context_a)

        # this test finds a singleton using different instance of app_context;
        # this app_context is compatible with the first one via __eq__()
        cache_b_1 = MySingleton.instance(app_context_b)
        cache_b_2 = MySingleton.instance(app_context_b)
        self.assertTrue(cache_b_1.app_context is app_context_a)
        self.assertTrue(cache_b_2.app_context is app_context_a)

        # this raises because singleton is already bound to a specific
        # app_context and an attempt to get the same singleton with another
        # incompatible app_context must fail; we could handle this inside the
        # cache, but the current decision is: this is not supported
        with self.assertRaises(AssertionError):
            MySingleton.instance(app_context_c)

        # clear all singletons and try again; it works now
        MySingleton.clear_all()
        cache_c_1 = MySingleton.instance(app_context_c)
        self.assertTrue(cache_c_1.app_context is app_context_c)


if __name__ == '__main__':
    unittest.TextTestRunner().run(
        unittest.TestLoader().loadTestsFromTestCase(InvokeExistingUnitTest))
