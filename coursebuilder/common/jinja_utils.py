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

"""Custom Jinja2 filters used in Course Builder."""

__author__ = 'John Orr (jorr@google.com)'

import sys
import traceback
import jinja2
import safe_dom
import tags

from webapp2_extras import i18n

import appengine_config

from common import caching
from common import messages
from models import config
from models import models
from models.counters import PerfCounter


# max size for in-process jinja template cache
MAX_GLOBAL_CACHE_SIZE_BYTES = 8 * 1024 * 1024

# this cache used to be memcache based; now it's in-process
CAN_USE_JINJA2_TEMPLATE_CACHE = config.ConfigProperty(
    'gcb_can_use_jinja2_template_cache', bool,
    messages.SITE_SETTINGS_CACHE_TEMPLATES, default_value=True,
    label='Cache Templates')


def finalize(x):
    """A finalize method which will correctly handle safe_dom elements."""
    if isinstance(x, safe_dom.SafeDom):
        return jinja2.utils.Markup(x.sanitized)
    return x


def js_string_raw(data):
    """Escape a string so that it can be put in a JS quote."""
    if not isinstance(data, basestring):
        return data
    data = data.replace('\\', '\\\\')
    data = data.replace('\r', '\\r')
    data = data.replace('\n', '\\n')
    data = data.replace('\b', '\\b')
    data = data.replace('"', '\\"')
    data = data.replace("'", "\\'")
    data = data.replace('<', '\\u003c')
    data = data.replace('>', '\\u003e')
    data = data.replace('&', '\\u0026')
    return data


def js_string(data):
    return jinja2.utils.Markup(js_string_raw(data))


def get_gcb_tags_filter(handler):

    @appengine_config.timeandlog('get_gcb_tags_filter')
    def gcb_tags(data):
        """Apply GCB custom tags, if enabled. Otherwise pass as if by 'safe'."""
        data = unicode(data)
        if tags.CAN_USE_DYNAMIC_TAGS.value:
            return jinja2.utils.Markup(tags.html_to_safe_dom(data, handler))
        else:
            return jinja2.utils.Markup(data)
    return gcb_tags


class ProcessScopedJinjaCache(caching.ProcessScopedSingleton):
    """This class holds in-process cache of Jinja compiled templates."""

    @classmethod
    def get_cache_len(cls):
        return len(ProcessScopedJinjaCache.instance().cache.items.keys())

    @classmethod
    def get_cache_size(cls):
        return ProcessScopedJinjaCache.instance().cache.total_size

    def __init__(self):
        self.cache = caching.LRUCache(
            max_size_bytes=MAX_GLOBAL_CACHE_SIZE_BYTES)
        self.cache.get_entry_size = self._get_entry_size

    def _get_entry_size(self, key, value):
        return sys.getsizeof(key) + sys.getsizeof(value)


class JinjaBytecodeCache(jinja2.BytecodeCache):
    """Jinja-compatible cache backed by global in-process Jinja cache."""

    def __init__(self, prefix):
        self.prefix = prefix

    def load_bytecode(self, bucket):
        found, _bytes = ProcessScopedJinjaCache.instance().cache.get(
            self.prefix + bucket.key)
        if found and _bytes is not None:
            bucket.bytecode_from_string(_bytes)

    def dump_bytecode(self, bucket):
        _bytes = bucket.bytecode_to_string()
        ProcessScopedJinjaCache.instance().cache.put(
            self.prefix + bucket.key, _bytes)


JINJA_CACHE_LEN = PerfCounter(
    'gcb-models-JinjaBytecodeCache-len',
    'A total number of items in Jinja cache.')
JINJA_CACHE_SIZE_BYTES = PerfCounter(
    'gcb-models-JinjaBytecodeCache-bytes',
    'A total size of items in Jinja cache in bytes.')

JINJA_CACHE_LEN.poll_value = ProcessScopedJinjaCache.get_cache_len
JINJA_CACHE_SIZE_BYTES.poll_value = ProcessScopedJinjaCache.get_cache_size


def create_jinja_environment(loader, locale=None, autoescape=True):
    """Create proper jinja environment."""

    cache = None
    if CAN_USE_JINJA2_TEMPLATE_CACHE.value:
        prefix = 'jinja2:bytecode:%s:/' % models.MemcacheManager.get_namespace()
        cache = JinjaBytecodeCache(prefix)

    jinja_environment = jinja2.Environment(
        autoescape=autoescape, finalize=finalize,
        extensions=['jinja2.ext.i18n'], bytecode_cache=cache, loader=loader)

    jinja_environment.filters['js_string'] = js_string

    if locale:
        i18n.get_i18n().set_locale(locale)
        jinja_environment.install_gettext_translations(i18n)

    old_handle_exception = jinja_environment.handle_exception

    def _handle_exception(exc_info=None, rendered=False, source_hint=None):
        """Handle template exception."""
        traceback.print_exc(exc_info)
        result = old_handle_exception(exc_info, rendered, source_hint)
        return result

    jinja_environment.handle_exception = _handle_exception

    return jinja_environment


def create_and_configure_jinja_environment(
    dirs, autoescape=True, handler=None, default_locale='en_US'):
    """Sets up an environment and gets jinja template."""

    # Defer to avoid circular import.
    from controllers import sites

    locale = None
    app_context = sites.get_course_for_current_request()
    if app_context:
        locale = app_context.get_current_locale()
        if not locale:
            locale = app_context.default_locale
    if not locale:
        locale = default_locale

    jinja_environment = create_jinja_environment(
        jinja2.FileSystemLoader(dirs), locale=locale, autoescape=autoescape)

    jinja_environment.filters['gcb_tags'] = get_gcb_tags_filter(handler)

    return jinja_environment


def get_template(
    template_name, dirs, autoescape=True, handler=None, default_locale='en_US'):
    return create_and_configure_jinja_environment(
        dirs, autoescape, handler, default_locale).get_template(template_name)
