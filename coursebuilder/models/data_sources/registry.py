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

"""Registration for data sources."""

__author__ = 'Mike Gainer (mgainer@google.com)'

from models import jobs
from models.data_sources import base_types


class _Registry(object):

    _data_source_classes = []

    @classmethod
    def register(cls, clazz):
        # Package private: pylint: disable-msg=protected-access
        if not issubclass(clazz, base_types._DataSource):
            raise ValueError(
                'All registered data sources must ultimately inherit '
                'from models.data_source.data_types._DataSource; '
                '"%s" does not.' % clazz.__name__)

        clazz.verify_on_registration()
        cls._data_source_classes.append(clazz)

    @classmethod
    def get_rest_data_source_classes(cls):
        return [c for c in cls._data_source_classes
                # Package private: pylint: disable-msg=protected-access
                if issubclass(c, base_types._AbstractRestDataSource)]

    @classmethod
    def is_registered(cls, clazz):
        return clazz in cls._data_source_classes

    @classmethod
    def get_generator_classes(cls):
        ret = set()
        for c in cls._data_source_classes:
            for g in c.required_generators():
                if issubclass(g, jobs.DurableJobBase):
                    ret.add(g)
        return ret
