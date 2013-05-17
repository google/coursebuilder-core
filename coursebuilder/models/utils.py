# Copyright 2012 Google Inc. All Rights Reserved.
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

"""Helper functions to work with various models."""

__author__ = [
    'johncox@google.com (John Cox)',
    'sll@google.com (Sean Lip)',
]

import logging
import transforms

_LOG = logging.getLogger('models.utils')
logging.basicConfig()


class Error(Exception):
    """Base error class."""


class StopMapping(Error):
    """Raised by user's map function to stop execution."""


class QueryMapper(object):
    """Mapper that applies a function to each result of a db.query.

    QueryMapper works with result sets larger than 1000.

    Usage:

        def map_fn(model, named_arg, keyword_arg=None):
            [...]

        query = MyModel.all()
        # We manipulate query, so it cannot be reused after it's fed to
        # QueryMapper.
        mapper = QueryMapper(query)
        mapper.run(map_fn, 'foo', keyword_arg='bar')
    """

    def __init__(self, query, batch_size=20, counter=None, report_every=None):
        """Constructs a new QueryMapper.

        Args:
            query: db.Query. The query to run. Cannot be reused after the
                query mapper's run() method is invoked.
            batch_size: int. Number of results to fetch per batch.
            counter: entities.PerfCounter or None. If given, the counter to
                increment once for every entity retrieved by query.
            report_every: int or None. If specified, every report_every results
                we will log the number of results processed at level info. By
                default we will do this every 10 batches. Set to 0 to disable
                logging.
        """
        if report_every is None:
            report_every = 10 * batch_size

        self._batch_size = batch_size
        self._counter = counter
        self._query = query
        self._report_every = report_every

    def run(self, fn, *fn_args, **fn_kwargs):
        """Runs the query in batches, applying a function to each result.

        Args:
            fn: function. Takes a single query result (either a db.Key or
                db.Model) instance as its first arg, then any number of
                positional and keyword arguments. Called on each result returned
                by the query.
            *fn_args: positional args delegated to fn.
            **fn_kwargs: keyword args delegated to fn.

        Returns:
            Integer. Total number of results processed.
        """
        total_count = 0
        cursor = None

        while True:
            batch_count, cursor = self._handle_batch(
                cursor, fn, *fn_args, **fn_kwargs)

            total_count += batch_count

            if not (batch_count and cursor):
                return total_count

            if self._report_every != 0 and not total_count % self._report_every:
                _LOG.info(
                    'Models processed by %s.%s so far: %s',
                    fn.__module__, fn.func_name, total_count)

    def _handle_batch(self, cursor, fn, *fn_args, **fn_kwargs):
        if cursor:
            self._query.with_cursor(start_cursor=cursor)

        count = 0
        empty = True

        batch = self._query.fetch(limit=self._batch_size)
        if self._counter:
            self._counter.inc(increment=len(batch))

        for result in batch:
            try:
                fn(result, *fn_args, **fn_kwargs)
            except StopMapping:
                return count, None

            count += 1
            empty = False

        cursor = None
        if not empty:
            cursor = self._query.cursor()

        return count, cursor


def set_answer(answers, assessment_name, answer):
    """Stores the answer array for the given student and assessment.

    The caller must call answers.put() to commit.
    This does not do any type-checking on 'answer'; it just stores whatever
    is passed in.

    Args:
        answers: the StudentAnswers entity in which the answer should be stored.
        assessment_name: the name of the assessment.
        answer: an array containing the student's answers.
    """
    if not answers.data:
        score_dict = {}
    else:
        score_dict = transforms.loads(answers.data)
    score_dict[assessment_name] = answer
    answers.data = transforms.dumps(score_dict)


def set_score(student, assessment_name, score):
    """Stores the score for the given student and assessment.

    The caller must call student.put() to commit.
    This does not do any type-checking on 'score'; it just stores whatever
    is passed in.

    Args:
        student: the student whose answer should be stored.
        assessment_name: the name of the assessment.
        score: the student's score.
    """
    if not student.scores:
        score_dict = {}
    else:
        score_dict = transforms.loads(student.scores)
    score_dict[assessment_name] = score
    student.scores = transforms.dumps(score_dict)
