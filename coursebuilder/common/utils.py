# Copyright 2012 Google Inc. All Rights Reserved.
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

"""General utility functions common to all of CourseBuilder."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import cStringIO
import datetime
import logging
import random
import re
import string
import sys
import traceback
import zipfile

import appengine_config
from google.appengine.api import namespace_manager

BACKWARD_COMPATIBLE_SPLITTER = re.compile(r'[\[\] ,\t\n]+', flags=re.M)
SPLITTER = re.compile(r'[ ,\t\n]+', flags=re.M)
ALPHANUM = string.ascii_letters + string.digits


def text_to_list(text, splitter=SPLITTER):
    if not text:
        return []
    return [item for item in splitter.split(text) if item]


def list_to_text(items):
    if not items:
        return ''
    return ' '.join([unicode(item) for item in items])


def generate_instance_id():
    length = 12
    return ''.join([random.choice(ALPHANUM) for _ in xrange(length)])


def truncate(x, precision=2):
    assert isinstance(precision, int) and precision >= 0
    factor = 10 ** precision
    return int(x * factor) / float(factor)


def iter_all(query, batch_size=100):
    """Yields query results iterator. Proven method for large datasets."""
    prev_cursor = None
    any_records = True
    while any_records:
        any_records = False
        query = query.with_cursor(prev_cursor)
        for entity in query.run(batch_size=batch_size):
            any_records = True
            yield entity
        prev_cursor = query.cursor()


def run_hooks(hooks, *args, **kwargs):
    """Run all the given callback hooks.

    Args:
        hooks: iterable. The callback functions to be invoked. Each function is
            passed the remaining args and kwargs.
        *args: List of arguments passed the hook functions.
        **kwargs: Dict of keyword args passed to the hook functions.
    """
    for hook in hooks:
        # TODO(jorr): Add configurable try-catch around call
        hook(*args, **kwargs)


class Namespace(object):
    """Save current namespace and reset it.

    This is inteded to be used in a 'with' statement.  The verbose code:
      old_namespace = namespace_manager.get_namespace()
      try:
          namespace_manager.set_namespace(self._namespace)
          app_specific_stuff()
      finally:
          namespace_manager.set_namespace(old_namespace)

    can be replaced with the much more terse:
      with Namespace(self._namespace):
          app_specific_stuff()

    This style can be used in classes that need to be pickled; the
    @in_namespace function annotation (see below) is arguably visually
    cleaner, but can't be used with pickling.

    The other use-case for this style of acquire/release guard is when
    only portions of a function need to be done within a namespaced
    context.
    """

    def __init__(self, new_namespace):
        self.new_namespace = new_namespace

    def __enter__(self):
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace(self.new_namespace)
        return self

    def __exit__(self, *unused_exception_info):
        namespace_manager.set_namespace(self.old_namespace)
        return False  # Don't suppress exceptions


def log_exception_origin():
    """Log the traceback of the origin of an exception as a critical error.

    When in a try/except block, logging often discards the traceback of the
    origin of the thrown exception.  This function determines the traceback at
    the point of exception and sends that to the standard logging library as a
    critical message.  This is a common idiom, and the boilerplate code is a
    little verbose, so factored here into a separate function.

    """
    try:
        # Log origin of exception to permit troubleshooting.
        # Do this in try/finally block to conform to Python docs'
        # recommendation to avoid circular reference to traceback
        # object.
        origin_traceback = sys.exc_info()[2]
        logging.critical(''.join(traceback.format_tb(origin_traceback)))
    finally:
        pass


def find(predicate, iterable, default=None):
    """Find the first matching item in a list, or None if not found.

    This is as a more-usable alternative to filter(), in that it does
    not raise an exception if the item is not found.

    Args:
      predicate: A function taking one argument: an item from the iterable.
      iterable: A list or generator providing items passed to "predicate".
      default: Value to return if no item is found.
    Returns:
      The first item in "iterable" where "predicate" returns True, or
      None if no item matches.
    """
    for item in iterable:
        if predicate(item):
            return item
    return default


class ZipAwareOpen(object):
    """Provide open() services for third party libraries in .zip files.

    Some libraries that are commonly downloaded and pushed alongside
    CourseBuilder are shipped with data files.  These libraries make the
    assumption that when shipped in a product, they are packaged as plain
    files in a normal directory hierarchy.  Thus, when that library is
    actually packaged in a .zip file, the open() call will fail.  This
    class provides a convenient syntax around functionality that wraps
    calls to the builtin open() (or in the case of AppEngine, the version
    of 'open()' that AppEngine itself provides).  When an attempt is made
    to open a file that is actually packaged within a .zip file, this
    wrapper will intelligently look within the .zip file for that member.

    Only read access is supported.

    No recursion into .zip files within other .zip files is supported.

    Example:
        with common_utils.ZipAwareOpen():
            third_party_module.some_func_that_calls_open()
    """

    LIB_PATHS = {l.file_path: l.full_path for l in appengine_config.ALL_LIBS}

    def zip_aware_open(self, name, *args, **kwargs):
        """Override open() iff opening a file in a library .zip for reading."""

        # First cut: Don't even consider checking .zip files unless the
        # open is for read-only and ".zip" is in the filename.
        mode = args[0] if args else kwargs['mode'] if 'mode' in kwargs else 'r'
        if '.zip' in name and (not mode or mode == 'r' or mode == 'rb'):

            # Only consider .zip files known in the third-party libraries
            # registered in appengine_config.py
            for path in ZipAwareOpen.LIB_PATHS:

                # Don't use zip-open if the file we are looking for _is_
                # the sought .zip file.  (We are recursed into from the
                # zipfile module when it needs to open a file.)
                if path in name and path != name:
                    zf = zipfile.ZipFile(path, 'r')

                    # Possibly extend simple path to .zip file with relative
                    # path inside .zip file to meaningful contents.
                    name = name.replace(
                        path, ZipAwareOpen.LIB_PATHS[path])

                    # Strip off on-disk path to .zip file.  This leaves
                    # us with the absolute path within the .zip file.
                    name = name.replace(path, '').lstrip('/')

                    # Return a file-like object containing the data extracted
                    # from the .zip file for the given name.
                    data = zf.read(name)
                    return cStringIO.StringIO(data)

        # All other cases pass through to builtin open().
        return self._real_open(name, *args, **kwargs)

    def __enter__(self):
        """Wrap Python's internal open() with our version."""
        # No particular reason to use __builtins__ in the 'zipfile' module; the
        # set of builtins is shared among all modules implemented in Python.
        self._real_open = sys.modules['zipfile'].__builtins__['open']
        sys.modules['zipfile'].__builtins__['open'] = self.zip_aware_open

    def __exit__(self, *unused_exception_info):
        """Reset open() to be the Python internal version."""
        sys.modules['zipfile'].__builtins__['open'] = self._real_open
        return False  # Don't suppress exceptions.


def _parse_timedelta_string(timedelta_string):
    keys = ['weeks', 'days', 'hours', 'minutes', 'seconds']
    kwargs = {}
    for key in keys:
        # Expect exact match to 'weeks', 'week', or 'w' (for all unit type
        # names, not just "weeks") and then either a separator, a number, or
        # end-of-string.  This prevents 'months' from being recognized as
        # valid, when actually 'm' -> 'minutes'.
        pattern = r'([0-9]+)\s*(%s|%s|%s)(\s|,|$|[0-9])' % (
            key, key[:-1], key[0])  # 'weeks', 'week', 'w'
        matches = re.search(pattern, timedelta_string, re.IGNORECASE)
        if matches:
            quantity = int(matches.group(1))
            if quantity:
                kwargs[key] = quantity
    return kwargs


def parse_timedelta_string(timedelta_string):
    return datetime.timedelta(**_parse_timedelta_string(timedelta_string))


class ValidateTimedelta(object):

    @classmethod
    def validate(cls, value, errors):
        if value is None or value == '':
            return  # Blank is OK.
        value = value.strip()
        kwargs = _parse_timedelta_string(value)
        if not kwargs:
            errors.append(
                'The string "%s" ' % value + 'has some problems. '
                'Supported units are: '
                '"weeks", "days", "hours", "minutes", "seconds".  Units may '
                'be specified as their first letter, singular, or plural.  '
                'Spaces and commas may be used or omitted.  E.g., both of '
                'the following are equivalent: "3w1d7h", '
                '"3 weeks, 1 day, 7 hours"')
        return datetime.timedelta(**kwargs).total_seconds()
