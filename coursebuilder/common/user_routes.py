# Copyright 2016 Google Inc. All Rights Reserved.
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

"""Manages user-defined URL routing inside courses."""

__author__ = [
    'nretallack@google.com (Nick Retallack)',
]

import logging
import re

from models import courses

USER_ROUTABLE_HANDLERS = {}

USER_ROUTES_KEY = 'user_routes'
HANDLER_ID_KEY = 'handler_id'
EXTRA_KEY = 'extra'

HANDLER_KEY = 'handler'
HANDLER_TITLE_KEY = 'title'

class URLError(Exception):
    pass


class URLReservedError(URLError):
    pass


class URLTakenError(URLError):
    def __init__(self, url, entry):
        super(URLTakenError, self).__init__()
        self.url = url
        self.handler_id = entry[HANDLER_ID_KEY]
        self.title = USER_ROUTABLE_HANDLERS[self.handler_id][HANDLER_TITLE_KEY]
        self.extra = entry[EXTRA_KEY]


class URLInvalidError(URLError):
    pass


class UserCourseRouteManager(object):
    def __init__(self, routes):
        self.routes = routes

    @classmethod
    def from_current_appcontext(cls):
        return cls(_get_routes_from_settings(_get_settings()))

    def save(self):
        settings = _get_settings()
        _put_routes_in_settings(settings, self.routes)
        _save_settings(settings)

    def add(self, url, handler_id, extra=None):
        """Add a route to the map.  Does not save automatically."""
        url = normalize_path(url)
        self._check_add_parameters(url, handler_id)

        if url in self.routes:
            raise URLTakenError(url, self.routes[url])

        self.routes[url] = {
            HANDLER_ID_KEY: handler_id,
            EXTRA_KEY: extra,
        }

    def _check_add_parameters(self, url, handler_id):
        """Check for errors that wouldn't change based on the state."""
        assert handler_id in USER_ROUTABLE_HANDLERS
        validate_path(url)

        if self.is_reserved_url(url):
            raise URLReservedError

    def is_reserved_url(self, url):
        from controllers import sites
        return url != '/' and url in sites.ApplicationRequestHandler.urls_map

    def remove(self, url):
        del self.routes[normalize_path(url)]


_PATH_REGEX = re.compile('^[/a-zA-Z0-9._-]*$')


def validate_path(path):
    if not _PATH_REGEX.match(path):
        raise URLInvalidError


def normalize_path(path):
    """Put a URL path into the format used by the data structure."""

    if path in ('', '/'):
        return '/'

    path = path.rstrip('/')
    if not path.startswith('/'):
        path = '/{path}'.format(path=path)
    return path

def _get_course():
    from controllers import sites
    return courses.Course(
        None, app_context=sites.get_app_context_for_current_request())


def _get_settings():
    from controllers import sites
    return sites.get_app_context_for_current_request().get_environ()


def _save_settings(settings):
    _get_course().save_settings(settings)


def _get_routes_from_settings(settings):
    return settings.get(USER_ROUTES_KEY, {})


def _put_routes_in_settings(settings, routes):
    settings[USER_ROUTES_KEY] = routes


def _get_user_route_for_path(course, path):
    """Unlike the other 'routes' functions, this gets a single path"""
    return course.get_environ()[USER_ROUTES_KEY][path]


def _get_handler(handler_id):
    return USER_ROUTABLE_HANDLERS[handler_id][HANDLER_KEY]


def register_handler(handler, handler_id, title):
    """Make a handler available to user-defined routing.

    Args:
        handler: The handler factory/class
        handler_id: How the handler will be referred to in the datastore
        title: A human-readable name for the handler.  Used in error messages.
    """

    assert handler_id not in USER_ROUTABLE_HANDLERS
    USER_ROUTABLE_HANDLERS[handler_id] = {
        HANDLER_KEY: handler,
        HANDLER_TITLE_KEY: title,
    }


def _get_handler_for_path(course, path):
    path = normalize_path(path)
    try:
        route = _get_user_route_for_path(course, path)
    except KeyError:
        return None

    try:
        handler_id = route[HANDLER_ID_KEY]
    except KeyError:
        logging.error('Invalid user route for path %s', path)
        return None

    try:
        return _get_handler(handler_id)
    except KeyError:
        logging.error('Handler with id %s is not registered', handler_id)
        return None
