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

"""Banner to obtain consent for usage reporting."""

__author__ = [
    'John Orr (jorr@google.com)',
]

import jinja2

from controllers import utils
from models import roles
from models import transforms
from modules.admin import admin
from modules.dashboard import dashboard
from modules.usage_reporting import config
from modules.usage_reporting import messaging
from modules.usage_reporting import constants

def _make_consent_banner(handler):
    if config.is_consent_set() or messaging.is_disabled():
        return None

    template_values = {
        'xsrf_token': handler.create_xsrf_token(
            ConsentBannerRestHandler.XSRF_TOKEN),
        'is_super_admin': roles.Roles.is_super_admin()
    }
    return jinja2.Markup(
        handler.get_template('consent_banner.html', [constants.TEMPLATES_DIR]
    ).render(template_values))


class ConsentBannerRestHandler(utils.BaseRESTHandler):
    """Handle REST requests to set report consent from banner."""

    URL = '/rest/modules/usage_reporting/consent'
    XSRF_TOKEN = 'usage_reporting_consent_banner'

    def post(self):
        request = transforms.loads(self.request.get('request'))

        if not self.assert_xsrf_token_or_fail(request, self.XSRF_TOKEN, {}):
            return

        if not roles.Roles.is_super_admin():
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        payload = transforms.loads(request.get('payload'))
        is_allowed = payload['is_allowed']
        config.set_report_allowed(is_allowed)
        messaging.Message.send_instance_message(
            messaging.Message.METRIC_REPORT_ALLOWED, is_allowed,
            source=messaging.Message.BANNER_SOURCE)

        transforms.send_json_response(self, 200, 'OK')


def notify_module_enabled():
    dashboard.DashboardHandler.PAGE_HEADER_HOOKS.append(_make_consent_banner)
    admin.GlobalAdminHandler.PAGE_HEADER_HOOKS.append(_make_consent_banner)
