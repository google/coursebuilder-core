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

"""Classes supporting creation and editing of labels."""

__author__ = 'Mike Gainer (mgainer@google.com)'

from common import schema_fields
from models import models
from modules.dashboard import dto_editor
from modules.dashboard import utils as dashboard_utils


class LabelManagerAndEditor(dto_editor.BaseDatastoreAssetEditor):

    def lme_prepare_template(self, key):
        return {
            'page_title': self.format_title('Edit Label'),
            'main_content': self.get_form(
                LabelRestHandler, key,
                dashboard_utils.build_assets_url('labels'))
        }

    def get_add_label(self):
        self.render_page(self.lme_prepare_template(''),
                         'assets', 'labels')

    def get_edit_label(self):
        key = self.request.get('key')
        label = models.LabelDAO.load(key)

        if not label:
            raise Exception('No label found')
        self.render_page(self.lme_prepare_template(key=key),
                         'assets', 'labels')


class LabelRestHandler(dto_editor.BaseDatastoreRestHandler):

    URI = '/rest/label'

    REQUIRED_MODULES = [
        'gcb-rte', 'inputex-radio', 'inputex-string', 'inputex-number',
        'inputex-hidden', 'inputex-uneditable']
    EXTRA_JS_FILES = []

    XSRF_TOKEN = 'label-edit'

    SCHEMA_VERSIONS = ['1.0']

    DAO = models.LabelDAO

    @classmethod
    def get_schema(cls):
        schema = schema_fields.FieldRegistry('Label', 'label')
        schema.add_property(schema_fields.SchemaField(
            'version', '', 'string', optional=True, hidden=True))
        schema.add_property(schema_fields.SchemaField(
            'id', 'ID', 'string', optional=True, editable=False))
        schema.add_property(schema_fields.SchemaField(
            'title', 'Title', 'string'))
        schema.add_property(schema_fields.SchemaField(
            'description', 'Description', 'string', optional=True,
            description='A brief statement outlining similarities among '
            'items marked with this label.'))
        schema.add_property(schema_fields.SchemaField(
            'type', 'Type', 'integer',
            description='The purpose for which this label will be used. '
            'E.g., Course Track labels are used to match to labels on '
            'students to select which units the student will see when '
            'taking the course.  More types of label will be added '
            'as more features are added to Course Builder.',
            select_data=[
                (lt.type, lt.title) for lt in models.LabelDTO.LABEL_TYPES],
            extra_schema_dict_values={
                '_type': 'radio',
                'className': 'label-selection'}))
        return schema

    def sanitize_input_dict(self, json_dict):
        json_dict['id'] = None
        json_dict['title'] = json_dict['title'].strip()
        json_dict['description'] = json_dict['description'].strip()
        json_dict['type'] = int(json_dict['type'])

    def validate(self, label_dict, key, version, errors):
        # Only one version currently supported, and version has already
        # been checked, so no need for dispatch.
        self._validate_10(label_dict, key, errors)

    def _validate_10(self, label_dict, key, errors):
        for label in models.LabelDAO.get_all():
            print label.title, label.id
            if (label.title == label_dict['title'] and
                (not key or label.id != long(key))):
                errors.append('There is already a label with this title!')

    def is_deletion_allowed(self, label):
        # TODO(mgainer): When labels on course units get modified to be
        # IDs of labels rather than strings, enforce non-deletion of
        # labels until they are removed from units.
        #
        # No integrity checks against Student objects; there will be
        # too many to economically check.  We will handle this by
        # simply gracefully handling (and removing, when convenient)
        # broken Label references on students.  (This is morally
        # equivalent to having an admin actually delete the label from
        # all students, but here, we're just paying an amortized cost,
        # rather than taking it all up front.)
        return True

    def get_default_content(self):
        return {
            'version': self.SCHEMA_VERSIONS[0],
            'title': 'New Label',
            'description': '',
            'type': models.LabelDTO.LABEL_TYPE_GENERAL,
            }
