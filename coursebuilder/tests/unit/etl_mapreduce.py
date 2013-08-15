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

"""Unit tests for mapreduce jobs."""

__author__ = 'juliaoh@google.com (Julia Oh)'

import unittest

from models import transforms
from tools.etl import mapreduce


class HistogramTests(unittest.TestCase):

    def test_get_bin_number(self):
        histogram = mapreduce.Histogram()
        self.assertEquals(histogram._get_bin_number(0), 0)
        self.assertEquals(histogram._get_bin_number(
            mapreduce._BUCKET_SIZE_SECONDS), 0)
        self.assertEquals(histogram._get_bin_number(
            mapreduce._BUCKET_SIZE_SECONDS + 1), 1)
        self.assertEquals(histogram._get_bin_number(
            mapreduce._BUCKET_SIZE_SECONDS * 2), 1)
        self.assertEquals(histogram._get_bin_number(
            (mapreduce._BUCKET_SIZE_SECONDS * 2) + 1), 2)

    def test_get_bin_number_throws_value_error_for_negative_input(self):
        histogram = mapreduce.Histogram()
        self.assertRaises(ValueError, histogram._get_bin_number, -1)

    def test_add(self):
        histogram = mapreduce.Histogram()
        histogram.add(0)
        histogram.add(1)
        histogram.add(31)
        histogram.add(60)
        histogram.add(61)
        histogram.add(123)
        self.assertEquals(histogram._values, {0: 2, 1: 2, 2: 1, 4: 1})

    def test_to_list(self):
        histogram = mapreduce.Histogram()
        histogram.add(0)
        histogram.add(1)
        histogram.add(31)
        histogram.add(60)
        histogram.add(61)
        histogram.add(123)
        self.assertEquals(histogram.to_list(), [2, 1, 0, 1])
        histogram = mapreduce.Histogram()
        histogram.add(121)
        self.assertEquals(histogram.to_list(), [0, 0, 0, 1])

    def test_to_list_returns_empty_list(self):
        histogram = mapreduce.Histogram()
        self.assertEquals(histogram.to_list(), [])


class FlattenJsonTests(unittest.TestCase):

    def test_empty_json_flattened_returns_empty_json(self):
        empty_json = transforms.loads(transforms.dumps({}))
        flattened_json = mapreduce.CSVGenerator._flatten_json(empty_json)
        self.assertEquals(empty_json, flattened_json)

    def test_flat_json_flattened_returns_same_json(self):
        flat_json = transforms.loads(
            transforms.dumps({'foo': 1, 'bar': 2, 'quz': 3}))
        flattened_json = mapreduce.CSVGenerator._flatten_json(flat_json)
        self.assertEquals(flat_json, flattened_json)

    def test_nested_json_flattens_correctly(self):
        dict1 = dict(aaa=111)
        dict2 = dict(aa=11, bb=22, cc=transforms.dumps(dict1))
        dict3 = dict(a=transforms.dumps(dict2), b=2)
        json = transforms.loads(transforms.dumps(dict3))
        flattened_json = mapreduce.CSVGenerator._flatten_json(json)
        result_json = transforms.loads(
            transforms.dumps(
                {'a_aa': '11', 'a_bb': '22', 'b': '2', 'a_cc_aaa': '111'}))
        self.assertEquals(result_json, flattened_json)

