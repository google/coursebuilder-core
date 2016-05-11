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

"""Course Explorer Hooks"""

__author__ = 'Rahul Singal (rahulsingal@google.com)'

from common import users
from controllers import utils
from models import models
from modules.explorer import settings


class ExplorerPageInitializer(utils.PageInitializer):
    """Page initializer for explorer page.

    Allow links to the course explorer to be added
    to the navbars of all course pages.
    """

    @classmethod
    def initialize(cls, template_values):
        template_values.update({
            'show_course_explorer_tab':
            settings.GCB_ENABLE_COURSE_EXPLORER_PAGE.value})
        user = users.get_current_user()
        if user:
            profile = models.StudentProfileDAO.get_profile_by_user_id(
                users.get_current_user().user_id())
            template_values.update({'has_global_profile': profile is not None})

def register():
    utils.PageInitializerService.set(ExplorerPageInitializer)
