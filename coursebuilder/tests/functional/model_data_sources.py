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

"""Tests exercising the analytics internals (not individual analytics)."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import time

from webtest import app

from common import catch_and_log
from common import crypto
from common import utils as common_utils
from models import data_sources
from models import entities
from models import transforms
from models.data_sources import utils as data_sources_utils

from google.appengine.ext import db


# Data source must be registered before we import actions; actions imports
# 'main', which does all setup and registration in package scope.
class Character(entities.BaseEntity):
    user_id = db.StringProperty(indexed=True)
    goal = db.StringProperty(indexed=True)
    name = db.StringProperty(indexed=False)
    age = db.IntegerProperty(indexed=False)
    rank = db.IntegerProperty(indexed=True)

    _PROPERTY_EXPORT_BLACKLIST = [name]

    def for_export(self, transform_fn):
        model = super(Character, self).for_export(transform_fn)
        model.user_id = transform_fn(self.user_id)
        return model

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        return db.Key.from_path(cls.kind(), transform_fn(db_key.id_or_name()))


class CharacterDataSource(data_sources.AbstractDbTableRestDataSource):

    @classmethod
    def get_name(cls):
        return 'character'

    @classmethod
    def get_entity_class(cls):
        return Character

data_sources.Registry.register(CharacterDataSource)

from tests.functional import actions


class DataSourceTest(actions.TestBase):

    def setUp(self):
        super(DataSourceTest, self).setUp()
        with common_utils.Namespace(self.NAMESPACE):
            self.characters = [
                Character(
                    user_id='001', goal='L', rank=4, age=8, name='Charlie'),
                Character(
                    user_id='002', goal='L', rank=6, age=6, name='Sally'),
                Character(
                    user_id='003', goal='L', rank=0, age=8, name='Lucy'),
                Character(
                    user_id='004', goal='G', rank=2, age=7, name='Linus'),
                Character(
                    user_id='005', goal='G', rank=8, age=8, name='Max'),
                Character(
                    user_id='006', goal='G', rank=1, age=8, name='Patty'),
                Character(
                    user_id='007', goal='R', rank=9, age=35, name='Othmar'),
                Character(
                    user_id='008', goal='R', rank=5, age=2, name='Snoopy'),
                Character(
                    user_id='009', goal='R', rank=7, age=8, name='Pigpen'),
                Character(
                    user_id='010', goal='R', rank=3, age=8, name='Violet'),
                ]
            for c in self.characters:
                c.put()

    def tearDown(self):
        with common_utils.Namespace(self.NAMESPACE):
            db.delete(Character.all(keys_only=True).run())
        super(DataSourceTest, self).tearDown()


class PiiExportTest(DataSourceTest):

    COURSE_NAME = 'test_course'
    ADMIN_EMAIL = 'admin@foo.com'
    NAMESPACE = 'ns_' + COURSE_NAME

    def setUp(self):
        super(PiiExportTest, self).setUp()

        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'The Course')
        self.data_source_context = (
          CharacterDataSource.get_context_class().build_blank_default({}, 20))

    def test_get_non_pii_data(self):
        data = self._get_page_data(0)
        self.assertEquals(10, len(data))
        for item in data:
            self.assertNotIn('name', item)

    def test_get_non_pii_schema(self):
        schema = self._get_schema()
        self.assertNotIn('name', schema)

    def test_get_pii_data(self):
        self.data_source_context.send_uncensored_pii_data = True
        data = self._get_page_data(0)
        self.assertEquals(10, len(data))
        for item in data:
            self.assertIn('name', item)

    def test_get_pii_schema(self):
        self.data_source_context.send_uncensored_pii_data = True
        schema = self._get_schema()
        self.assertIn('name', schema)

    def _get_schema(self):
        log = catch_and_log.CatchAndLog()
        schema = CharacterDataSource.get_schema(
            self.app_context, log, self.data_source_context)
        return schema

    def _get_page_data(self, page_number):
        log = catch_and_log.CatchAndLog()
        schema = self._get_schema()
        data, _ = CharacterDataSource.fetch_values(
            self.app_context, self.data_source_context, schema, log,
            page_number)
        return data

class PaginatedTableTest(DataSourceTest):
    """Verify operation of paginated access to AppEngine DB tables."""

    NAMESPACE = ''

    def test_simple_read(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        response = transforms.loads(self.get('/rest/data/character/items').body)
        self.assertIn('data', response)
        self._verify_data(self.characters, response['data'])

        self.assertIn('schema', response)
        self.assertIn('user_id', response['schema'])
        self.assertIn('age', response['schema'])
        self.assertIn('rank', response['schema'])
        self.assertNotIn('name', response['schema'])  # blacklisted

        self.assertIn('log', response)
        self.assertIn('source_context', response)
        self.assertIn('params', response)
        self.assertEquals([], response['params']['filters'])
        self.assertEquals([], response['params']['orderings'])

    def test_admin_required(self):
        with self.assertRaisesRegexp(app.AppError, 'Bad response: 403'):
            self.get('/rest/data/character/items')

    def test_filtered_read(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        # Single greater-equal filter
        response = transforms.loads(self.get(
            '/rest/data/character/items?filters=rank>=7').body)
        self.assertEquals(3, len(response['data']))
        for character in response['data']:
            self.assertTrue(character['rank'] >= 7)

        # Single less-than filter
        response = transforms.loads(self.get(
            '/rest/data/character/items?filters=rank<7').body)
        self.assertEquals(7, len(response['data']))
        for character in response['data']:
            self.assertTrue(character['rank'] < 7)

        # Multiple filters finding some rows
        response = transforms.loads(self.get(
            '/rest/data/character/items?filters=rank<5&filters=goal=L').body)
        self.assertEquals(2, len(response['data']))
        for character in response['data']:
            self.assertTrue(character['rank'] < 5)
            self.assertTrue(character['goal'] == 'L')

    def test_ordered_read(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        # Single ordering by rank
        response = transforms.loads(self.get(
            '/rest/data/character/items?ordering=rank').body)
        self.assertEquals(10, len(response['data']))
        prev_rank = -1
        for character in response['data']:
            self.assertTrue(character['rank'] > prev_rank)
            prev_rank = character['rank']

        # Single ordering by rank, descending
        response = transforms.loads(self.get(
            '/rest/data/character/items?ordering=-rank').body)
        self.assertEquals(10, len(response['data']))
        prev_rank = 10
        for character in response['data']:
            self.assertTrue(character['rank'] < prev_rank)
            prev_rank = character['rank']

        # Order by goal then rank
        response = transforms.loads(self.get(
            '/rest/data/character/items?ordering=goal&ordering=rank').body)
        self.assertEquals(10, len(response['data']))
        prev_goal = 'A'
        prev_rank = -1
        for character in response['data']:
            self.assertTrue(character['goal'] >= prev_goal)
            if character['goal'] != prev_goal:
                prev_rank = -1
                prev_goal = character['goal']
            else:
                self.assertTrue(character['rank'] > prev_rank)
                prev_rank = character['rank']

    def test_filtered_and_ordered(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        response = transforms.loads(self.get(
            '/rest/data/character/items?filters=rank<7&ordering=rank').body)
        self.assertEquals(7, len(response['data']))
        prev_rank = -1
        for character in response['data']:
            self.assertTrue(character['rank'] > prev_rank)
            self.assertTrue(character['rank'] < 7)

    def test_illegal_filters_and_orderings(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        response = transforms.loads(self.get(
            '/rest/data/character/items?filters=foo').body)
        self._assert_have_critical_error(
            response,
            'Filter specification "foo" is not of the form: <name><op><value>')

        response = transforms.loads(self.get(
            '/rest/data/character/items?filters=foo=9').body)
        self._assert_have_critical_error(
            response,
            'field "foo" which is not in the schema for type "Character"')

        response = transforms.loads(self.get(
            '/rest/data/character/items?filters=rank=kitten').body)
        self._assert_have_critical_error(
            response,
            'invalid literal for int() with base 10: \'kitten\'')

        response = transforms.loads(self.get(
            '/rest/data/character/items?filters=rank<<7').body)
        self._assert_have_critical_error(
            response,
            '"rank<<7" uses an unsupported comparison operation "<<"')

        response = transforms.loads(self.get(
            '/rest/data/character/items?ordering=foo').body)
        self._assert_have_critical_error(
            response,
            'Invalid property name \'foo\'')

        response = transforms.loads(self.get(
            '/rest/data/character/items?ordering=age').body)
        self._assert_have_critical_error(
            response,
            'Property \'age\' is not indexed')

        response = transforms.loads(self.get(
            '/rest/data/character/items?filters=age>5').body)
        self._assert_have_critical_error(
            response,
            'Property \'age\' is not indexed')

        response = transforms.loads(self.get(
            '/rest/data/character/items?filters=rank<7&ordering=goal').body)
        self._assert_have_critical_error(
            response,
            'First ordering property must be the same as inequality filter')

    def _assert_have_critical_error(self, response, expected_message):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        for log in response['log']:
            if (log['level'] == 'critical' and
                expected_message in log['message']):
                return
        self.fail('Expected a critical error containing "%s"' %
                  expected_message)

    def test_pii_encoding(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)
        token = data_sources_utils.generate_data_source_token(
            crypto.XsrfTokenManager)

        response = transforms.loads(self.get('/rest/data/character/items').body)
        for d in response['data']:
            # Ensure that field marked as needing transformation is cleared
            # when we don't pass in an XSRF token used for generating a secret
            # for encrypting.
            self.assertEquals('None', d['user_id'])
            self.assertEquals(str(db.Key.from_path(Character.kind(), 'None')),
                              d['key'])

            # Ensure that field marked for blacklist is suppressed.
            self.assertFalse('name' in d)

        response = transforms.loads(self.get(
            '/rest/data/character/items?data_source_token=' + token).body)

        for d in response['data']:
            # Ensure that field marked as needing transformation is cleared
            # when we don't pass in an XSRF token used for generating a secret
            # for encrypting.
            self.assertIsNotNone(d['user_id'])
            self.assertNotEquals('None', d['key'])

            # Ensure that field marked for blacklist is still suppressed.
            self.assertFalse('name' in d)

    def test_pii_encoding_changes(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        token1 = data_sources_utils.generate_data_source_token(
            crypto.XsrfTokenManager)
        time.sleep(1)  # Legit: XSRF token is time-based, so will change.
        token2 = data_sources_utils.generate_data_source_token(
            crypto.XsrfTokenManager)
        self.assertNotEqual(token1, token2)

        response1 = transforms.loads(self.get(
            '/rest/data/character/items?data_source_token=' + token1).body)
        response2 = transforms.loads(self.get(
            '/rest/data/character/items?data_source_token=' + token2).body)

        for c1, c2 in zip(response1['data'], response2['data']):
            self.assertNotEquals(c1['user_id'], c2['user_id'])
            self.assertNotEquals(c1['key'], c2['key'])

    def test_sequential_pagination(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        response = transforms.loads(self.get(
            '/rest/data/character/items?chunk_size=3&page_number=0').body)
        source_context = response['source_context']
        self.assertEquals(0, response['page_number'])
        self._verify_data(self.characters[:3], response['data'])
        self._assert_have_only_logs(response, [
            'Creating new context for given parameters',
            'fetch page 0 start cursor missing; end cursor missing',
            'fetch page 0 using limit 3',
            'fetch page 0 saving end cursor',
            ])

        response = transforms.loads(self.get(
            '/rest/data/character/items?chunk_size=3&page_number=1'
            '&source_context=%s' % source_context).body)
        source_context = response['source_context']
        self.assertEquals(1, response['page_number'])
        self._verify_data(self.characters[3:6], response['data'])
        self._assert_have_only_logs(response, [
            'Existing context matches parameters; using existing context',
            'fetch page 1 start cursor present; end cursor missing',
            'fetch page 1 using limit 3',
            'fetch page 1 saving end cursor',
            ])

        response = transforms.loads(self.get(
            '/rest/data/character/items?chunk_size=3&page_number=2'
            '&source_context=%s' % source_context).body)
        source_context = response['source_context']
        self.assertEquals(2, response['page_number'])
        self._verify_data(self.characters[6:9], response['data'])
        self._assert_have_only_logs(response, [
            'Existing context matches parameters; using existing context',
            'fetch page 2 start cursor present; end cursor missing',
            'fetch page 2 using limit 3',
            'fetch page 2 saving end cursor',
            ])

        response = transforms.loads(self.get(
            '/rest/data/character/items?chunk_size=3&page_number=3'
            '&source_context=%s' % source_context).body)
        source_context = response['source_context']
        self.assertEquals(3, response['page_number'])
        self._verify_data(self.characters[9:], response['data'])
        self._assert_have_only_logs(response, [
            'Existing context matches parameters; using existing context',
            'fetch page 3 start cursor present; end cursor missing',
            'fetch page 3 using limit 3',
            'fetch page 3 is partial; not saving end cursor',
            ])

    def test_non_present_page_request(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        response = transforms.loads(self.get(
            '/rest/data/character/items?chunk_size=9&page_number=5').body)
        self._verify_data(self.characters[9:], response['data'])
        self.assertEquals(1, response['page_number'])
        self._assert_have_only_logs(response, [
            'Creating new context for given parameters',
            'fetch page 0 start cursor missing; end cursor missing',
            'fetch page 0 using limit 9',
            'fetch page 0 saving end cursor',
            'fetch page 1 start cursor present; end cursor missing',
            'fetch page 1 using limit 9',
            'fetch page 1 is partial; not saving end cursor',
            'Fewer pages available than requested.  Stopping at last page 1',
            ])

    def test_empty_last_page_request(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        response = transforms.loads(self.get(
            '/rest/data/character/items?chunk_size=10&page_number=3').body)
        self._verify_data([], response['data'])
        self.assertEquals(1, response['page_number'])
        self._assert_have_only_logs(response, [
            'Creating new context for given parameters',
            'fetch page 0 start cursor missing; end cursor missing',
            'fetch page 0 using limit 10',
            'fetch page 0 saving end cursor',
            'fetch page 1 start cursor present; end cursor missing',
            'fetch page 1 using limit 10',
            'fetch page 1 is partial; not saving end cursor',
            'Fewer pages available than requested.  Stopping at last page 1',
            ])

    def test_nonsequential_pagination(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        response = transforms.loads(self.get(
            '/rest/data/character/items?chunk_size=3&page_number=2').body)
        source_context = response['source_context']
        self.assertEquals(2, response['page_number'])
        self._verify_data(self.characters[6:9], response['data'])
        self._assert_have_only_logs(response, [
            'Creating new context for given parameters',
            'fetch page 0 start cursor missing; end cursor missing',
            'fetch page 0 using limit 3',
            'fetch page 0 saving end cursor',
            'fetch page 1 start cursor present; end cursor missing',
            'fetch page 1 using limit 3',
            'fetch page 1 saving end cursor',
            'fetch page 2 start cursor present; end cursor missing',
            'fetch page 2 using limit 3',
            'fetch page 2 saving end cursor',
            ])

        response = transforms.loads(self.get(
            '/rest/data/character/items?chunk_size=3&page_number=1'
            '&source_context=%s' % source_context).body)
        source_context = response['source_context']
        self._verify_data(self.characters[3:6], response['data'])
        self._assert_have_only_logs(response, [
            'Existing context matches parameters; using existing context',
            'fetch page 1 start cursor present; end cursor present',
            ])

    def test_pagination_filtering_and_ordering(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        response = transforms.loads(self.get(
            '/rest/data/character/items?filters=rank>=5&ordering=rank'
            '&chunk_size=3&page_number=1').body)
        source_context = response['source_context']
        self.assertEquals(1, response['page_number'])
        self._verify_data([self.characters[4], self.characters[6]],
                          response['data'])
        self._assert_have_only_logs(response, [
            'Creating new context for given parameters',
            'fetch page 0 start cursor missing; end cursor missing',
            'fetch page 0 using limit 3',
            'fetch page 0 saving end cursor',
            'fetch page 1 start cursor present; end cursor missing',
            'fetch page 1 using limit 3',
            'fetch page 1 is partial; not saving end cursor',
            ])

        response = transforms.loads(self.get(
            '/rest/data/character/items?filters=rank>=5&ordering=rank'
            '&chunk_size=3&page_number=0'
            '&source_context=%s' % source_context).body)
        source_context = response['source_context']
        self.assertEquals(0, response['page_number'])
        self._verify_data([self.characters[7], self.characters[1],
                           self.characters[8]], response['data'])
        self._assert_have_only_logs(response, [
            'Existing context matches parameters; using existing context',
            'fetch page 0 start cursor missing; end cursor present',
            ])

    def test_parameters_can_be_omitted_if_using_source_context(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        response = transforms.loads(self.get(
            '/rest/data/character/items?filters=rank>=5&ordering=rank'
            '&chunk_size=3&page_number=1').body)
        source_context = response['source_context']
        self._verify_data([self.characters[4], self.characters[6]],
                          response['data'])

        # This should load identical items, without having to respecify
        # filters, ordering, chunk_size.
        response = transforms.loads(self.get(
            '/rest/data/character/items?page_number=1'
            '&source_context=%s' % source_context).body)
        self.assertEquals(1, response['page_number'])
        self._verify_data([self.characters[4], self.characters[6]],
                          response['data'])
        self._assert_have_only_logs(response, [
            'Continuing use of existing context',
            'fetch page 1 start cursor present; end cursor missing',
            'fetch page 1 using limit 3',
            'fetch page 1 is partial; not saving end cursor',
            ])

    def test_build_default_context(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        response = transforms.loads(self.get('/rest/data/character/items').body)
        self._assert_have_only_logs(response, [
            'Building new default context',
            'fetch page 0 start cursor missing; end cursor missing',
            'fetch page 0 using limit 10000',
            'fetch page 0 is partial; not saving end cursor',
            ])

    def test_change_filtering_invalidates_context(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        response = transforms.loads(self.get(
            '/rest/data/character/items?filters=rank>=5'
            '&chunk_size=3&page_number=0').body)
        source_context = response['source_context']

        response = transforms.loads(self.get(
            '/rest/data/character/items?filters=rank<5'
            '&chunk_size=3&page_number=0'
            '&source_context=%s' % source_context).body)
        source_context = response['source_context']
        self._verify_data([self.characters[2], self.characters[5],
                           self.characters[3]], response['data'])
        self._assert_have_only_logs(response, [
            'Existing context and parameters mismatch; '
            'discarding existing and creating new context.',
            'fetch page 0 start cursor missing; end cursor missing',
            'fetch page 0 using limit 3',
            'fetch page 0 saving end cursor',
            ])

    def test_change_ordering_invalidates_context(self):
        email = 'admin@google.com'
        actions.login(email, is_admin=True)

        response = transforms.loads(self.get(
            '/rest/data/character/items?ordering=rank'
            '&chunk_size=3&page_number=0').body)
        source_context = response['source_context']

        response = transforms.loads(self.get(
            '/rest/data/character/items?ordering=-rank'
            '&chunk_size=3&page_number=0'
            '&source_context=%s' % source_context).body)
        source_context = response['source_context']
        self._verify_data([self.characters[6], self.characters[4],
                           self.characters[8]], response['data'])
        self._assert_have_only_logs(response, [
            'Existing context and parameters mismatch; '
            'discarding existing and creating new context.',
            'fetch page 0 start cursor missing; end cursor missing',
            'fetch page 0 using limit 3',
            'fetch page 0 saving end cursor',
            ])

    def _assert_have_only_logs(self, response, messages):
        for message in messages:
            found_index = -1
            for index, log in enumerate(response['log']):
                if message in log['message']:
                    found_index = index
                    break
            if found_index < 0:
                self.fail('Expected to find message "%s" in logs' % message)
            else:
                del response['log'][found_index]
        if response['log']:
            self.fail('Unexpected message "%s"' % response['log'][0])

    def _verify_data(self, characters, data):
        for c, d in zip(characters, data):
            self.assertEquals(c.rank, d['rank'])
            self.assertEquals(c.age, d['age'])
