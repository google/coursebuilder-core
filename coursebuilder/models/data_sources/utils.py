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

from models import jobs

DATA_SOURCE_ACCESS_XSRF_ACTION = 'data_source_access'


def generate_data_source_token(xsrf):
    """Generate an XSRF token used to access data source, and protect PII."""
    return xsrf.create_xsrf_token(DATA_SOURCE_ACCESS_XSRF_ACTION)


def get_required_jobs(data_source_class, app_context, catch_and_log_):
    ret = []
    for required_generator in data_source_class.required_generators():
        job = required_generator(app_context).load()
        if not job:
            catch_and_log_.critical('Job for %s has never run.' %
                                    required_generator.__name__)
            return None
        elif not job.has_finished:
            catch_and_log_.critical('Job for %s is still running.' %
                                    required_generator.__name__)
            return None
        elif job.status_code == jobs.STATUS_CODE_FAILED:
            catch_and_log_.critical('Job for %s failed its last run.' %
                                    required_generator.__name__)
            return None
        else:
            ret.append(job)
    return ret
