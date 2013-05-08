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

"""Functional tests for models/utils.py."""

__author__ = [
    'johncox@google.com (John Cox)',
]

from models import counters
from models import utils
from tests.functional import actions
from google.appengine.ext import db


class Model(db.Model):
    create_date = db.DateTimeProperty(auto_now=True, indexed=True)
    number = db.IntegerProperty(indexed=True)
    string = db.StringProperty()


def process(model, number, string=None):
    model.number = number
    model.string = string
    db.put(model)


def stop_mapping_at_5(model):
    if model.number == 5:
        raise utils.StopMapping


class QueryMapperTest(actions.TestBase):
    """Tests for utils.QueryMapper."""

    def test_raising_stop_mapping_stops_execution(self):
        db.put([Model(number=x) for x in xrange(11)])
        num_processed = utils.QueryMapper(
            Model.all().order('number')).run(stop_mapping_at_5)

        self.assertEqual(5, num_processed)

    def test_run_processes_empty_result_set(self):
        self.assertEqual(
            0, utils.QueryMapper(Model.all()).run(process, 1, string='foo'))

    def test_run_processes_one_entity(self):
        """Tests that we can process < batch_size results."""
        Model().put()
        num_processed = utils.QueryMapper(
            Model.all()).run(process, 1, string='foo')
        model = Model.all().get()

        self.assertEqual(1, num_processed)
        self.assertEqual(1, model.number)
        self.assertEqual('foo', model.string)

    def test_run_process_more_than_1000_entities(self):
        """Tests we can process more entities than the old limit of 1k."""
        counter = counters.PerfCounter(
            'test-run-process-more-than-1000-entities-counter',
            'counter for testing increment by QueryMapper')
        db.put([Model() for _ in xrange(1001)])
        # Also pass custom args to QueryMapper ctor.
        num_processed = utils.QueryMapper(
            Model.all(), batch_size=50, counter=counter, report_every=0
        ).run(process, 1, string='foo')
        last_written = Model.all().order('-create_date').get()

        self.assertEqual(1001, counter.value)
        self.assertEqual(1001, num_processed)
        self.assertEqual(1, last_written.number)
        self.assertEqual('foo', last_written.string)
