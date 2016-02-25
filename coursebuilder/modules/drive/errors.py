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

"""Drive-related exceptions."""

__author__ = [
    'nretallack@google.com (Nick Retallack)',
]


class Error(Exception):
    pass


class ConfigurationError(Error):
    pass


class NotConfigured(ConfigurationError):
    pass


class _WrappedError(Error):
    def __init__(self, original):
        super(_WrappedError, self).__init__()
        self._original = original

    def __str__(self):
        return "{}: {}".format(
            self._original.__class__.__name__, str(self._original))


class SharingPermissionError(_WrappedError):
    pass


class TimeoutError(_WrappedError):
    pass


class Misconfigured(_WrappedError, ConfigurationError):
    pass


class _HttpError(Error):
    def __init__(self, url, response, content):
        super(_HttpError, self).__init__()
        self.url = url
        self.response = response
        self.content = content

    def __str__(self):
        return self.response
