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


"""Unit tests for the transforms functions."""

__author__ = 'John Orr (jorr@google.com)'

import unittest

from models import config


class ValidateIntegerRangeTests(unittest.TestCase):

    def _assert_no_error(self, validator, value):
        errors = []
        validator.validate(value, errors)
        self.assertEquals([], errors)

    def _assert_greater_equal_error(self, validator, value):
        errors = []
        validator.validate(value, errors)
        self.assertEquals(['This value must be greater than or equal to %d' %
                           validator._lower_bound_inclusive], errors)

    def _assert_greater_error(self, validator, value):
        errors = []
        validator.validate(value, errors)
        self.assertEquals(['This value must be greater than %d' %
                           validator._lower_bound_exclusive], errors)

    def _assert_less_equal_error(self, validator, value):
        errors = []
        validator.validate(value, errors)
        self.assertEquals(['This value must be less than or equal to %d' %
                           validator._upper_bound_inclusive], errors)
    def _assert_less_error(self, validator, value):
        errors = []
        validator.validate(value, errors)
        self.assertEquals(['This value must be less than %d' %
                           validator._upper_bound_exclusive], errors)

    def test_invalid_bounds(self):
        # Can't set both lower bounds
        with self.assertRaises(ValueError):
            config.ValidateIntegerRange(lower_bound_inclusive=2,
                                        lower_bound_exclusive=2)
        # Can't set both upper bounds
        with self.assertRaises(ValueError):
            config.ValidateIntegerRange(upper_bound_inclusive=2,
                                        upper_bound_exclusive=2)

        # Must set at least one bound.
        with self.assertRaises(ValueError):
            config.ValidateIntegerRange()

        # All combinations of in/ex-clusive upper/lower bound
        config.ValidateIntegerRange(lower_bound_inclusive=3,
                                    upper_bound_inclusive=3)
        with self.assertRaises(ValueError):
            config.ValidateIntegerRange(lower_bound_inclusive=3,
                                        upper_bound_inclusive=2)

        config.ValidateIntegerRange(lower_bound_exclusive=2,
                                    upper_bound_inclusive=3)
        with self.assertRaises(ValueError):
            config.ValidateIntegerRange(lower_bound_exclusive=3,
                                        upper_bound_inclusive=3)

        config.ValidateIntegerRange(lower_bound_inclusive=2,
                                    upper_bound_exclusive=3)
        with self.assertRaises(ValueError):
            config.ValidateIntegerRange(lower_bound_inclusive=3,
                                        upper_bound_exclusive=3)

        config.ValidateIntegerRange(lower_bound_exclusive=2,
                                    upper_bound_exclusive=4)
        with self.assertRaises(ValueError):
            config.ValidateIntegerRange(lower_bound_exclusive=3,
                                        upper_bound_exclusive=4)

        # Bounds must be castable to int.
        with self.assertRaises(ValueError):
            config.ValidateIntegerRange(lower_bound_inclusive='x')
        with self.assertRaises(ValueError):
            config.ValidateIntegerRange(lower_bound_exclusive='x')
        with self.assertRaises(ValueError):
            config.ValidateIntegerRange(upper_bound_inclusive='x')
        with self.assertRaises(ValueError):
            config.ValidateIntegerRange(upper_bound_exclusive='x')

    def test_bounds_checking(self):
        v = config.ValidateIntegerRange(lower_bound_inclusive=-1,
                                        upper_bound_inclusive=1)
        self._assert_greater_equal_error(v, -200000)
        self._assert_greater_equal_error(v, -2)
        self._assert_no_error(v, -1)
        self._assert_no_error(v, 0)
        self._assert_no_error(v, 1)
        self._assert_less_equal_error(v, 2)
        self._assert_less_equal_error(v, 2000000)


        v = config.ValidateIntegerRange(lower_bound_exclusive=-1,
                                        upper_bound_exclusive=1)
        self._assert_greater_error(v, -200000)
        self._assert_greater_error(v, -2)
        self._assert_greater_error(v, -1)
        self._assert_no_error(v, 0)
        self._assert_less_error(v, 1)
        self._assert_less_error(v, 2)
        self._assert_less_error(v, 2000000)

    def test_type_checking(self):
        v = config.ValidateIntegerRange(lower_bound_inclusive=-1,
                                        upper_bound_inclusive=1)
        errors = []
        v.validate('x', errors)
        self.assertEquals(['"x" is not an integer'], errors)
