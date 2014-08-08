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

"""LTI request field definitions.

Provides the field set of LTI 1.2. See spec at
http://www.imsglobal.org/lti/ltiv1p2pd/ltiIMGv1p2pd.html.
"""

__author__ = [
    'johncox@google.com (John Cox)',
]

import base64
import yaml


CONTEXT_ID = 'context_id'
CONTEXT_LABEL = 'context_label'
CONTEXT_TITLE = 'context_title'
CONTEXT_TYPE = 'context_type'
LAUNCH_PRESENTATION_CSS_URL = 'launch_presentation_css_url'
LAUNCH_PRESENTATION_DOCUMENT_TARGET = 'launch_presentation_document_target'
LAUNCH_PRESENTATION_HEIGHT = 'launch_presentation_height'
LAUNCH_PRESENTATION_LOCALE = 'launch_presentation_locale'
LAUNCH_PRESENTATION_RETURN_URL = 'launch_presentation_return_url'
LAUNCH_PRESENTATION_WIDTH = 'launch_presentation_width'
LAUNCH_URL = 'launch_url'
LIS_PERSON_CONTACT_EMAIL_PRIMARY = 'lis_person_contact_email_primary'
LIS_PERSON_NAME_FAMILY = 'lis_person_name_family'
LIS_PERSON_NAME_FULL = 'lis_person_name_full'
LIS_PERSON_NAME_GIVEN = 'lis_person_name_given'
LTI_MESSAGE_TYPE = 'lti_message_type'
LTI_VERSION = 'lti_version'
RESOURCE_LINK_DESCRIPTION = 'resource_link_description'
RESOURCE_LINK_ID = 'resource_link_id'
RESOURCE_LINK_TITLE = 'resource_link_title'
ROLE_SCOPE_MENTOR = 'role_scope_mentor'
ROLES = 'roles'
SECURE_LAUNCH_URL = 'secure_launch_url'
TOOL_CONSUMER_INFO_PRODUCT_FAMILY_CODE = (
    'tool_consumer_info_product_family_code')
TOOL_CONSUMER_INFO_VERSION = 'tool_consumer_info_version'
TOOL_CONSUMER_INSTANCE_CONTACT_EMAIL = 'tool_consumer_instance_contact_email'
TOOL_CONSUMER_INSTANCE_DESCRIPTION = 'tool_consumer_instance_description'
TOOL_CONSUMER_INSTANCE_GUID = 'tool_consumer_instance_guid'
TOOL_CONSUMER_INSTANCE_NAME = 'tool_consumer_instance_name'
TOOL_CONSUMER_INSTANCE_URL = 'tool_consumer_instance_url'
USER_ID = 'user_id'
USER_IMAGE = 'user_image'

_ALL = frozenset([
    CONTEXT_ID,
    CONTEXT_LABEL,
    CONTEXT_TITLE,
    CONTEXT_TYPE,
    LAUNCH_PRESENTATION_CSS_URL,
    LAUNCH_PRESENTATION_DOCUMENT_TARGET,
    LAUNCH_PRESENTATION_HEIGHT,
    LAUNCH_PRESENTATION_LOCALE,
    LAUNCH_PRESENTATION_RETURN_URL,
    LAUNCH_PRESENTATION_WIDTH,
    LAUNCH_URL,
    LIS_PERSON_CONTACT_EMAIL_PRIMARY,
    LIS_PERSON_NAME_FAMILY,
    LIS_PERSON_NAME_FULL,
    LIS_PERSON_NAME_GIVEN,
    LTI_MESSAGE_TYPE,
    LTI_VERSION,
    RESOURCE_LINK_DESCRIPTION,
    RESOURCE_LINK_ID,
    RESOURCE_LINK_TITLE,
    ROLE_SCOPE_MENTOR,
    ROLES,
    SECURE_LAUNCH_URL,
    TOOL_CONSUMER_INFO_PRODUCT_FAMILY_CODE,
    TOOL_CONSUMER_INFO_VERSION,
    TOOL_CONSUMER_INSTANCE_CONTACT_EMAIL,
    TOOL_CONSUMER_INSTANCE_DESCRIPTION,
    TOOL_CONSUMER_INSTANCE_GUID,
    TOOL_CONSUMER_INSTANCE_NAME,
    TOOL_CONSUMER_INSTANCE_URL,
    USER_ID,
    USER_IMAGE,
])
_ROLE_STUDENT = 'student'
_REQUIRED = frozenset([
    LTI_MESSAGE_TYPE,
    LTI_VERSION,
    RESOURCE_LINK_ID,
])  # One of LAUNCH_URL, SECURE_LAUNCH_URL must also be set; enforced below.
_CUSTOM_PREFIX = 'custom_'
_DEFAULTS = {
    LTI_MESSAGE_TYPE: 'basic-lti-launch-request',
    LTI_VERSION: 'LTI-1p0'
}


def _check_launch_url(from_dict):
  has_launch_url = from_dict.has_key(LAUNCH_URL)
  has_secure_launch_url = from_dict.has_key(SECURE_LAUNCH_URL)

  if has_launch_url and has_secure_launch_url:
    raise ValueError(
        'Cannot pass both %s and %s' % (LAUNCH_URL, SECURE_LAUNCH_URL))

  if not (has_launch_url or has_secure_launch_url):
    raise ValueError(
        'Must pass one of %s or %s' % (LAUNCH_URL, SECURE_LAUNCH_URL))


def _is_valid(name):
  return name in _ALL or name.startswith(_CUSTOM_PREFIX)


def _get_missing_base(from_dict):
  """Gets the missing base required LTI fields from the given dict.

  Base fields are statically enumerated and do not include fields like
  LAUNCH_URL or SECURE_LAUNCH_URL, which must be checked dynamically since one
  or the other is required.

  Args:
    from_dict: dict of filed name string to value. The fields to process.

  Returns:
    List of string. The missing field names in lexicographical order. May be
    empty.
  """
  return sorted(set(_REQUIRED) - set(from_dict.keys()))


def make(from_dict):
  """Makes a dict of LTI post payload data from the given dict.

  from_dict must contain at least RESOURCE_LINK_ID.

  Args:
    from_dict: dict of field name string to value. The fields to process.

  Returns:
    Dict. An map of field name string to field value. Must be signed before
    transport to an LTI provider.

  Raises:
    ValueError: if any keys in from_dict are not valid LTI fields; the result is
    missing any required LTI fields because they were not given in from_dict; or
    the from_dict contains both LAUNCH_URL and SECURE_LAUNCH_URL.
  """
  bad_fields = []
  missing = set(_REQUIRED) - set(_DEFAULTS)
  to_dict = dict(_DEFAULTS)
  _check_launch_url(from_dict)

  for k, v in from_dict.iteritems():
    missing.discard(k)
    if not _is_valid(k):
      bad_fields.append(k)
    else:
      to_dict[k] = v

  if bad_fields:
    raise ValueError(
        'Cannot include bad fields: %s' % ', '.join(
            [b for b in sorted(bad_fields)]))

  if missing:
    raise ValueError(
        'Missing required fields: %s' % ', '.join([m for m in sorted(missing)]))

  return to_dict


class _Serializer(object):
  """Serializes fields for wire transport between CB pages."""

  @classmethod
  def dump(cls, fields_str):
    fields_dict = yaml.safe_load(fields_str)

    bad_fields = []

    for field_name in fields_dict:
      if not _is_valid(field_name):
        bad_fields.append(field_name)

    if bad_fields:
      raise ValueError(
          'Cannot serialize invalid fields: %s' % ', '.join(bad_fields))

    return base64.b64encode(fields_str)

  @classmethod
  def load(cls, serialized):
    return yaml.safe_load(base64.b64decode(serialized))
