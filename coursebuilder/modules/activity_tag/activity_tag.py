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

"""Classes to provide a tag to embed activities into lesson bodies."""

import os
from xml.etree import cElementTree

from common import schema_fields
from common import tags
from models import courses
from models import custom_modules

# String. Course Builder root-relative path where resources for this module are.
_RESOURCES_PATH = os.path.join(
    os.path.sep, 'modules', 'activity_tag', 'resources')


class Activity(tags.BaseTag):
    """A tag to embed activities into lesson bodies."""

    binding_name = 'gcb-activity'

    @classmethod
    def name(cls):
        return 'Activity'

    @classmethod
    def vendor(cls):
        return 'gcb'

    def render(self, node, unused_handler):
        activity_id = node.attrib.get('activityid')
        script = cElementTree.XML("""
<div>
  <script></script>
  <div id="activityContents"></div>
</div>""")
        script[0].set('src', 'assets/js/%s' % activity_id)
        return script

    def get_icon_url(self):
        return os.path.join(_RESOURCES_PATH, 'activity.png')

    def get_schema(self, handler):
        """The schema of the tag editor."""
        activity_list = []
        if handler:
            course = courses.Course(handler)

            if course.version == courses.COURSE_MODEL_VERSION_1_2:
                return self.unavailable_schema(
                    'Not available in file-based courses.')

            lesson_id = None
            if handler.request:
                lesson_id = handler.request.get('lesson_id')

            activity_list = []
            for unit in course.get_units():
                for lesson in course.get_lessons(unit.unit_id):
                    filename = 'activity-%s.js' % lesson.lesson_id
                    if lesson.has_activity:
                        if lesson.activity_title:
                            title = lesson.activity_title
                        else:
                            title = filename
                        name = '%s - %s (%s) ' % (
                            unit.title, lesson.title, title)
                        activity_list.append((filename, name))
                    elif str(lesson.lesson_id) == lesson_id:
                        name = 'Current Lesson (%s)' % filename
                        activity_list.append((filename, name))

        reg = schema_fields.FieldRegistry('Activity')
        reg.add_property(
            schema_fields.SchemaField(
                'activityid', 'Activity Id', 'string', optional=True,
                select_data=activity_list))
        return reg


custom_module = None


def register_module():
    """Registers this module for use."""

    def on_module_disable():
        tags.Registry.remove_tag_binding(Activity.binding_name)
        tags.EditorBlacklists.unregister(
            Activity.binding_name,
            tags.EditorBlacklists.COURSE_SCOPE)
        tags.EditorBlacklists.unregister(
            Activity.binding_name, tags.EditorBlacklists.ASSESSMENT_SCOPE)
        tags.EditorBlacklists.unregister(
            Activity.binding_name, tags.EditorBlacklists.DESCRIPTIVE_SCOPE)

    def on_module_enable():
        tags.Registry.add_tag_binding(Activity.binding_name, Activity)
        tags.EditorBlacklists.register(
            Activity.binding_name,
            tags.EditorBlacklists.COURSE_SCOPE)
        tags.EditorBlacklists.register(
            Activity.binding_name, tags.EditorBlacklists.ASSESSMENT_SCOPE)
        tags.EditorBlacklists.register(
            Activity.binding_name, tags.EditorBlacklists.DESCRIPTIVE_SCOPE)

    global custom_module  # pylint: disable=global-statement

    # Add a static handler for icons shown in the rich text editor.
    global_routes = [(
        os.path.join(_RESOURCES_PATH, '.*'), tags.ResourcesHandler)]

    custom_module = custom_modules.Module(
        'Embedded Activity',
        'Adds a custom tag to embed an activity in a lesson.',
        global_routes, [],
        notify_module_disabled=on_module_disable,
        notify_module_enabled=on_module_enable,
    )

    return custom_module
