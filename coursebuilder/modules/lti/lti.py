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

"""LTI module that supports LTI 1.0 - 1.2."""

__author__ = [
    'johncox@google.com (John Cox)',
]

import logging
import os
import urllib
from xml import etree

import oauth
import yaml

from common import crypto
from common import jinja_utils
from common import safe_dom
from common import schema_fields
from common import tags
from controllers import utils
from models import custom_modules
from modules.dashboard import course_settings
from modules.lti import fields

from google.appengine.api import app_identity
from google.appengine.api import users


_CONFIG_KEY_COURSE = 'course'
_CONFIG_KEY_LTI1 = 'lti1'
_LAUNCH_URL = '/lti/launch'
_YAML_ENTRY_DESCRIPTION = 'description'
_YAML_ENTRY_KEY = 'key'
_YAML_ENTRY_NAME = 'name'
_YAML_ENTRY_SECRET = 'secret'
_YAML_ENTRY_URL = 'url'
_YAML_ENTRY_VERSION = 'version'

_LOG = logging.getLogger('modules.lti.lti')
logging.basicConfig()

VERSION_1_0 = '1.0'
VERSION_1_1 = '1.1'
VERSION_1_2 = '1.2'
VERSIONS = frozenset([
    VERSION_1_0,
    VERSION_1_1,
    VERSION_1_2,
])


class _Config(object):
  """DTO for LTI configuration."""

  def __init__(self, description, key, name, secret, url, version):
    self.description = description
    self.key = key
    self.name = name
    self.secret = secret
    self.url = url
    self.version = version

  def __eq__(self, other):
    return (
        self.description == other.description and
        self.key == other.key and
        self.name == other.name and
        self.secret == other.secret and
        self.url == other.url and
        self.version == other.version)

  def __str__(self):
    return (
        'LTI Config(%(name)s, LTI %(version)s)' % {
            'name': self.name, 'version': self.version})


class _SettingsParser(object):
  """Parses LTI course-level settings into Configs."""

  @classmethod
  def _get_config(cls, yaml_entry):
    try:
      return _Config(
          yaml_entry[_YAML_ENTRY_DESCRIPTION],
          yaml_entry[_YAML_ENTRY_KEY],
          yaml_entry[_YAML_ENTRY_NAME],
          yaml_entry[_YAML_ENTRY_SECRET],
          yaml_entry[_YAML_ENTRY_URL],
          cls._get_version(yaml_entry[_YAML_ENTRY_VERSION]))
    except Exception, e:
      raise ValueError('LTI config entry malformed; error was "%s"' % str(e))

  @classmethod
  def _get_version(cls, version):
    version = str(version)
    if version not in VERSIONS:
      raise ValueError('Invalid version: ' + version)

    return version

  @classmethod
  def parse(cls, value):
    configs = {}
    raw_entries = []

    try:
      loaded = yaml.safe_load(value)
      raw_entries = loaded if loaded else []
    except Exception, e:
      raise ValueError(
          'Could not parse LTI configuration; error was: %s' % str(e))

    for raw_entry in raw_entries:
      if raw_entry:
        config = cls._get_config(raw_entry)
        configs[config.name] = config

    return configs


class _Runtime(object):
  """Derives LTI runtime configuration state from CB application context."""

  def __init__(self, app_context):
    self._app_context = app_context
    self._environ = self._app_context.get_environ()
    self._configs = self._get_configs()

  def get_config(self, name):
    return self._configs.get(name)

  def get_configs(self):
    return self._configs

  def get_launch_url(self, name, resource_link_id, extra_fields=None):
    query = {'name': name, fields.RESOURCE_LINK_ID: resource_link_id}

    if extra_fields:
      query['extra_fields'] = extra_fields

    return '%s%s?%s' % (
        self._app_context.get_slug(), _LAUNCH_URL, urllib.urlencode(query))

  def get_default_resource_link_id(self):
    return self._app_context.get_slug().strip('/')

  def get_user_id(self):
    user = users.get_current_user()

    if not user:
      return None

    return crypto.get_external_user_id(
        app_identity.get_application_id(),
        str(self._app_context.get_namespace_name()), user.email()
    )

  def _get_configs(self):
    raw_yaml = self._environ.get(
        _CONFIG_KEY_COURSE, {}).get(_CONFIG_KEY_LTI1, '')
    return _SettingsParser.parse(raw_yaml)

  def _get_current_user(self):
    return users.get_current_user()


def _get_runtime(app_context):
  # For tests.
  return _Runtime(app_context)


class LTIToolTag(tags.BaseTag):

  binding_name = 'lti'
  _DEFAULT_HEIGHT = '600'
  _DEFAULT_WIDTH = '600'

  @classmethod
  def name(cls):
    return 'LTI Tool'

  @classmethod
  def vendor(cls):
    return 'gcb'

  def get_icon_url(self):
      return '/extensions/tags/gcb/resources/iframe.png'

  def get_schema(self, handler):
    runtime = None
    names_and_descriptions = None

    # Treat as module-protected. pylint: disable-msg=protected-access
    try:
      runtime = _get_runtime(handler.app_context)
      names_and_descriptions = sorted([
        (tool.name, tool.description) for tool in runtime.get_configs().values()
      ])
    except ValueError:
      pass

    if not names_and_descriptions:
      return self.unavailable_schema(
          'No LTI tools available. Either they have not been configured, or '
          'the configuration contains syntax errors.')

    reg = schema_fields.FieldRegistry(self.name())
    reg.add_property(schema_fields.SchemaField(
        'tool', 'Tool', 'string', optional=True,
        select_data=names_and_descriptions, description='The LTI tool you '
        'wish to embed. If you do not see your tool, you first need to '
        'configure the LTI tools for your course.'))
    reg.add_property(schema_fields.SchemaField(
        fields.RESOURCE_LINK_ID, 'Resource Link ID', 'string',
        extra_schema_dict_values={
            'value': runtime.get_default_resource_link_id()},
        description='The resource_link_id you wish to transmit to the LTI '
        'provider. Different providers attach different meanings to this '
        'value; consult your LTI provider to determine the correct value here. '
        'By default, we use the course URL slug.'))
    reg.add_property(schema_fields.SchemaField(
        'width', 'Width', 'integer',
        extra_schema_dict_values={'value': self._DEFAULT_WIDTH},
        description='The width of the rendered LTI tool, in pixels'))
    reg.add_property(schema_fields.SchemaField(
        'height', 'Height', 'integer',
        extra_schema_dict_values={'value': self._DEFAULT_HEIGHT},
        description='The height of the rendered LTI tool, in pixels'))
    reg.add_property(schema_fields.SchemaField(
        'extra_fields', 'Extra Fields', 'text', optional=True,
        description='YAML of optional fields to transmit in the LTI launch '
        'request. See the LTI spec at http://www.imsglobal.org/lti/index.html '
        'for the lists of supported fields.'))

    return reg

  def render(self, node, handler):
    runtime = _get_runtime(handler.app_context)
    height = node.attrib.get('height') or self._DEFAULT_HEIGHT
    width = node.attrib.get('width') or self._DEFAULT_WIDTH
    resource_link_id = node.attrib.get(fields.RESOURCE_LINK_ID)
    tool = node.attrib.get('tool')
    extra_fields = node.attrib.get('extra_fields')

    if extra_fields:
      # Treating as module-protected: pylint: disable-msg=protected-access
      extra_fields = fields._Serializer.dump(extra_fields)

    iframe = etree.cElementTree.XML('<iframe style="border: 0;"></iframe>')
    iframe.set('name', 'gcb-lti-iframe-' + tool)
    iframe.set(
        'src',
        runtime.get_launch_url(
            tool, resource_link_id, extra_fields=extra_fields))
    iframe.set('height', height)
    iframe.set('width', width)

    return iframe


class LaunchHandler(utils.BaseHandler):

  def get(self):
    runtime = _get_runtime(self.app_context)
    name = urllib.unquote(self.request.get('name', ''))
    resource_link_id = urllib.unquote(
        self.request.get(fields.RESOURCE_LINK_ID, ''))
    config = runtime.get_config(name)

    if not (name and config and resource_link_id):
      _LOG.error(
          'Unable to attempt LTI launch; invalid parameters: name: "%(name)s", '
          'config: "%(config)s", resource_link_id: "%(resource_link_id)s"', {
              'name': name, 'config': config,
              fields.RESOURCE_LINK_ID: resource_link_id})
      self.error(400)
      return

    template = jinja_utils.get_template(
        'launch.html', [os.path.dirname(__file__)])

    extra_fields = self.request.get('extra_fields')
    if extra_fields:
      # Treating as module-protected. pylint: disable-msg=protected-access
      extra_fields = fields._Serializer.load(extra_fields)

    # We use a *very* minimal set of common args. Other static values can be
    # passed on an as-needed basis via the tag UI. If you need dynamic values,
    # you can override _get_custom_unsigned_launch_parameters below.
    unsigned_parameters = self._get_unsigned_launch_parameters(
        extra_fields, name, resource_link_id, config.url, runtime.get_user_id())
    signed_parameters = self._get_signed_launch_parameters(
        config.key, str(config.secret), unsigned_parameters, config.url)
    self.response.out.write(template.render({
      'signed_parameters': signed_parameters,
      'tool_url': config.url,
    }))

  def _get_signed_launch_parameters(self, key, secret, parameters, url):
    consumer = oauth.OAuthConsumer(key, secret)
    request = oauth.OAuthRequest.from_consumer_and_token(
        consumer, http_method='POST', http_url=url,
        parameters=parameters)
    request.sign_request(oauth.OAuthSignatureMethod_HMAC_SHA1(), consumer, None)
    return request.parameters

  def get_custom_unsigned_launch_parameters(self, from_dict, name):
    """Hook for client customization.

    If you want to merge parameters onto the launch request that are dynamic
    (and consequently cannot be entered statically by the admin UI), you can
    calculate them here and merge them onto from_dict.

    Args:
      from_dict: dict of string -> value. The LTI launch request payload that we
          are calculating, modified in place.
      name: string. The name of the LTI tool configuration we're processing a
          request for.
    """
    pass

  def _get_unsigned_launch_parameters(
        self, extra_fields, name, resource_link_id, url, user_id):
    from_dict = {
        fields.RESOURCE_LINK_ID: resource_link_id,
        # No support for other roles in CB yet.
        # Treating as module-protected. pylint: disable-msg=protected-access
        fields.ROLES: fields._ROLE_STUDENT,
        self._get_url_field(url): url,
    }

    if extra_fields:
      from_dict.update(extra_fields)

    if user_id:
      from_dict.update({fields.USER_ID: user_id})

    self.get_custom_unsigned_launch_parameters(from_dict, name)
    return fields.make(from_dict)

  def _get_url_field(self, url):
    return (
        fields.SECURE_LAUNCH_URL if url.startswith('https')
        else fields.LAUNCH_URL)


custom_module = None


def register_module():

  global custom_module

  def get_criteria_specification_schema(unused_course):
    example = safe_dom.NodeList().append(safe_dom.Element('pre').add_text('''
    - name: my_tool
    description: My Tool
    url: http://launch.url
    key: 1234
    secret: 5678
    version: 1.2
    '''))
    lti_field_name = '%s:%s' % (_CONFIG_KEY_COURSE, _CONFIG_KEY_LTI1)
    return schema_fields.SchemaField(
        lti_field_name, 'LTI tools', 'text', optional=True,
        description='LTI tools. This is a YAML string containing zero or more '
        'configurations. Each configuration needs to have a "name" (which must '
        'be unique); a "key" and a "secret", both of which come from the LTI '
        'tool provider you are using; a "description", which is displayed in '
        'the editor when selecting your LTI tool; a "url", which is the LTI '
        'launch URL of the tool you are using; and a "version", which is the '
        'version of the LTI specification the tool uses '
        '(we support 1.0 - 1.2). For example:' + example.sanitized)

  def on_module_enabled():
    course_settings.EXTRA_COURSE_OPTIONS_SCHEMA_PROVIDERS.append(
        get_criteria_specification_schema)
    tags.Registry.add_tag_binding(LTIToolTag.binding_name, LTIToolTag)

  def on_module_disabled():
    course_settings.EXTRA_COURSE_OPTIONS_SCHEMA_PROVIDERS.remove(
         get_criteria_specification_schema)
    tags.Registry.remove_tag_binding(LTIToolTag.binding_name)

  global_handlers = []
  namespaced_handlers = [
      (_LAUNCH_URL, LaunchHandler)]
  custom_module = custom_modules.Module(
      'LTI', 'LTI module', global_handlers, namespaced_handlers,
      notify_module_disabled=on_module_disabled,
      notify_module_enabled=on_module_enabled)

  return custom_module
