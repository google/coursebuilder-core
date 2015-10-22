# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Course explorer module."""

__author__ = 'Rahul Singal (rahulsingal@google.com)'

from common import users
from controllers import utils
from models import custom_modules
from models.config import ConfigProperty
from models.models import StudentProfileDAO
from modules.course_explorer import messages
from modules.course_explorer import student


GCB_ENABLE_COURSE_EXPLORER_PAGE = ConfigProperty(
    'gcb_enable_course_explorer_page', bool,
    messages.SITE_SETTINGS_COURSE_EXPLORER, default_value=False,
    label='Course Explorer', multiline=False, validator=None)


custom_module = None


class ExplorerPageInitializer(utils.PageInitializer):
    """Page initializer for explorer page.

    Allow links to the course explorer to be added
    to the navbars of all course pages.
    """

    @classmethod
    def initialize(cls, template_values):
        template_values.update(
            {'show_course_explorer_tab': GCB_ENABLE_COURSE_EXPLORER_PAGE.value})
        user = users.get_current_user()
        if user:
            profile = StudentProfileDAO.get_profile_by_user_id(
                users.get_current_user().user_id())
            template_values.update({'has_global_profile': profile is not None})


def register_module():
    """Registers this module in the registry."""

    # set the page initializer
    utils.PageInitializerService.set(ExplorerPageInitializer)

    # setup routes
    explorer_routes = [
        ('/', student.IndexPageHandler),
        ('/explorer', student.AllCoursesHandler),
        (r'/explorer/assets/(.*)', student.AssetsHandler),
        ('/explorer/courses', student.RegisteredCoursesHandler),
        ('/explorer/profile', student.ProfileHandler)]

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Course Explorer',
        'A set of pages for delivering an online course.',
        explorer_routes, [])
    return custom_module


def unregister_module():
    """Unregisters this module in the registry."""

    # set the page intializer to default.
    utils.PageInitializerService.set(utils.DefaultPageInitializer)

    return custom_modules
