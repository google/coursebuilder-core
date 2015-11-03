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

"""Provide the capability to add extra links or text to the main navbar."""

__author__ = 'John Orr (jorr@google.com)'

import os

import appengine_config
from common import schema_fields
from common import users
from controllers import utils
from models import courses
from models import custom_modules
from models import models
import messages

EXTRA_TABS_KEY = 'extra_tabs'
LABEL_KEY = 'label'
URL_KEY = 'url'
CONTENT_KEY = 'content'
POSITION_KEY = 'position'
VISIBILITY_KEY = 'visibility'

POS_LEFT = 'left'
POS_RIGHT = 'right'

VIS_ALL = 'all'
VIS_STUDENT = 'student'

TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'extra_tabs', 'templates')


class ExtraTabHandler(utils.BaseHandler):
    URL = 'modules/extra_tabs/render'
    INDEX_QUERY_PARAM = 'index'

    def get(self):
        index = int(self.request.get(self.INDEX_QUERY_PARAM))
        env = courses.Course.get_environ(self.get_course().app_context)
        tab_data = env['course'][EXTRA_TABS_KEY][index]

        if not _is_visible(tab_data, self.get_student()):
            return

        self.template_value['navbar'] = {}
        self.template_value['content'] = tab_data['content']

        self.render('extra_tab_page.html', additional_dirs=[TEMPLATES_DIR])


def options_schema_provider(unused_course):

    extra_tab_type = schema_fields.FieldRegistry(
        'Extra Tab',
        extra_schema_dict_values={'className': 'settings-list-item'})
    extra_tab_type.add_property(schema_fields.SchemaField(
        LABEL_KEY, 'Title', 'string',
        description=messages.EXTRA_TABS_TITLE_DESCRIPTION))
    extra_tab_type.add_property(schema_fields.SchemaField(
        POSITION_KEY, 'Tab Position', 'string',
        description=messages.EXTRA_TAB_POSITION_DESCRIPTION,
        i18n=False, optional=True,
        select_data=[(POS_LEFT, 'Left'), (POS_RIGHT, 'Right')]))
    extra_tab_type.add_property(schema_fields.SchemaField(
        VISIBILITY_KEY, 'Visibility', 'string', optional=True, i18n=False,
        description=messages.EXTRA_TABS_VISIBILITY_DESCRIPTION,
        select_data=[
            (VIS_ALL, 'Everyone'), (VIS_STUDENT, 'Registered students')]))
    extra_tab_type.add_property(schema_fields.SchemaField(
        URL_KEY, 'Tab URL', 'string', optional=True,
        description=messages.EXTRA_TABS_URL_DESCRIPTION,
        extra_schema_dict_values={'_type': 'url', 'showMsg': True}))
    extra_tab_type.add_property(schema_fields.SchemaField(
        CONTENT_KEY, 'Tab Content', 'html', optional=True,
        description=messages.EXTRA_TABS_CONTENT_DESCRIPTION))
    return schema_fields.FieldArray(
        'course:' + EXTRA_TABS_KEY, 'Extra Tabs',
        item_type=extra_tab_type,
        description=messages.EXTRA_TABS_DESCRIPTION,
        extra_schema_dict_values={
            'className': 'settings-list wide',
            'listAddLabel': 'Add a tab',
            'listRemoveLabel': 'Delete tab'},
        optional=True)


def _get_current_student():
    user = users.get_current_user()
    if user is None:
        return None
    else:
        return models.Student.get_enrolled_student_by_user(user)


def _is_visible(tab_data, student):
    return tab_data.get(VISIBILITY_KEY) != VIS_STUDENT or (
        student is not None and student.is_enrolled)


def _get_links(app_context, pos):
    env = courses.Course.get_environ(app_context)
    student = _get_current_student()

    links = []
    for tab_index, tab_data in enumerate(env['course'].get(EXTRA_TABS_KEY, [])):
        if _is_visible(tab_data, student) and tab_data.get(POSITION_KEY) == pos:
            label = tab_data.get(LABEL_KEY)
            url = tab_data.get(URL_KEY)
            if not url:
                url = '%s?%s=%s' % (
                    ExtraTabHandler.URL, ExtraTabHandler.INDEX_QUERY_PARAM,
                    tab_index)
            links.append((url, label))
    return links


def left_links(app_context):
    return _get_links(app_context, POS_LEFT)


def right_links(app_context):
    return _get_links(app_context, POS_RIGHT)


extra_tabs_module = None


def register_module():

    def on_module_enabled():
        courses.Course.OPTIONS_SCHEMA_PROVIDERS.setdefault(
            courses.Course.SCHEMA_SECTION_COURSE, []).append(
                options_schema_provider)
        utils.CourseHandler.LEFT_LINKS.append(left_links)
        utils.CourseHandler.RIGHT_LINKS.append(right_links)

    def on_module_disabled():
        courses.Course.OPTIONS_SCHEMA_PROVIDERS.setdefault(
            courses.Course.SCHEMA_SECTION_COURSE, []).remove(
                options_schema_provider)
        utils.CourseHandler.LEFT_LINKS.remove(left_links)
        utils.CourseHandler.RIGHT_LINKS.remove(right_links)

    global_routes = []

    namespaced_routes = [
        ('/' + ExtraTabHandler.URL, ExtraTabHandler)]

    global extra_tabs_module  # pylint: disable=global-statement
    extra_tabs_module = custom_modules.Module(
        'Extra Navbar Tabs',
        'Add tabs to the main navbar.',
        global_routes, namespaced_routes,
        notify_module_disabled=on_module_disabled,
        notify_module_enabled=on_module_enabled)
    return extra_tabs_module
