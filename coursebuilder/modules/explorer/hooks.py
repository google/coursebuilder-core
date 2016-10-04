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
from common import safe_dom
from controllers import utils
from models import courses
from models import models
from modules.admin import admin
from modules.explorer import constants
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


def _maybe_local(
        result, site_data, app_context, key, path,
        blank_values=courses.BLANK_VALUES):
    course_value = courses.get_setting_value(app_context, path)
    site_value = site_data.get(key)
    if course_value not in blank_values:
        result[key] = course_value
    else:
        result[key] = site_value


def _get_site_info(app_context):
    result = {}
    data = settings.get_course_explorer_settings_data()
    simple_settings = (
        ('institution_name', 'institution:name',
            courses.INSTITUTION_NAME_BLANK_VALUES),
        ('institution_url', 'institution:url',
            courses.INSTITUTION_URL_BLANK_VALUES),
        ('privacy_terms_url', 'base:privacy_terms_url',
            courses.PRIVACY_TERM_URL_BLANK_VALUES),
        ('logo_alt_text', 'institution:logo:alt_text',
            courses.BLANK_VALUES),
        ('title', 'base:nav_header',
            courses.SITE_NAME_BLANK_VALUES),
    )

    for key, path, blanks in simple_settings:
        _maybe_local(result, data, app_context, key, path, blank_values=blanks)

    local_logo = courses.get_setting_value(
        app_context, 'institution:logo:url')
    if local_logo not in courses.SITE_LOGO_BLANK_VALUES:
        result['logo_url'] = local_logo
    else:
        try:
            result['logo_url'] = settings.make_logo_url(
                data['logo_mime_type'], data['logo_bytes_base64'])
        except KeyError:
            pass

    return result


class ShowInExplorerColumn(admin.AbstractAdditionalAllCoursesColumn):

    @classmethod
    def produce_table_header(cls):
        return safe_dom.Element(
            'th', className='gcb-not-sortable'
        ).add_text(
            'In Explorer?'
        )

    @classmethod
    def produce_table_row(cls, app_context):
        if courses.Course.get_named_course_setting_from_environ(
            constants.SHOW_IN_EXPLORER, app_context.get_environ(),
            default=True):
            status = 'Yes'
        else:
            status = 'No'
        return safe_dom.Element(
            'td',
            className='show_in_explorer',
            id='show_in_explorer_' + app_context.get_namespace_name()
        ).add_text(
            status
        )

    @classmethod
    def produce_table_footer(cls):
        return safe_dom.Element('td')


def register():
    admin.BaseAdminHandler.ADDITIONAL_COLUMN_HOOKS[constants.MODULE_NAME] = (
        ShowInExplorerColumn)
    utils.PageInitializerService.set(ExplorerPageInitializer)
    utils.CourseHandler.SITE_INFO.append(_get_site_info)
