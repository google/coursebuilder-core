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

"""ETL testing utilities."""

import copy
import cStringIO
import logging
import os
from controllers import sites
from tests.functional import actions
from tools.etl import etl
from tools.etl import remote


class EtlTestBase(actions.TestBase):
    # Allow access to protected members under test.
    # pylint: disable=protected-access

    def setUp(self):
        """Configures EtlMainTestCase."""
        super(EtlTestBase, self).setUp()
        self.test_environ = copy.deepcopy(os.environ)
        # In etl.main, use test auth scheme to avoid interactive login.
        self.test_environ['SERVER_SOFTWARE'] = remote.TEST_SERVER_SOFTWARE
        self.url_prefix = '/test'
        self.namespace = 'ns_test'
        self.raw = 'course:%s::%s' % (self.url_prefix, self.namespace)
        self.swap(os, 'environ', self.test_environ)
        sites.setup_courses(self.raw + ', course:/:/')

        self.log_stream = cStringIO.StringIO()
        self.old_log_handlers = list(etl._LOG.handlers)
        etl._LOG.handlers = [logging.StreamHandler(self.log_stream)]

    def tearDown(self):
        sites.reset_courses()
        etl._LOG.handlers = self.old_log_handlers
        super(EtlTestBase, self).tearDown()

    def get_log(self):
        self.log_stream.flush()
        return self.log_stream.getvalue()


class FakeEnvironment(object):
    """Temporary fake tools.etl.remote.Evironment.

    Bypasses making a remote_api connection because webtest can't handle it and
    we don't want to bring up a local server for our functional tests. When this
    fake is used, the in-process datastore stub will handle RPCs.

    TODO(johncox): find a way to make webtest successfully emulate the
    remote_api endpoint and get rid of this fake.
    """

    def __init__(self, application_id, server, path=None):
        self._appication_id = application_id
        self._path = path
        self._server = server

    def establish(self):
        pass
