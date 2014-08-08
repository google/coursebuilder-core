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

"""LTI module that supports LTI 1.0 - 1.2.

LTI is an open standard for re-using online education tools. IMS Global is the
member organization that owns the standard.

The LTI module enables a Course Builder course to act either as an LTI consumer
(that is, it can use LTI content from other systems) as an LTI provider (that
is, it can make its content available to other systems via LTI), or both.

The LTI standards are available at http://www.imsglobal.org/lti/.

The LTI module is enabled by default. LTI configuration is done on a course-by-
course basis in the Course Options page of the Course Builder admin site. Let's
look at both the consumer and producer feature sets in turn.

To use the consumer feature set, you must populate the 'LTI tools' section of
the Course Options page. This is a YAML text entry field in which you enter tool
definitions. Each tool definition contains a unique name, a description, the LTI
launch URL of the tool's endpoint on the web, a security key, a security secret,
and the LTI version the tool supports. The Launch URL, key, and secret are all
given to you by the LTI tool provider you want to use.

Once you have entered your tool, you can put it in a Course Builder lesson via
the rich text editor. In it, click on the toolbox. Select 'gcb: LTI Tool' from
the dropdown. Then, select the LTI tool you defined earlier to insert it into
your lesson.

On the resulting popup, you can configure the LTI tool. LTI tools are entered
into Course Builder as iframes; here you can set their width and height. You can
also set two specific LTI fields:

  1. Resource Link ID. This uniquely identifies the embed to the tool provider.
     By default we set this to your course's slug; you can override this value
     if your tool provider requires something different.
  2. Extra Fields. This is a YAML text entry field where you can put key-value
     pairs. Each key is a field in the LTI spec; each value is the string you
     wish to transmit for that field. Some providers require fields that are
     optional in the spec or custom to their tool; you can enter those values
     here.

     Course Builder LTI providers require some custom fields. See the provider
     section below for details. This is where you enter those items.

Next, the provider feature set. Each Course Builder course can make its contents
available to other sites on the web via the LTI protocol. To do this, you must
enable the LTI provider for your course. This is a course-level setting;
however, the admin for your Course Builder deployment must enable per-course LTI
provider configuration ('gcb_courses_can_enable_lti_provider' must be True and
active in the admin settings page) in order for your configuration to take
effect.

To configure your course as an LTI provider, go to the Course Options page.
Check the 'Enable LTI Provider' check box. Next, in 'LTI security' you must
enter a key and secret for each consumer you want to be able to use your tool.
Each key and secret must be unique within a course. They are also *extremely
sensitive values* and you must take great care that you never transmit them or
otherwise expose them in ways that could let anyone but your consumer get them.
Otherwise, anybody can impersonate your consumer, which allows them to both
access and mutate your course and student data. You have been warned.

Users of the Course Builder LTI provider must transmit the required fields from
the LTI spec. They must also transmit either 'launch_url', 'secure_launch_url',
or both (in which case 'secure_launch_url' will be used and 'launch_url' will be
ignored). The request must be signed per the LTI spec (meaning HMACed OAuth 1).

Additionally, they must transmit a field named 'custom_cb_resource'. The value
of this field is a string that gives the slug-relative URL of the Course Builder
resource that will be rendered by Course Builder once the LTI launch process is
complete, with the query parameter 'hide-controls=true' appended.

For example, if you want to render
http://example.com/my_course/unit?unit=1&lesson=2, this value is
'unit?unit=1&lesson=2&hide-controls=true'. This will cause unit 1 lesson 2 to
render with no Course Builder chrome, suitable for iframing.

User authentication with LTI is somewhat complicated. If you enable LTI but your
course is not enabled, all LTI requests will fail with HTTP status code 404. If
you enable the course, the LTI endpoints are exposed. If your course is
browsable, users do not need to authenticate in order to see content. If the
course is not browsable, users do need to authenticate. The course pages you
embed are responsible for enforcing enrollment status; the LTI machinery does
not do this for you.

You can force authentication for users who have not yet signed in by passing
'custom_cb_force_login' with a value of 'true' (case insensitive) in your LTI
launch request. This will not force login if the user already has credentials
with that CB course, which avoids the bad UX experience of asking users to
authenticate extra times.

Note that URLs used LTI launch requetss in this system are restricted to
US-ASCII (see https://www.ietf.org/rfc/rfc1738.txt). Unicode URLs are not
supported.
"""

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
from models import config
from models import courses
from models import custom_modules
from modules.lti import fields

from google.appengine.api import app_identity
from google.appengine.api import users


_BASE_URL = '/lti'
_CONFIG_KEY_BROWSABLE = 'browsable'
_CONFIG_KEY_COURSE = 'course'
_CONFIG_KEY_LOCALE = 'locale'
_CONFIG_KEY_LTI1 = 'lti1'
_CONFIG_KEY_PROVIDER_ENABLED = 'provider_enabled'
_CONFIG_KEY_SECURITY = 'security'
_CONFIG_KEY_TOOLS = 'tools'
_EMPTY_STRING = ''
_ERROR_INVALID_VERSION = 'Unsupported version: %s; choices are %s'
_ERROR_KEY_NOT_UNIQUE = 'Key is not unique: %s'
_ERROR_NAME_NOT_UNIQUE = 'Name is not unique: %s'
_ERROR_PARSE_SETTINGS_CONFIG_YAML = 'Cannot parse settings config yaml'
_ERROR_PARSE_TOOLS_CONFIG_YAML = 'Cannot parse tools config yaml'
_ERROR_SECRET_NOT_UNIQUE = 'Secret is not unique: %s'
_LAUNCH_URL = _BASE_URL + '/launch'
_LOGIN_URL = _BASE_URL + '/login'
_REDIRECT_URL = _BASE_URL + '/redirect'
_POST = 'POST'
_VALIDATION_URL = _BASE_URL
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


COURSES_CAN_ENABLE_LTI_PROVIDER = config.ConfigProperty(
    'gcb_courses_can_enable_lti_provider', bool,
    ('Whether or not to allow courses to enable the LTI provider for their '
     'content. If True, courses can enable a setting to allow outside parties '
     'to embed their content via the LTI protocol. If False, the control on '
     'the course page to enable the LTI provider will be present, but it will '
     'have no effect.'), default_value=True)


class Error(Exception):
  """Base error."""


class InvalidVersionError(Exception):
  """Raised when an invalid LTI version is specified."""


def _get_runtime(app_context):
  # For tests.
  return _Runtime(app_context)


def _get_signed_oauth_request(key, secret, parameters, url):
  consumer = oauth.OAuthConsumer(key, secret)
  request = oauth.OAuthRequest.from_consumer_and_token(
      consumer, http_method=_POST, http_url=url, parameters=parameters)
  request.sign_request(oauth.OAuthSignatureMethod_HMAC_SHA1(), consumer, None)
  return request


def _urljoin(*parts):
  """Joins and normalizes URL path parts (not urls, like urlparse.urljoin)."""
  joined = '/'.join(part.strip('/') for part in parts)

  if parts[-1].endswith('/') and not joined.endswith('/'):
    joined += '/'

  if not joined.startswith('/'):
    joined = '/' + joined

  return joined


class _Dispatcher(object):
  """Abstract base class for resource dispatching."""

  @classmethod
  def dispatch(cls, handler, runtime, resource_id):
    """Redirects handler to the resource given by resource_id.

    Args:
      handler: ValidationHandler. The handler to redirect.
      runtime: _Runtime. Current application state.
      resource_id: string. The resource to redirect to.

    Returns:
      None.
    """
    raise NotImplementedError


class _CourseBuilderDispatcher(_Dispatcher):

  @classmethod
  def dispatch(cls, handler, runtime, resource_id):
    # In CB, the resource id is the path component, minus the course slug, that
    # we want to redirect to.
    handler.redirect(_urljoin(runtime.get_base_url(), resource_id))


class _Parser(object):
  """Abstract base for configuration parsers that turn yaml to DTOs."""

  PARSE_ERROR = None

  @classmethod
  def _is_valid_empty_value(cls, raw_value):
    return raw_value is None or raw_value == _EMPTY_STRING

  @classmethod
  def _load_yaml(cls, raw_value, errors):
    try:
      return yaml.safe_load(raw_value)
    except:  # Deliberately broad. pylint: disable-msg=bare-except
      errors.append(cls.PARSE_ERROR)

  @classmethod
  def parse(cls, raw_value, errors):
    """Returns a map of identifier -> DTO; populates errors list of string."""
    raise NotImplementedError


class _ToolConfig(object):
  """DTO for LTI tool configuration."""

  def __init__(self, description, key, name, secret, url, version):
    self.description = description
    self.key = key
    self.name = name
    self.secret = secret
    self.url = url
    self.version = version

  def __eq__(self, other):
    return (
        isinstance(other, _ToolConfig) and
        self.description == other.description and
        self.key == other.key and
        self.name == other.name and
        self.secret == other.secret and
        self.url == other.url and
        self.version == other.version)

  def __str__(self):
    return (
        'LTI Tool Config(%(name)s, LTI %(version)s)' % {
            'name': self.name, 'version': self.version})


class _ToolsParser(_Parser):
  """Parses LTI course-level tools settings into _ToolConfigs."""

  PARSE_ERROR = _ERROR_PARSE_TOOLS_CONFIG_YAML

  @classmethod
  def _get_tool_config(cls, yaml_entry):
    return _ToolConfig(
        yaml_entry[_YAML_ENTRY_DESCRIPTION],
        yaml_entry[_YAML_ENTRY_KEY],
        yaml_entry[_YAML_ENTRY_NAME],
        yaml_entry[_YAML_ENTRY_SECRET],
        yaml_entry[_YAML_ENTRY_URL],
        cls._get_version(yaml_entry[_YAML_ENTRY_VERSION]))

  @classmethod
  def _get_version(cls, version):
    version = str(version)
    if version not in VERSIONS:
      raise InvalidVersionError('Invalid version: ' + version)

    return version

  @classmethod
  def parse(cls, raw_value, errors):
    """Validator for tools yaml; returns {name_str: _ToolConfig}."""
    if cls._is_valid_empty_value(raw_value):
      return {}

    load_errors = []
    loaded = cls._load_yaml(raw_value, load_errors)

    if load_errors:
      errors.extend(load_errors)
      return

    if not isinstance(loaded, list):
      errors.append(cls.PARSE_ERROR)
      return

    name_to_config = {}

    for entry in loaded:
      if not isinstance(entry, dict):
        errors.append(cls.PARSE_ERROR)
        return

      try:
        tool_config = cls._get_tool_config(entry)
      except InvalidVersionError:
        errors.append(
            _ERROR_INVALID_VERSION % (
                entry.get('version'), ', '.join(sorted(VERSIONS))))
        return
      except:
        errors.append(cls.PARSE_ERROR)
        return

      if tool_config.name in name_to_config:
        errors.append(_ERROR_NAME_NOT_UNIQUE % tool_config.name)
        return

      name_to_config[tool_config.name] = tool_config

    return name_to_config


class _SecurityConfig(object):
  """DTO for LTI security information."""

  def __init__(self, key, secret):
    self.key = key
    self.secret = secret

  def __eq__(self, other):
    return (
        isinstance(other, _SecurityConfig) and
        self.key == other.key and self.secret == other.secret)

  def __str__(self):
    # No secret to prevent e.g. logging it in a bad place.
    return 'LTI Security Config(%s)' % self.key


class _SecurityParser(_Parser):
  """Parses security yaml into _SecurityConfigs."""

  PARSE_ERROR = _ERROR_PARSE_SETTINGS_CONFIG_YAML

  @classmethod
  def parse(cls, raw_value, errors):
    """Validator for security yaml; returns {key_unicode: _SecurityConfig}."""
    if cls._is_valid_empty_value(raw_value):
      return {}

    load_errors = []
    loaded = cls._load_yaml(raw_value, load_errors)

    if load_errors:
      errors.extend(load_errors)
      return

    if not isinstance(loaded, list):
      errors.append(cls.PARSE_ERROR)
      return

    key_to_config = {}
    seen_keys = set()
    seen_secrets = set()

    for entry in loaded:
      if not (isinstance(entry, dict) and len(entry.keys()) == 1):
        errors.append(cls.PARSE_ERROR)
        return

      key = entry.keys()[0]
      secret = entry.values()[0]

      if key in seen_keys:
        errors.append(_ERROR_KEY_NOT_UNIQUE % key)
        return

      if secret in seen_secrets:
        errors.append(_ERROR_SECRET_NOT_UNIQUE % secret)
        return

      # Cast key to unicode because later comparisons are done against POSTed
      # data (strings). Do not cast the value in the config.
      key_to_config[unicode(key)] = _SecurityConfig(key, secret)
      seen_keys.add(key)
      seen_secrets.add(secret)

    return key_to_config


class _Runtime(object):
  """Derives runtime configuration state from CB application context."""

  def __init__(self, app_context):
    self._app_context = app_context
    self._environ = self._app_context.get_environ()
    self._security_configs = self._get_security_configs()
    self._tool_configs = self._get_tool_configs()

  def get_base_url(self):
    return self._app_context.get_slug()

  def get_course_browsable(self):
    return self._environ.get(
        _CONFIG_KEY_COURSE, {}).get(_CONFIG_KEY_BROWSABLE, False)

  def get_current_user(self):
    return users.get_current_user()

  def get_default_resource_link_id(self):
    return self._app_context.get_slug().strip('/')

  def get_launch_url(
      self, name, resource_link_id, return_url, extra_fields=None):
    query = {
        'name': name,
        fields.LAUNCH_PRESENTATION_RETURN_URL: return_url,
        fields.RESOURCE_LINK_ID: resource_link_id,
    }

    if extra_fields:
      query['extra_fields'] = extra_fields

    return '%s?%s' % (
        _urljoin(self.get_base_url(), _LAUNCH_URL), urllib.urlencode(query))

  def get_locale(self):
    return self._environ.get(_CONFIG_KEY_COURSE, {}).get(_CONFIG_KEY_LOCALE)

  def get_login_url(self, return_url):
    query = {fields.LAUNCH_PRESENTATION_RETURN_URL: return_url}
    return users.create_login_url(dest_url='%s?%s' % (
        _urljoin(self.get_base_url(), _REDIRECT_URL), urllib.urlencode(query)))

  def get_tool_config(self, name):
    return self._tool_configs.get(name)

  def get_tool_configs(self):
    return self._tool_configs

  def get_security_config(self, key):
    return self._security_configs.get(key)

  def get_user_id(self):
    user = self.get_current_user()

    if not user:
      return None

    return crypto.get_external_user_id(
        app_identity.get_application_id(),
        str(self._app_context.get_namespace_name()), user.email()
    )

  def get_provider_enabled(self):
    return (
        COURSES_CAN_ENABLE_LTI_PROVIDER.value and
        self._get_lti_provider_enabled_for_course())

  def _get_lti_provider_enabled_for_course(self):
    return bool(self._get_yaml_value(_CONFIG_KEY_PROVIDER_ENABLED))

  def _get_configs(self, config_key, parser):
    # This may crash if users have edited config.yaml by hand. Bad config.yaml
    # edits can cause all manner of insanity; we allow errors to percolate up
    # rather than trying to recover so admins discover them fast. The only case
    # we'll handle specially is if the value is sane but fails validation.
    errors = []
    raw_yaml = self._get_yaml_value(config_key)
    configs = parser.parse(raw_yaml, errors)

    if errors:
      raise ValueError('Errors in %s.parse: %s' % (parser.__name__, errors))

    return configs

  def _get_yaml_value(self, config_key):
    return self._environ.get(
        _CONFIG_KEY_COURSE, {}
    ).get(
        _CONFIG_KEY_LTI1, {}
    ).get(
        config_key, _EMPTY_STRING)

  def _get_security_configs(self):
    return self._get_configs(_CONFIG_KEY_SECURITY, _SecurityParser)

  def _get_tool_configs(self):
    return self._get_configs(_CONFIG_KEY_TOOLS, _ToolsParser)


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
      tool_configs = runtime.get_tool_configs()
      names_and_descriptions = sorted([
        (tool.name, tool.description) for tool in tool_configs.values()
      ])
    except:  # Broad on purpose. pylint: disable-msg=bare-except
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
            tool, resource_link_id, handler.request.url,
            extra_fields=extra_fields))
    iframe.set('height', height)
    iframe.set('width', width)

    return iframe


class _BaseHandler(utils.BaseHandler):

  @classmethod
  def _get_request_arg(cls, from_dict, name):
    return urllib.unquote(from_dict.get(name, _EMPTY_STRING))

  def _get_launch_presentation_return_url_or_error(self, from_dict):
    return_url = self._get_request_arg(
        from_dict, fields.LAUNCH_PRESENTATION_RETURN_URL)

    if not return_url:
      _LOG.error(
          'Unable to process LTI request; %s not specified',
          fields.LAUNCH_PRESENTATION_RETURN_URL)
      self.error(400)

    return str(return_url)  # Cast from unicode so it can be used in redirects.


class LaunchHandler(_BaseHandler):

  @classmethod
  def _get_signed_launch_parameters(cls, key, secret, parameters, url):
    request = _get_signed_oauth_request(key, secret, parameters, url)
    return request.parameters

  def get(self):
    runtime = _get_runtime(self.app_context)
    name = self._get_request_arg(self.request, 'name')
    resource_link_id = self._get_request_arg(
        self.request, fields.RESOURCE_LINK_ID)
    return_url = self._get_request_arg(
        self.request, fields.LAUNCH_PRESENTATION_RETURN_URL)
    tool_config = runtime.get_tool_config(name)

    if not (name and tool_config and resource_link_id and return_url):
      _LOG.error(
          'Unable to attempt LTI launch; invalid parameters: name: "%(name)s", '
          'config: "%(config)s", resource_link_id: "%(resource_link_id)s", '
          'launch_presentation_return_url: '
          '"%(launch_presentation_return_url)s"', {
              'name': name, 'config': tool_config,
              fields.LAUNCH_PRESENTATION_RETURN_URL: return_url,
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
        extra_fields, name, return_url, resource_link_id, tool_config.url,
        runtime.get_user_id())
    signed_parameters = self._get_signed_launch_parameters(
        tool_config.key, str(tool_config.secret), unsigned_parameters,
        tool_config.url)
    self.response.out.write(template.render({
      'signed_parameters': signed_parameters,
      'tool_url': tool_config.url,
    }))

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
        self, extra_fields, name, return_url, resource_link_id, url, user_id):
    from_dict = {
        fields.LAUNCH_PRESENTATION_RETURN_URL: return_url,
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


class LoginHandler(_BaseHandler):

  _XSRF_TOKEN_NAME = 'modules-lti-login'
  _XSRF_TOKEN_REQUEST_KEY = 'xsrf_token'

  @classmethod
  def _get_post_url(cls, base_url):
    return _urljoin(base_url, _LOGIN_URL)

  @classmethod
  def _get_xsrf_token(cls):
    return crypto.XsrfTokenManager.create_xsrf_token(cls._XSRF_TOKEN_NAME)

  def get(self):
    self._handle_request('login.html', self._get_get_context)

  def _get_get_context(self, return_url, runtime):
    return {
        'post_url': self._get_post_url(runtime.get_base_url()),
        'return_url_key': fields.LAUNCH_PRESENTATION_RETURN_URL,
        fields.LAUNCH_PRESENTATION_RETURN_URL: return_url,
        'xsrf_token_key': self._XSRF_TOKEN_REQUEST_KEY,
        self._XSRF_TOKEN_REQUEST_KEY: self._get_xsrf_token(),
    }

  def post(self):
    self._handle_request(
        'redirect.html', self._get_post_context,
        validation_fn=self._validate_xsrf_token_or_error)

  def _get_post_context(self, return_url, runtime):
    return {'login_url': runtime.get_login_url(return_url)}

  def _get_template(self, name, locale):
    return jinja_utils.get_template(
        name, [os.path.dirname(__file__)], locale=locale)

  def _handle_request(self, template_name, get_context_fn, validation_fn=None):
    runtime = _get_runtime(self.app_context)
    return_url = self._get_launch_presentation_return_url_or_error(self.request)

    if not return_url:
      return

    if validation_fn and not validation_fn():
      return

    template = self._get_template(template_name, locale=runtime.get_locale())
    context = get_context_fn(return_url, runtime)
    self.response.out.write(template.render(context))

  def _validate_xsrf_token_or_error(self):
    token = self._get_request_arg(
        self.request.POST, self._XSRF_TOKEN_REQUEST_KEY)

    if not (token and crypto.XsrfTokenManager.is_xsrf_token_valid(
            token, self._XSRF_TOKEN_NAME)):
      _LOG.error('Unable to process LTI request; invalid XSRF token')
      self.error(400)
      return

    return token


class RedirectHandler(_BaseHandler):

  def get(self):
    return_url = self._get_launch_presentation_return_url_or_error(self.request)

    if not return_url:
      return

    self.redirect(return_url)


class ValidationHandler(_BaseHandler):

  _DISPATCHER = _CourseBuilderDispatcher
  OAUTH_KEY_FIELD = 'oauth_consumer_key'
  OAUTH_SIGNATURE_FIELD = 'oauth_signature'

  @classmethod
  def _get_expected_signature(cls, key, secret, parameters, url):
    request = _get_signed_oauth_request(key, secret, parameters, url)
    return request.get_parameter(cls.OAUTH_SIGNATURE_FIELD)

  @classmethod
  def _get_login_redirect_url(cls, base_url, return_url):
    return '%s?%s' % (
        _urljoin(base_url, _LOGIN_URL), urllib.urlencode(
            {fields.LAUNCH_PRESENTATION_RETURN_URL: return_url}))

  @classmethod
  def _get_url(cls, post):
    secure_launch_url = post.get(fields.SECURE_LAUNCH_URL)
    return (
        secure_launch_url if secure_launch_url is not None else
        post.get(fields.LAUNCH_URL))

  @classmethod
  def _needs_login(cls, course_browsable, current_user, force_login):
    already_authenticated = bool(current_user)

    if already_authenticated or (course_browsable and not force_login):
      return False

    return True

  def _get_launch_user_id(self):
    return self.request.POST.get(fields.USER_ID)

  def get(self):
    self.error(404)

  def post(self):
    runtime = None

    try:
      runtime = _get_runtime(self.app_context)
    except Exception, e:  # On purpose. pylint: disable-msg=broad-except
      _LOG.error('Unable to get runtime; error was %s', e)
      self.error(500)
      return

    if not runtime.get_provider_enabled():
      _LOG.error(
          'Unable to process LTI request; provider is not enabled')
      self.error(404)
      return

    key = self.request.POST.get(self.OAUTH_KEY_FIELD)
    if not key:
      _LOG.error(
          'Unable to process LTI request; %s missing', self.OAUTH_KEY_FIELD)
      self.error(400)
      return

    security_config = runtime.get_security_config(key)
    if not security_config:
      _LOG.error(
          'Unable to process LTI request; no config found for key %s', key)
      self.error(400)
      return

    launch_url = self._get_url(self.request.POST)
    if not launch_url:
      _LOG.error(
          'Unable to process LTI request; neither %s nor %s specified',
          fields.SECURE_LAUNCH_URL, fields.LAUNCH_URL)
      self.error(400)
      return

    return_url = self._get_launch_presentation_return_url_or_error(
        self.request.POST)
    if not return_url:
      return

    # Treat as module-protected. pylint: disable-msg=protected-access
    missing = fields._get_missing_base(self.request.POST)
    if missing:
      _LOG.error(
          'Unable to process LTI request; missing required fields: %s',
          ', '.join(missing))
      self.error(400)
      return

    cb_resource = self.request.POST.get(fields.CUSTOM_CB_RESOURCE)
    if not cb_resource:
      _LOG.error(
          'Unable to process LTI request; %s not specified',
          fields.CUSTOM_CB_RESOURCE)
      self.error(400)
      return

    request_signature = self.request.POST.get(self.OAUTH_SIGNATURE_FIELD)
    if not request_signature:
      _LOG.error(
          'Unable to process LTI request; %s not specified',
          self.OAUTH_SIGNATURE_FIELD)
      self.error(400)
      return

    try:
      expected_signature = self._get_expected_signature(
          security_config.key, security_config.secret, self.request.POST,
          launch_url)
    except Exception, e:  # Deliberately broad. pylint: disable-msg=broad-except
      _LOG.error(
          'Unable to process LTI request; error calculating signature: %s', e)
      self.error(400)
      return

    if expected_signature != request_signature:
      _LOG.error(
          'Unable to process LTI request; signature mismatch. Ours: %s; '
          'theirs: %s', expected_signature, request_signature)
      self.error(400)
      return

    if self._needs_login(
        runtime.get_course_browsable(), runtime.get_current_user(),
        fields.get_custom_cb_force_login(self.request.POST)):
      self.redirect(
          self._get_login_redirect_url(runtime.get_base_url(), return_url))
      return

    self._DISPATCHER.dispatch(self, runtime, cb_resource)


def _get_provider_enabled_field(unused_course):
  provider_enabled_name = '%s:%s:%s' % (
      _CONFIG_KEY_COURSE, _CONFIG_KEY_LTI1, _CONFIG_KEY_PROVIDER_ENABLED)
  return schema_fields.SchemaField(
      provider_enabled_name, 'Enable LTI Provider', 'boolean',
      description='Whether or not to allow LTI consumers to embed content for '
      'this course. Note that the admin for this Course Builder deployment '
      'must have enabled %s for this setting to take effect, and you will also '
      'need to create a key and secret for each consumer who you want to allow '
      'to embed content from this course (see "LTI security").' % (
          COURSES_CAN_ENABLE_LTI_PROVIDER.name))


def _get_security_field(unused_course):
  security_example = safe_dom.NodeList().append(
      safe_dom.Element('pre').add_text('''
- key1: secret1
- key2: secret2
'''))
  security_field_name = '%s:%s:%s' % (
      _CONFIG_KEY_COURSE, _CONFIG_KEY_LTI1, _CONFIG_KEY_SECURITY)
  return schema_fields.SchemaField(
      security_field_name, 'LTI security', 'text', optional=True,
      description='This is a YAML string containing zero or more key/secret '
      'pairs that allow other systems to make LTI launch requests against this '
      'course in your Course Builder deployment. They are very sensitive and '
      'should be treated with care (for example, emailing them will compromise '
      'the integrity and security of your user data). Each key must be unique '
      'within a course; it is used to uniquely identify the LTI consumer '
      'making a launch request. The secret, which must also be unique within a '
      'course, is used to secure LTI launch requests and ensure that the '
      'consumer is who they say they are. For example:' +
      security_example.sanitized,
      # Treating as module-protected. pylint: disable-msg=protected-access
      validator=_SecurityParser.parse)


def _get_tool_field(unused_course):
  tool_example = safe_dom.NodeList().append(safe_dom.Element('pre').add_text('''
- name: my_tool
  description: My Tool
  url: http://launch.url
  key: 1234
  secret: 5678
  version: 1.2
'''))
  tool_field_name = '%s:%s:%s' % (
      _CONFIG_KEY_COURSE, _CONFIG_KEY_LTI1, _CONFIG_KEY_TOOLS)
  return schema_fields.SchemaField(
      tool_field_name, 'LTI tools', 'text', optional=True,
      description='This is a YAML string containing zero or more '
      'configurations. Each configuration needs to have a "name" (which must '
      'be unique); a "key" and a "secret", both of which come from the LTI '
      'tool provider you are using; a "description", which is displayed in the '
      'editor when selecting your LTI tool; a "url", which is the LTI launch '
      'URL of the tool you are using; and a "version", which is the version of '
      'the LTI specification the tool uses (we support 1.0 - 1.2). For '
      'example:' + tool_example.sanitized,
      # Treating as module-protected. pylint: disable-msg=protected-access
      validator=_ToolsParser.parse)


custom_module = None


def register_module():

  global custom_module

  schema_providers = [
      _get_provider_enabled_field, _get_security_field, _get_tool_field]

  def on_module_enabled():
    courses.Course.OPTIONS_SCHEMA_PROVIDERS.extend(schema_providers)
    tags.Registry.add_tag_binding(LTIToolTag.binding_name, LTIToolTag)

  def on_module_disabled():
    for schema_provider in schema_providers:
      courses.Course.OPTIONS_SCHEMA_PROVIDERS.remove(schema_provider)
    tags.Registry.remove_tag_binding(LTIToolTag.binding_name)

  global_handlers = []
  namespaced_handlers = [
      (_LAUNCH_URL, LaunchHandler),
      (_LOGIN_URL, LoginHandler),
      (_REDIRECT_URL, RedirectHandler),
      (_VALIDATION_URL, ValidationHandler)]
  custom_module = custom_modules.Module(
      'LTI', 'LTI module', global_handlers, namespaced_handlers,
      notify_module_disabled=on_module_disabled,
      notify_module_enabled=on_module_enabled)

  return custom_module
