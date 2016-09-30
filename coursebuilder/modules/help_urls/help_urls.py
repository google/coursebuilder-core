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

"""Help URL resolver.

Help URLs are of the form <base>/<version>/<suffix> where

1) <base> is the base help URL, which defaults to _BASE_URL below.
2) <version> is derived from the GCB_PRODUCT_VERSION environment variable. If
   the patch version is zero, it and its leading dot are stripped (so '1.0.0'
   becomes '1.0').
3) <suffix> is a string from topics._ALL, which contains a mapping from a
   topic_id to a URL suffix.

URLs are normalized to contain correct slashes. To set a help URL, edit
topics.py's _ALL variable.

The flow is:

1) Use services.help_urls.make_learn_more_message() to make a message for
   display in the UI.
2) This composes a link with the href set to _REDIRECT_HANDLER_URL, and passes
   the topic_id passed in the call to make_learn_more_message().
3) The redirect handler validates the topic_id, then redirects the user to the
   real help URL, calculated from the value in topics._ALL.

This allows us control over the help URLs, opening up the ability to version
them, or to have different doc sets for different runtime configurations. It
also gathers the URLs into one place (topics._ALL) rather than scattering them
throughout the codebase.
"""

__author__ = [
    'John Cox (johncox@google.com)',
]

import logging
import os

from common import safe_dom
from controllers import utils
from models import custom_modules
from models import services
from modules.help_urls import topics


_BASE_URL = 'https://www.google.com/edu/openonline/course-builder/docs'
# Legacy documentation URL. Fall through to this whenever an item is in
# topics._ALL but its value is topics._DEFAULT.
# TODO(johncox): remove this once topics._ALL is fully populated.
_LOG = logging.getLogger('modules.help_urls.help_urls')
logging.basicConfig()
_REDIRECT_HANDLER_URL = '/modules/help_urls/redirect'


class Service(services.HelpUrls):

    def get(self, topic_id):
        return _TopicRegistry.get_url(topic_id)

    def make_learn_more_message(self, text, topic_id, to_string=True):
        message = safe_dom.assemble_text_message(
            text, '%s?topic_id=%s' % (_REDIRECT_HANDLER_URL, topic_id))
        return str(message) if to_string else message


class _TopicRegistry(object):

    _MAP = {}

    @classmethod
    def build(cls, rows):
        for row in rows:
            key, value = cls._validate(row)
            cls._MAP[key] = value

    @classmethod
    def get_url(cls, topic_id):
        suffix = cls._MAP.get(topic_id)
        if not suffix:
            raise ValueError('No URL suffix found for topic "%s"' % topic_id)

        # Treat as module-protected. pylint: disable=protected-access
        if isinstance(suffix, topics._LegacyUrl):
            return suffix.value

        if suffix.startswith('/'):
            suffix = suffix[1:]

        return '%s/%s/%s' % (_BASE_URL, cls._get_version_infix(), suffix)

    @classmethod
    def _get_version_infix(cls):
        version = os.environ.get('GCB_PRODUCT_VERSION')
        assert version

        parts = version.split('.')
        assert len(parts) == 3
        parts.pop()
        return '.'.join(parts)

    @classmethod
    def _validate(cls, row):
        row_length = len(row)
        if row_length != 2:
            raise ValueError(
                'Topic row must have exactly 2 items; got %s for row "%s"' % (
                    row_length, row))

        key, value = row
        if not key or not value:
            raise ValueError(
                'Topic mapping values must both be set; got "%s" and "%s"' % (
                    key, value))

        if key in cls._MAP:
            raise ValueError(
                'Topic mappings must be unique; "%s" already registered' % key)

        return key, value


class _RedirectHandler(utils.BaseHandler):

    def get(self):
        topic_id = self.request.get('topic_id')
        if not topic_id:
            _LOG.error('No topic_id')
            self.error(400)
            return

        try:
            url = services.help_urls.get(topic_id)
        except ValueError:
            _LOG.error("topic_id '%s' not found", topic_id)
            self.error(400)
            return

        self.redirect(url, normalize=False)


custom_module = None


def register_module():
    # pylint: disable=global-statement
    global custom_module

    def on_module_enabled():
        # Treat as module-protected. pylint: disable=protected-access
        _TopicRegistry.build(topics._ALL)
        services.help_urls = Service()

    global_routes = [
        (_REDIRECT_HANDLER_URL, _RedirectHandler),
    ]
    namespaced_routes = []

    custom_module = custom_modules.Module(
        'Help URL Resolver', 'Creates help URLs for the admin UI',
        global_routes, namespaced_routes,
        notify_module_enabled=on_module_enabled)
    return custom_module
