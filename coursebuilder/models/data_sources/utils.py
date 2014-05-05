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

"""Utility functions common to data sources module."""

__author__ = 'Mike Gainer (mgainer@google.com)'

DATA_SOURCE_ACCESS_XSRF_ACTION = 'data_source_access'


def generate_data_source_token(xsrf):
    """Generate an XSRF token used to access data source, and protect PII."""
    return xsrf.create_xsrf_token(DATA_SOURCE_ACCESS_XSRF_ACTION)
