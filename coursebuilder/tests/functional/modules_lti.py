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

"""Functional tests for the LTI module."""

__author__ = [
    'johncox@google.com (John Cox)'
]

import re

from common import crypto
from controllers import sites
from modules.lti import fields
from modules.lti import lti
from modules.oeditor import oeditor
from tests.functional import actions

from google.appengine.api import app_identity
from google.appengine.api import users

# Allow access to code under test. pylint: disable-msg=protected-access


class FieldsTest(actions.TestBase):

  def setUp(self):
    super(FieldsTest, self).setUp()
    self.base = dict(fields._DEFAULTS)
    self.base.update({fields.LAUNCH_URL: fields.LAUNCH_URL + '_value'})

  def test_make_overrides_defaults_from_from_dict(self):
    expected = dict(self.base)
    from_dict = {
        fields.LAUNCH_URL: 'launch_url_override',
        fields.LTI_VERSION: 'lti_version_override',
        fields.RESOURCE_LINK_ID: 'resource_link_id_override',
    }
    expected.update(from_dict)
    self.assertEqual(expected, fields.make(from_dict))

  def test_make_raises_value_error_if_bad_fields(self):
    bad_fields = ['bad1', 'bad2']

    for field in bad_fields:
      self.assertNotIn(field, fields._ALL)

    from_dict = dict(self.base)
    from_dict.update({b: None for b in bad_fields})

    with self.assertRaisesRegexp(
        ValueError, 'bad fields: %s' % ', '.join(bad_fields)):
      fields.make(from_dict)

  def test_make_raises_value_error_if_both_launch_url_keys_present(self):
    from_dict = dict(self.base)
    from_dict.update(
        {fields.LAUNCH_URL: 'foo', fields.SECURE_LAUNCH_URL: 'bar'})

    with self.assertRaisesRegexp(ValueError, 'Cannot pass both'):
      fields.make(from_dict)

  def test_make_raises_value_error_if_neither_launch_url_key_present(self):
    with self.assertRaisesRegexp(ValueError, 'Must pass one of'):
      fields.make({})

  def test_make_raises_value_error_if_missing_fields(self):
    with self.assertRaisesRegexp(
        ValueError, 'Missing required fields: ' + fields.RESOURCE_LINK_ID):
      fields.make(self.base)

  def test_make_sets_missing_defaults_and_includes_valid_passed_fields(self):
    expected = dict(self.base)
    from_dict = {
        fields.LAUNCH_URL: fields.LAUNCH_URL + '_value',
        fields.RESOURCE_LINK_ID: fields.RESOURCE_LINK_ID + '_value',
        'custom_foo': 'custom_foo_value',
    }
    expected.update(from_dict)

    self.assertEqual(expected, fields.make(from_dict))


class LtiWebappTestBase(actions.TestBase):

  def setUp(self):
    super(LtiWebappTestBase, self).setUp()
    self.app_context = sites.get_all_courses()[0]
    self.environ = dict(self.app_context.get_environ())
    self.config = {
        'description': 'config_description',
        'key': 'config_key',
        'name': 'config_name',
        'secret': 'config_secret',
        'url': 'http://config_url',
        'version': lti.VERSION_1_0,
    }

  def get_config_yaml(self):
    return (
        '- description: %(description)s\n'
        '  name: %(name)s\n'
        '  key: %(key)s\n'
        '  secret: %(secret)s\n'
        '  url: %(url)s\n'
        '  version: %(version)s') % self.config

  def set_lti_config(self, config_yaml=None):
    if config_yaml is None:
      config_yaml = self.get_config_yaml()

    self.environ[lti._CONFIG_KEY_COURSE][lti._CONFIG_KEY_LTI1] = config_yaml
    mock_context = actions.MockAppContext(
        environ=self.environ, namespace=self.app_context.get_namespace_name(),
        slug=self.app_context.get_slug())
    self.swap(lti, '_get_runtime', lambda _: lti._Runtime(mock_context))


class LaunchHandlerTest(LtiWebappTestBase):

  def setUp(self):
    super(LaunchHandlerTest, self).setUp()
    self.email = 'user@example.com'
    self.external_userid = crypto.get_external_user_id(
        app_identity.get_application_id(),
        str(self.app_context.get_namespace_name()), self.email)
    self.resource_link_id = 'resource_link_id'
    self.params = {
        'name': self.config['name'],
        fields.RESOURCE_LINK_ID: self.resource_link_id,
    }

  def assert_matches_form_inputs(self, expected_dict, form_inputs):
    for k, v in expected_dict.iteritems():
      self.assertEqual(v, form_inputs[k])

  def assert_base_oauth_form_inputs_look_valid(self, form_inputs):
    url_field = (
        fields.SECURE_LAUNCH_URL if self.config['url'].startswith('https')
        else fields.LAUNCH_URL)

    self.assertEqual('LTI-1p0', form_inputs[fields.LTI_VERSION])
    self.assertEqual(
        'basic-lti-launch-request', form_inputs[fields.LTI_MESSAGE_TYPE])
    self.assertEqual(fields._ROLE_STUDENT, form_inputs[fields.ROLES])
    self.assertEqual(self.config['url'], form_inputs[url_field])
    self.assertEqual(
        self.resource_link_id, form_inputs[fields.RESOURCE_LINK_ID])

  def assert_oauth1_signature_looks_valid(self, form_inputs):
    for oauth_param in [
        'oauth_consumer_key', 'oauth_nonce', 'oauth_signature',
        'oauth_signature_method', 'oauth_timestamp', 'oauth_version']:
      self.assertIn(oauth_param, form_inputs.keys())

    self.assertEqual('HMAC-SHA1', form_inputs['oauth_signature_method'])
    self.assertEqual('1.0', form_inputs['oauth_version'])

  def assert_tool_url_set(self, body):
    self.assertIn("action='%s'" % self.config['url'], body)

  def assert_user_id_equal(self, user_id, form_params):
    self.assertEqual(user_id, form_params[fields.USER_ID])

  def assert_user_not_set(self, form_params):
    self.assertNotIn(fields.USER_ID, form_params.keys())

  def get_form_inputs(self, body):
    return dict(re.findall(
      r"input type='hidden' name='(.+)' value='(.+)'", body))

  def test_get_returns_400_if_context_not_found(self):
    response = self.testapp.get(
        lti._LAUNCH_URL, expect_errors=True, params=self.params)

    self.assertEqual(400, response.status_code)

  def test_get_returns_400_if_name_not_set(self):
    self.set_lti_config()
    self.params.pop('name')
    response = self.testapp.get(
        lti._LAUNCH_URL, expect_errors=True, params=self.params)

    self.assertEqual(400, response.status_code)

  def test_get_returns_400_if_resource_link_id_not_set(self):
    self.set_lti_config()
    self.params.pop(fields.RESOURCE_LINK_ID)
    response = self.testapp.get(
        lti._LAUNCH_URL, expect_errors=True, params=self.params)

    self.assertEqual(400, response.status_code)

  def test_get_when_extra_fields_set_renders_extra_fields_in_form_inputs(self):
    context_id_value = 'context_id_value'
    context_label_value = 'context_label_value'
    extra_fields_yaml = '%s: %s\n%s: %s' % (
        fields.CONTEXT_ID, context_id_value, fields.CONTEXT_LABEL,
        context_label_value)
    self.params.update(
        {'extra_fields': fields._Serializer.dump(extra_fields_yaml)})
    self.set_lti_config()
    response = self.testapp.get(lti._LAUNCH_URL, params=self.params)
    form_inputs = self.get_form_inputs(response.body)

    self.assertEqual(200, response.status_code)
    self.assert_tool_url_set(response.body)
    self.assert_matches_form_inputs(
        {fields.CONTEXT_ID: context_id_value,
         fields.CONTEXT_LABEL: context_label_value}, form_inputs)
    self.assert_base_oauth_form_inputs_look_valid(form_inputs)

  def test_get_when_insecure_launch_url_set(self):
    insecure_url = 'http://something'
    self.config['url'] = insecure_url
    self.set_lti_config()
    response = self.testapp.get(lti._LAUNCH_URL, params=self.params)
    form_inputs = self.get_form_inputs(response.body)

    self.assertEqual(200, response.status_code)
    self.assertEqual(insecure_url, form_inputs[fields.LAUNCH_URL])

  def test_get_when_secure_launch_url_set(self):
    secure_url = 'https://something'
    self.config['url'] = secure_url
    self.set_lti_config()
    response = self.testapp.get(lti._LAUNCH_URL, params=self.params)
    form_inputs = self.get_form_inputs(response.body)

    self.assertEqual(200, response.status_code)
    self.assertEqual(secure_url, form_inputs[fields.SECURE_LAUNCH_URL])

  def test_get_when_user_set_renders_signed_form_inputs(self):
    user = users.User(email=self.email)
    self.swap(users, 'get_current_user', lambda: user)
    self.set_lti_config()
    response = self.testapp.get(lti._LAUNCH_URL, params=self.params)
    form_inputs = self.get_form_inputs(response.body)

    self.assertEqual(200, response.status_code)
    self.assert_tool_url_set(response.body)
    self.assert_oauth1_signature_looks_valid(form_inputs)
    self.assert_base_oauth_form_inputs_look_valid(form_inputs)
    self.assert_user_id_equal(self.external_userid, form_inputs)

  def test_get_when_user_unset_renders_signed_form_inputs(self):
    self.set_lti_config()
    response = self.testapp.get(lti._LAUNCH_URL, params=self.params)
    form_inputs = self.get_form_inputs(response.body)

    self.assertEqual(200, response.status_code)
    self.assert_tool_url_set(response.body)
    self.assert_oauth1_signature_looks_valid(form_inputs)
    self.assert_base_oauth_form_inputs_look_valid(form_inputs)
    self.assert_user_not_set(form_inputs)


class LTIToolTagTest(LtiWebappTestBase):

  # TODO(johncox): turn this into an integration test if/when we write a
  # provider. Right now there's nothing to POST to.

  def assert_is_unavailable_schema(self, schema):
    self.assertEqual(1, len(schema._properties))
    self.assertEqual('unused_id', schema._properties[0].name)

  def test_get_schema_returns_populated_schema_when_config_set_and_valid(self):
    self.set_lti_config()
    handler = oeditor.PopupHandler()
    handler.app_context = self.app_context
    tag = lti.LTIToolTag()
    schema = tag.get_schema(handler)

    self.assertEqual('LTI Tool', schema.title)
    self.assertEqual(5, len(schema._properties))

  def test_get_schema_returns_unavailable_schema_when_config_invalid(self):
    self.set_lti_config(config_yaml='-invalid-')
    handler = oeditor.PopupHandler()
    handler.app_context = self.app_context
    tag = lti.LTIToolTag()

    self.assert_is_unavailable_schema(tag.get_schema(handler))

  def test_get_schema_returns_unavailable_schema_when_config_missing(self):
    self.set_lti_config(config_yaml='')
    handler = oeditor.PopupHandler()
    handler.app_context = self.app_context
    tag = lti.LTIToolTag()

    self.assert_is_unavailable_schema(tag.get_schema(handler))


class SerializerTest(actions.TestBase):

  def test_dump_raises_value_error_if_input_contains_invalid_field(self):
    bad_field = 'bad_field'

    with self.assertRaisesRegexp(ValueError, 'invalid fields: ' + bad_field):
      fields._Serializer.dump('bad_field: value')

  def test_round_trip_of_valid_fields(self):
    valid_field = fields.USER_IMAGE
    value = 'value'
    yaml_string = '%s: %s' % (fields.USER_IMAGE, value)
    self.assertEqual(
        {valid_field: value},
        fields._Serializer.load(fields._Serializer.dump(yaml_string)))
