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
To demo embed with child courses, visit
http://localhost:8081/modules/embed/v1/demo/child. Both demos will 404 in prod.

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
embedded content). Handlers for your embedded content extend BaseHandler.

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
from common import tags
from common import users
from common import utils as common_utils
from controllers import sites
from controllers import utils as controllers_utils
from models import courses
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

_CHILD_COURSES_NAME = 'child_courses'
_COURSE_NAME = 'course'
_COURSE_TITLE_NAME = 'course_title'
_DEFAULT_LOCALE = 'en_US'
_DEMO_URL = _BASE_URL_V1 + '/demo'
_DEMO_CHILD_URL = _BASE_URL_V1 + '/demo/child'
_DISPATCH_INFIX = '/resource'
_DISPATCH_URL = _BASE_URL_V1 + _DISPATCH_INFIX
_EMAIL_NAME = 'email'
_EMBED_CHILD_CSS_URL = '%s/%s' % (_STATIC_BASE_URL_V1, 'embed_child.css')
_EMBED_CHILD_CSS_URL_NAME = 'embed_child_css_url'
_EMBED_CHILD_JS_NAME = 'embed_child.js'
_EMBED_CHILD_JS_URL = '%s/%s' % (_BASE_URL_V1, _EMBED_CHILD_JS_NAME)
_EMBED_CHILD_JS_URL_NAME = 'embed_child_js_url'
_EMBED_CSS_URL = '%s/%s' % (_STATIC_BASE_URL_V1, 'embed.css')
_EMBED_CSS_URL_NAME = 'embed_css_url'
_EMBED_JS_NAME = 'embed.js'
_EMBED_JS_URL = '%s/%s' % (_BASE_URL_V1, _EMBED_JS_NAME)
_EMBED_LIB_JS_NAME = 'embed_lib.js'
_EMBED_LIB_JS_URL = '%s/%s' % (_BASE_URL_V1, _EMBED_LIB_JS_NAME)
_EMBED_LIB_JS_URL_NAME = 'embed_lib_js_url'
_ENROLL_ERROR_NAME = 'enroll_error.html'
_ENROLL_ERROR_URL = _BASE_URL_V1 + '/enroll_error'
_ENV_NAME = 'env'
_ERRORS_DEMO_URL = _DEMO_URL + '/errors'
_EXAMPLE_NAME = 'example.html'
_EXAMPLE_URL = _BASE_URL + '/example'
_FINISH_AUTH_NAME = 'finish_auth.html'
_FINISH_AUTH_URL = '%s/%s' % (_BASE_URL_V1, 'auth')
_GLOBAL_ERRORS_DEMO_URL = _ERRORS_DEMO_URL + '/global'
_ID_OR_NAME_NAME = 'id_or_name'
_IN_SESSION_NAME = 'in_session'
_JQUERY_URL = 'https://ajax.googleapis.com/ajax/libs/jquery/2.1.3/jquery.min.js'
_JQUERY_URL_NAME = 'jquery_url'
_KIND_NAME = 'kind'
_LOCAL_ERRORS_DEMO_URL = _ERRORS_DEMO_URL + '/local'
_MATERIAL_ICONS_URL = 'https://fonts.googleapis.com/icon?family=Material+Icons'
_MATERIAL_ICONS_URL_NAME = 'material_icons_url'
_ORIGIN_NAME = 'origin'
_RESOURCE_URI_PREFIX_BOUNDARY_NAME = 'resource_uri_prefix_boundary'
_ROBOTO_URL = 'https://fonts.googleapis.com/css?family=Roboto'
_ROBOTO_URL_NAME = 'roboto_url'
_SIGN_IN_URL_NAME = 'sign_in_url'
_STATIC_URL = '%s/%s/.*' % (_BASE_URL, _STATIC)

_LOG = logging.getLogger('modules.embed.embed')

_TEMPLATES_DIR_V1 = os.path.join(_BASE_DIR, 'templates', _V1)
_DEMO_CHILD_HTML_PATH = os.path.join(_TEMPLATES_DIR_V1, 'demo_child.html')
_DEMO_HTML_PATH = os.path.join(_TEMPLATES_DIR_V1, 'demo.html')
_GLOBAL_ERRORS_DEMO_HTML_PATH = os.path.join(
    _TEMPLATES_DIR_V1, 'global_errors.html')
_LOCAL_ERRORS_DEMO_HTML_PATH = os.path.join(
    _TEMPLATES_DIR_V1, 'local_errors.html')
_TEMPLATES_ENV = jinja_utils.create_jinja_environment(
    jinja2.FileSystemLoader([_TEMPLATES_DIR_V1]))

# Exported public variables
EMBED_CHILD_JS_URL = _EMBED_CHILD_JS_URL


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
    Additionally, your handlers that serve embedded content must inherit from
    BaseHandler.

    The job of this class is to enroll the student and then to redirect to the
    embedded resource. If your course has no children (meaning that the
    'child_courses' member in course.yaml is missing or empty), the
    ENROLLMENT_POLICY will be applied against your course, and the user will be
    redirected to the desired resource.

    If 'child_courses' is present and non-empty, each item is a string denoting
    the namespace of all courses which are children of the target course. In
    that case, we first validate the child course state to make sure the student
    can be enrolled. To pass validation, exactly one active course must exist
    with the student on its whitelist. If this is not the case, we redirect to
    an error rather than the desired resource.

    If the system's state is valid, we find the correct child course and apply
    the ENROLLMENT_POLICY to it, then redirect to the desired resource.
    """

    # Enrollment policy we apply before 302ing to the requested resource. Can be
    # used by embed types that require an enrolled student during their render.
    ENROLLMENT_POLICY = AbstractEnrollmentPolicy

    @classmethod
    def get_embed_snippet(cls, handler, embed_key):
        kind = Registry.get_kind(cls)
        assert kind is not None

        host_url = handler.request.host_url
        slug = handler.app_context.get_slug()
        if slug == '/':
            slug = ''

        script_src = '%s%s' % (host_url, _EMBED_JS_URL)
        cb_embed_src = '%s%s%s/%s/%s' % (
            host_url, slug, _DISPATCH_URL, kind, embed_key)
        snippet = (
            '<script src="%s"></script>\n'
            '<cb-embed src="%s"></cb-embed>') % (script_src, cb_embed_src)
        return snippet

    @classmethod
    def dispatch(cls, handler):
        child_course_namespaces = cls._get_child_course_namespaces(
            handler.app_context.get_environ())

        if not cls._namespaces_valid(child_course_namespaces):
            _LOG.error(
                '%s invalid; must contain list of child course namespaces. '
                'Got: %s', _CHILD_COURSES_NAME, child_course_namespaces)
            handler.error(500)
            return

        if child_course_namespaces:
            cls._child_courses_dispatch(handler, child_course_namespaces)
        else:
            cls._default_dispatch(handler)

    @classmethod
    def get_redirect_url(cls, handler, target_slug=None):
        """Given dispatch handler, returns URL of resource we 302 to.

        Args:
            handler: webapp2.RequestHandler. The handler for the current
                request.
            target_slug: string or None. If None, the course of the embed target
                matches the course referenced by handler.request.url. Otherwise,
                the slug of the child course we resolved the user into during
                dispatch().

        Returns.
            String. The URL of the desired embed resource.
        """
        raise NotImplementedError

    @classmethod
    def get_slug(cls, handler, target_slug=None):
        """Gets target_slug, falling back to slug of handler's app_context."""
        if target_slug is not None:
            slug = target_slug
        else:
            slug = handler.get_course().app_context.get_slug()

        if slug == '/':
            return ''
        else:
            return slug

    @classmethod
    def _check_redirect_url(cls, url):
        assert isinstance(url, str), 'URL must be str, not unicode'

    @classmethod
    def _child_courses_dispatch(cls, handler, child_course_namespaces):
        # First, resolve the target course. The parent has >= 1 candidate
        # children. A candidate course is a match for dispatch if both the
        # course is currently available, and the current user is on the
        # whitelist.
        #
        # If we find a namespace we cannot resolve into a course, child_courses
        # is misconfigured by the admin. We log and 500.
        #
        # If we find any number of matches other than 1, the system is
        # misconfigured by the admin *for a particular user*. In that case, we
        # show the user an error message and encourage them to report the
        # problem to the admin.
        #
        # If we resolve into exactly one course, we apply ENROLLMENT_POLICY to
        # that course and proceed with the redirect flow, passing the slug of
        # the matched course along to get_redirect_url() for handling in
        # concrete AbstractEmbed implementations.
        all_contexts = []
        for namespace in child_course_namespaces:
            child_app_context = sites.get_app_context_for_namespace(namespace)
            if not child_app_context:
                _LOG.error(
                    '%s contains namespace with no associated course: %s',
                    _CHILD_COURSES_NAME, namespace)
                handler.error(500)
                return

            all_contexts.append(child_app_context)

        matches = []
        for app_context in all_contexts:
            course = courses.Course.get(app_context)
            if course.can_enroll_current_user():
                matches.append(course.app_context)

        num_matches = len(matches)
        if num_matches != 1:
            _LOG.error(
                'Must have exactly 1 enrollment target; got %s', num_matches)
            handler.redirect(_ENROLL_ERROR_URL, normalize=False)
            return

        child_app_context = matches[0]
        with common_utils.Namespace(child_app_context.get_namespace_name()):
            cls.ENROLLMENT_POLICY.apply(handler)

        return cls._redirect(
            handler, normalize=False, target_slug=child_app_context.get_slug())

    @classmethod
    def _default_dispatch(cls, handler):
        cls.ENROLLMENT_POLICY.apply(handler)
        return cls._redirect(handler)

    @classmethod
    def _get_child_course_namespaces(cls, course_environ):
        return course_environ.get(_COURSE_NAME, {}).get(_CHILD_COURSES_NAME, [])

    @classmethod
    def _namespaces_valid(cls, namespaces):
        if not isinstance(namespaces, list):
            return False

        for namespace in namespaces:
            if not isinstance(namespace, basestring):
                return False

        return True

    @classmethod
    def _redirect(cls, handler, normalize=True, target_slug=None):
        redirect_url = cls.get_redirect_url(handler, target_slug=target_slug)
        cls._check_redirect_url(redirect_url)
        return handler.redirect(redirect_url, normalize=normalize)


class _EmbedHeaderMixin(object):

    def _set_headers(self, headers):
        # Explicitly tell browsers this content may be framed.
        headers['X-Frame-Options'] = 'ALLOWALL'


class BaseHandler(controllers_utils.BaseHandler, _EmbedHeaderMixin):
    """Base class for handlers that serve embedded content.

    All namespaced handlers should inherit from this class; non-namespaced
    handlers that expect to render in an embed should instead inherit from
    _EmbedHeaderMixin and call _set_headers() on all responses.
    """

    def before_method(self, unused_verb, unused_path):
        self._set_headers(self.response.headers)


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

    @classmethod
    def get_kind(cls, embed_cls):
        for key, value in cls._bindings.items():
            if value == embed_cls:
                return key
        return None


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
        if len(parts) == 10:
            # A URL with an explicit namespace
            _, _, _, _, modules, embed, version, _, kind, id_or_name = parts
        elif len(parts) == 9:
            # A URL with root ('/') namespace
            _, _, _, modules, embed, version, _, kind, id_or_name = parts
        else:
            return None

        if (modules != _MODULES) or (embed != _EMBED) or (version != _V1):
            return None

        return tuple([value.strip() for value in [id_or_name, kind]])


class _AbstractJsHandler(controllers_utils.ApplicationHandler):

    _TEMPLATE_NAME = None

    @classmethod
    def _get_template(cls):
        assert cls._TEMPLATE_NAME is not None

        return _TEMPLATES_ENV.get_template(cls._TEMPLATE_NAME)

    def get(self):
        self._set_headers(self.response.headers)
        context = {}
        env = self._get_env()
        if env:
            context = {_ENV_NAME: transforms.dumps(env)}

        self.response.out.write(self._get_template().render(context))

    def _get_absolute_embed_child_css_url(self):
        return self.request.host_url + _EMBED_CHILD_CSS_URL

    def _get_absolute_embed_css_url(self):
        return self.request.host_url + _EMBED_CSS_URL

    def _get_env(self):
        raise NotImplementedError

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
            _EMBED_CHILD_CSS_URL_NAME: self._get_absolute_embed_child_css_url(),
            _IN_SESSION_NAME: users.get_current_user() is not None,
            _MATERIAL_ICONS_URL_NAME: _MATERIAL_ICONS_URL,
            _ORIGIN_NAME: self.request.host_url,
            _RESOURCE_URI_PREFIX_BOUNDARY_NAME: _DISPATCH_INFIX,
            _ROBOTO_URL_NAME: _ROBOTO_URL,
            _SIGN_IN_URL_NAME: self._get_absolute_sign_in_url(),
        }


class _EmbedJsHandler(_AbstractJsHandler):

    _TEMPLATE_NAME = _EMBED_JS_NAME

    def _get_absolute_embed_lib_js_url(self):
        return self.request.host_url + _EMBED_LIB_JS_URL

    def _get_env(self):
        return {
            _EMBED_CSS_URL_NAME: self._get_absolute_embed_css_url(),
            _EMBED_LIB_JS_URL_NAME: self._get_absolute_embed_lib_js_url(),
            _JQUERY_URL_NAME: _JQUERY_URL,
            _MATERIAL_ICONS_URL_NAME: _MATERIAL_ICONS_URL,
            _ROBOTO_URL_NAME: _ROBOTO_URL,
        }


class _AbstractDemoHandler(controllers_utils.BaseHandler):

    _TEMPLATE_PATH = None

    def get(self):
        if not self._active():
            self.error(404)
            return

        # We're not using Jinja here because we want to illustrate the use case
        # where embeds bring dynamic content into an otherwise-static HTML page.
        with open(self._TEMPLATE_PATH) as f:
            self.response.out.write(f.read())

    @classmethod
    def _active(cls):
        # Turn off in prod; exposed for swap() in tests.
        return not appengine_config.PRODUCTION_MODE


class _ChildCoursesDemoHandler(_AbstractDemoHandler):

    _TEMPLATE_PATH = _DEMO_CHILD_HTML_PATH


class _DemoHandler(_AbstractDemoHandler):

    _TEMPLATE_PATH = _DEMO_HTML_PATH


class _GlobalErrorsDemoHandler(_AbstractDemoHandler):

    _TEMPLATE_PATH = _GLOBAL_ERRORS_DEMO_HTML_PATH


class _LocalErrorsDemoHandler(_AbstractDemoHandler):

    _TEMPLATE_PATH = _LOCAL_ERRORS_DEMO_HTML_PATH


class _DispatchHandler(
        controllers_utils.BaseHandler, controllers_utils.StarRouteHandlerMixin):

    def get(self):
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


class _EnrollErrorHandler(
        controllers_utils.LocalizedGlobalHandler, _EmbedHeaderMixin):

    def get(self):
        user = users.get_current_user()
        self._set_headers(self.response.headers)
        template = self.get_template(_ENROLL_ERROR_NAME, [_TEMPLATES_DIR_V1])
        self.response.out.write(template.render({
            _EMBED_CHILD_JS_URL_NAME: _EMBED_CHILD_JS_URL,
            _EMAIL_NAME: user.email() if user else None,
        }))


class _FinishAuthHandler(controllers_utils.BaseHandler):

    def get(self):
        template = _TEMPLATES_ENV.get_template(_FINISH_AUTH_NAME)
        self.response.out.write(template.render({
            _ENV_NAME: transforms.dumps({
                _IN_SESSION_NAME: bool(users.get_current_user()),
            })
        }))


class _ExampleEmbed(AbstractEmbed):
    """Reference implementation of an Embed.

    Supports both standalone courses and those with children.
    """

    ENROLLMENT_POLICY = AutomaticEnrollmentPolicy

    @classmethod
    def get_redirect_url(cls, handler, target_slug=None):
        query = {
            _ID_OR_NAME_NAME: UrlParser.get_id_or_name(handler.request.url),
            _KIND_NAME: UrlParser.get_kind(handler.request.url),
        }
        # Note that because redirect URLs may span course boundaries, they must
        # be absolute. Use the get_slug() convenience method to determine the
        # target course of the embedded resource.
        return str('%s%s?%s' % (
            cls.get_slug(handler, target_slug=target_slug), _EXAMPLE_URL,
            urllib.urlencode(query)))


class _ExampleHandler(BaseHandler):
    """Reference implementation of a handler for an Embed."""

    def get(self):
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
    (_DEMO_CHILD_URL, _ChildCoursesDemoHandler),
    (_EMBED_CHILD_JS_URL, _EmbedChildJsHandler),
    (_EMBED_JS_URL, _EmbedJsHandler),
    (_EMBED_LIB_JS_URL, _EmbedLibJsHandler),
    (_ENROLL_ERROR_URL, _EnrollErrorHandler),
    (_FINISH_AUTH_URL, _FinishAuthHandler),
    (_GLOBAL_ERRORS_DEMO_URL, _GlobalErrorsDemoHandler),
    (_LOCAL_ERRORS_DEMO_URL, _LocalErrorsDemoHandler),
    (_STATIC_URL, tags.ResourcesHandler),
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
