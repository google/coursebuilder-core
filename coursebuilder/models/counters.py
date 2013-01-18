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

"""Manages performance counters of an application and/or its modules."""

__author__ = 'Pavel Simakov (psimakov@google.com)'


class PerfCounter(object):
    """A generic, in-process integer counter."""

    def __init__(self, name, doc_string):
        self._name = name
        self._doc_string = doc_string
        self._value = 0

        Registry.registered[self.name] = self

    def inc(self, increment=1):
        """Increments value by a given increment."""
        self._value += increment

    @property
    def name(self):
        return self._name

    @property
    def doc_string(self):
        return self._doc_string

    @property
    def value(self):
        return self._value


class Registry(object):
    """Holds all registered counters."""
    registered = {}
