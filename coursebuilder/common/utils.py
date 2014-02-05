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


from google.appengine.api import namespace_manager


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
