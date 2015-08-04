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

"""Module for embedding Course Builder content in arbitrary HTML pages.

Start your development appserver and visit
http://localhost:8081/modules/embed/v1/demo for documentation with a live demo.
The live demo will 404 in prod.

Embeds are pieces of Course Builder content that live inside iframes inside
static pages. They are valuable because they allow people who aren't running
servers or who otherwise would have static, stateless pages to make use of your
Course Builder content. With some coding, you can embed any piece of content
from Course Builder into any webpage.

This module provides a way for you to author your own embeds, and
it provides the embed system itself, which handles object lifecycle within the
page containing the embed, user authentication, student registration, and
network communication.

To get started writing embeds, see AbstractEmbed. For an example, see
_ExampleEmbed (and _ExampleHandler, which renders the stateful, dynamic
embedded content).

Known gaps:

1. Embeds within a given page must all be from the same CB deployment. This is
   because users would need to authenticate against each deployment, and making
   usable UX for users to sign in to n systems for 1 page is very hard.
2. Auth UX and embed error UX is very rough.
3. Security needs to be strengthened. In particular, cross-frame communication
   should check a nonce in addition to checking event origin.
4. There is no authorization mechanism. Anyone with the right embed HTML snippet
   can embed a piece of content, provided that content is served by App Engine
   to the broader internet.
5. Right now embeds do not generate their snippet HTML and display it in the
   admin editor. This is because currently there are no editable types with
   embeds. We should add one so people have a reference implementation that is
   closer to reality than _ExampleEmbed.
"""

__author__ = [
    'johncox@google.com (John Cox)',
]

import logging
import os
import urllib

import appengine_config
import jinja2

from common import jinja_utils
from common import users
from controllers import utils
from models import config
from models import custom_modules
from models import models
from models import transforms

_BASE_DIR = os.path.join(appengine_config.BUNDLE_ROOT, 'modules/embed')
_EMBED = 'embed'
_MODULES = 'modules'
_BASE_URL = '/%s/%s' % (_MODULES, _EMBED)
_V1 = 'v1'
_BASE_URL_V1 = '%s/%s' % (_BASE_URL, _V1)
_STATIC = 'static'
_STATIC_BASE_URL_V1 = '%s/%s/%s' % (_BASE_URL, _STATIC, _V1)
_STATIC_DIR_V1 = os.path.join(_BASE_DIR, _STATIC, _V1)

_DEMO_URL = _BASE_URL_V1 + '/demo'
_ERRORS_DEMO_URL = _DEMO_URL + '/errors'
_GLOBAL_ERRORS_DEMO_URL = _ERRORS_DEMO_URL + '/global'
_LOCAL_ERRORS_DEMO_URL = _ERRORS_DEMO_URL + '/local'

_DISPATCH_INFIX = '/resource'
_DISPATCH_URL = _BASE_URL_V1 + _DISPATCH_INFIX

_EMBED_CHILD_JS_NAME = 'embed_child.js'
_EMBED_CHILD_JS_URL = '%s/%s' % (_BASE_URL_V1, _EMBED_CHILD_JS_NAME)
_EMBED_CHILD_JS_URL_NAME = 'embed_child_js_url'
_EMBED_CSS_PATH = os.path.join(_STATIC_DIR_V1, 'embed.css')
_EMBED_CSS_URL = '%s/%s' % (_STATIC_BASE_URL_V1, 'embed.css')
_EMBED_LIB_JS_NAME = 'embed_lib.js'
_EMBED_LIB_JS_URL = '%s/%s' % (_BASE_URL_V1, _EMBED_LIB_JS_NAME)
_EMBED_JS_NAME = 'embed.js'
_EMBED_JS_URL = '%s/%s' % (_BASE_URL_V1, _EMBED_JS_NAME)

_COURSE_TITLE_NAME = 'course_title'
_EMAIL_NAME = 'email'
_ENV_NAME = 'env'
_EXAMPLE_NAME = 'example.html'
_EXAMPLE_URL = _BASE_URL + '/example'
_ID_OR_NAME_NAME = 'id_or_name'
_KIND_NAME = 'kind'
_FINISH_AUTH_NAME = 'finish_auth.html'
_FINISH_AUTH_URL = '%s/%s' % (_BASE_URL_V1, 'auth')
_JQUERY_URL = 'https://ajax.googleapis.com/ajax/libs/jquery/2.1.3/jquery.min.js'
_MATERIAL_ICONS_URL = 'https://fonts.googleapis.com/icon?family=Material+Icons'
_ROBOTO_URL = 'http://fonts.googleapis.com/css?family=Roboto'

_LOG = logging.getLogger('modules.embed.embed')

_TEMPLATES_DIR_V1 = os.path.join(_BASE_DIR, 'templates', _V1)
_DEMO_HTML_PATH = os.path.join(_TEMPLATES_DIR_V1, 'demo.html')
_GLOBAL_ERRORS_DEMO_HTML_PATH = os.path.join(
    _TEMPLATES_DIR_V1, 'global_errors.html')
_LOCAL_ERRORS_DEMO_HTML_PATH = os.path.join(
    _TEMPLATES_DIR_V1, 'local_errors.html')
_TEMPLATES_ENV = jinja_utils.create_jinja_environment(
    jinja2.FileSystemLoader([_TEMPLATES_DIR_V1]))


# TODO(johncox): remove after security audit of embed module.
_MODULE_HANDLERS_ENABLED = config.ConfigProperty(
    'gcb_modules_embed_handlers_enabled', bool,
    ('Whether or not to enable the embed module handlers. You must enable this '
     'property to use Course Builder embeds'), default_value=False,
    label='Enable embed module handlers')


class AbstractEnrollmentPolicy(object):
    """Abstract parent for business logic run during resource dispatch."""

    @classmethod
    def apply(cls, unused_handler):
        raise NotImplementedError(
            'You must set a concrete enrollment policy on your embed')


class AutomaticEnrollmentPolicy(AbstractEnrollmentPolicy):
    """Policy that registers the current user in a course automatically."""

    @classmethod
    def apply(cls, handler):
        user = users.get_current_user()
        assert user

        if models.Student.get_enrolled_student_by_user(user):
            return

        models.StudentProfileDAO.add_new_student_for_current_user(
            None, None, handler)


class AbstractEmbed(object):
    """Abstract parent class for Embeds, which define embeddable types.

    See _ExampleEmbed|Handler below for a reference implementation.
    """

    # TODO(johncox): add method for generating HTML embed snippet once we have
    # a concrete implementation backed by an entity with an editor. Snippet
    # format is:
    #
    # <script type='text/javascript' src='http://example.tld/_EMBED_JS_URL'>
    # </script>
    # <cb-embed
    #   src='http://example.tld/namespace/_DISPATCH_URL/kind/id_or_name'>
    # </cb-embed>

    # Enrollment policy we apply before 302ing to the requested resource. Can be
    # used by embed types that require an enrolled student during their render.
    ENROLLMENT_POLICY = AbstractEnrollmentPolicy

    @classmethod
    def dispatch(cls, handler):
        cls.ENROLLMENT_POLICY.apply(handler)
        handler.redirect(cls.get_redirect_url(handler))

    @classmethod
    def get_redirect_url(cls, unused_handler):
        """Given dispatch handler, returns URL of resource we 302 to."""
        raise NotImplementedError


class Registry(object):
    """All known embeds, along with the URL fragments used during dispatch."""

    _bindings = {}

    @classmethod
    def bind(cls, kind, embed_class):
        if kind in cls._bindings:
            raise ValueError(
                'Kind %s is already bound to %s' % (
                    kind, cls._bindings.get(kind)))

        cls._bindings[kind] = embed_class

    @classmethod
    def get(cls, kind):
        """Gets embed_class (or None) by kind string."""
        return cls._bindings.get(kind)


class UrlParser(object):
    """Parses embed kind and id_or_name strings out of URLs.

    URL format is:

        http://example.com/namespace/modules/embed/vn/resource/kind/id_or_name

    for example,

        http://example.com/mycourse/modules/embed/vn/resource/assessment/1

    has kind == assessment and id_or_name == 1. id_or_name is owned by the
    underlying model's key implementation. kind is determined at registration
    time in Registry.bind(); it often maps 1:1 with a db.Model kind, but this is
    not enforced.
    """

    @classmethod
    def get_id_or_name(cls, url):
        parts = cls._get_parts(url)
        return parts[0] if parts else None

    @classmethod
    def get_kind(cls, url):
        parts = cls._get_parts(url)
        return parts[1] if parts else None

    @classmethod
    def _get_parts(cls, url):
        parts = url.split('/')
        if len(parts) != 10:
            return None

        _, _, _, _, modules, embed, version, _, kind, id_or_name = parts

        if (modules != _MODULES) or (embed != _EMBED) or (version != _V1):
            return None

        return tuple([value.strip() for value in [id_or_name, kind]])


class _404IfHandlersDisabledMixin(object):
    """Mixin that 404s unless _MODULE_HANDLERS_ENABLED is True.

    TODO(johncox): remove after security audit of embed module.
    """

    def get(self):
        if not _MODULE_HANDLERS_ENABLED.value:
            self.error(404)
            _LOG.error(
                'You must enable %s to fetch %s.',
                _MODULE_HANDLERS_ENABLED.name, self.request.path)
            return

        self._real_get()

    def _real_get(self):
        pass


class _CssHandler(utils.ApplicationHandler, _404IfHandlersDisabledMixin):

    def _real_get(self):
        self.response.headers['Content-Type'] = 'text/css'
        with open(_EMBED_CSS_PATH) as f:
            self.response.out.write(f.read())


class _AbstractJsHandler(utils.ApplicationHandler, _404IfHandlersDisabledMixin):

    _TEMPLATE_NAME = None

    @classmethod
    def _get_template(cls):
        assert cls._TEMPLATE_NAME is not None

        return _TEMPLATES_ENV.get_template(cls._TEMPLATE_NAME)

    def _get_env(self):
        raise NotImplementedError

    def _real_get(self):
        self._set_headers(self.response.headers)
        context = {}
        env = self._get_env()
        if env:
            context = {_ENV_NAME: transforms.dumps(env)}

        self.response.out.write(self._get_template().render(context))

    def _set_headers(self, headers):
        headers['Content-Type'] = 'text/javascript'

        # Disable caching.
        headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        headers['Expires'] = '0'
        headers['Pragma'] = 'no-cache'


class _EmbedChildJsHandler(_AbstractJsHandler):

    _TEMPLATE_NAME = _EMBED_CHILD_JS_NAME

    def _get_env(self):
        return None


class _EmbedLibJsHandler(_AbstractJsHandler):

    _TEMPLATE_NAME = _EMBED_LIB_JS_NAME

    def _get_absolute_sign_in_url(self):
        return users.create_login_url(
            self.request.host_url + _FINISH_AUTH_URL)

    def _get_env(self):
        return {
            'IN_SESSION': users.get_current_user() is not None,
            'ORIGIN': self.request.host_url,
            'RESOURCE_URI_PREFIX_BOUNDARY': _DISPATCH_INFIX,
            'SIGN_IN_URL': self._get_absolute_sign_in_url(),
        }


class _EmbedJsHandler(_AbstractJsHandler):

    _TEMPLATE_NAME = _EMBED_JS_NAME

    def _get_absolute_embed_css_url(self):
        return self.request.host_url + _EMBED_CSS_URL

    def _get_absolute_embed_lib_js_url(self):
        return self.request.host_url + _EMBED_LIB_JS_URL

    def _get_env(self):
        return {
            'EMBED_CSS_URL': self._get_absolute_embed_css_url(),
            'EMBED_LIB_JS_URL': self._get_absolute_embed_lib_js_url(),
            'JQUERY_URL': _JQUERY_URL,
            'MATERIAL_ICONS_URL': _MATERIAL_ICONS_URL,
            'ROBOTO_URL': _ROBOTO_URL,
        }


class _AbstractDemoHandler(utils.BaseHandler, _404IfHandlersDisabledMixin):

    _TEMPLATE_PATH = None

    @classmethod
    def _active(cls):
        # Turn off in prod; exposed for swap() in tests.
        return not appengine_config.PRODUCTION_MODE

    def _real_get(self):
        if not self._active():
            self.error(404)
            return

        # We're not using Jinja here because we want to illustrate the use case
        # where embeds bring dynamic content into an otherwise-static HTML page.
        with open(self._TEMPLATE_PATH) as f:
            self.response.out.write(f.read())


class _DemoHandler(_AbstractDemoHandler):

    _TEMPLATE_PATH = _DEMO_HTML_PATH


class _GlobalErrorsDemoHandler(_AbstractDemoHandler):

    _TEMPLATE_PATH = _GLOBAL_ERRORS_DEMO_HTML_PATH


class _LocalErrorsDemoHandler(_AbstractDemoHandler):

    _TEMPLATE_PATH = _LOCAL_ERRORS_DEMO_HTML_PATH


class _DispatchHandler(
        utils.BaseHandler, utils.StarRouteHandlerMixin,
        _404IfHandlersDisabledMixin):

    def _real_get(self):
        kind = UrlParser.get_kind(self.request.url)
        id_or_name = UrlParser.get_id_or_name(self.request.url)

        if not (kind and id_or_name):
            _LOG.error(
                'Request malformed; kind: %s, id_or_name: %s', kind,
                id_or_name)
            self.error(404)
            return

        embed = Registry.get(kind)
        if not embed:
            _LOG.error('No embed found for kind: %s', kind)
            self.error(404)
            return

        return embed.dispatch(self)


class _FinishAuthHandler(utils.BaseHandler, _404IfHandlersDisabledMixin):

    def _real_get(self):
        self.response.out.write(
            _TEMPLATES_ENV.get_template(_FINISH_AUTH_NAME).render())


class _ExampleEmbed(AbstractEmbed):
    """Reference implementation of an Embed."""

    ENROLLMENT_POLICY = AutomaticEnrollmentPolicy

    @classmethod
    def get_redirect_url(cls, handler):
        query = {
            _ID_OR_NAME_NAME: UrlParser.get_id_or_name(handler.request.url),
            _KIND_NAME: UrlParser.get_kind(handler.request.url),
        }
        return '%s%s?%s' % (
            handler.get_course().app_context.get_slug(), _EXAMPLE_URL,
            urllib.urlencode(query))


class _ExampleHandler(utils.BaseHandler, _404IfHandlersDisabledMixin):
    """Reference implementation of a handler for an Embed."""

    def _real_get(self):
        template = _TEMPLATES_ENV.get_template(_EXAMPLE_NAME)
        id_or_name = self.request.get(_ID_OR_NAME_NAME)
        kind = self.request.get(_KIND_NAME)

        if not (id_or_name and kind):
            self.error(404)
            return

        user = users.get_current_user()
        if not user:
            self.error(500)
            return

        self.response.out.write(template.render({
            _COURSE_TITLE_NAME: self.get_course().title,
            _EMAIL_NAME: user.email(),
            _EMBED_CHILD_JS_URL_NAME: _EMBED_CHILD_JS_URL,
            _ID_OR_NAME_NAME: id_or_name,
            _KIND_NAME: kind,
        }))


custom_module = None

_GLOBAL_HANDLERS = [
    (_DEMO_URL, _DemoHandler),
    (_EMBED_CHILD_JS_URL, _EmbedChildJsHandler),
    (_EMBED_CSS_URL, _CssHandler),
    (_EMBED_JS_URL, _EmbedJsHandler),
    (_EMBED_LIB_JS_URL, _EmbedLibJsHandler),
    (_FINISH_AUTH_URL, _FinishAuthHandler),
    (_GLOBAL_ERRORS_DEMO_URL, _GlobalErrorsDemoHandler),
    (_LOCAL_ERRORS_DEMO_URL, _LocalErrorsDemoHandler),
]
_NAMESPACED_HANDLERS = [
    (_DISPATCH_URL, _DispatchHandler),
    (_EXAMPLE_URL, _ExampleHandler),
]


def register_module():
    global custom_module  # Per module pattern. pylint: disable=global-statement

    def on_module_enabled():
        Registry.bind('example', _ExampleEmbed)

    custom_module = custom_modules.Module(
        'Embed Module', 'Embed Module', _GLOBAL_HANDLERS, _NAMESPACED_HANDLERS,
        notify_module_enabled=on_module_enabled)

    return custom_module
