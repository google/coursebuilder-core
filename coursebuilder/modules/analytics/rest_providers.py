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

"""Classes providing REST data sources for common CourseBuilder items."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import logging

from common import schema_fields
from common import utils
from models import courses
from models import data_sources
from models import entity_transforms
from models import jobs
from models import models
from models import transforms
from tools import verify

from google.appengine.ext import db


class AssessmentsDataSource(data_sources.AbstractSmallRestDataSource):

    @classmethod
    def get_name(cls):
        return 'assessments'

    @classmethod
    def get_title(cls):
        return 'Assessments'

    @classmethod
    def get_schema(cls, unused_app_context, unused_catch_and_log,
                   unused_source_context):
        reg = schema_fields.FieldRegistry(
            'Analytics',
            description='Sets of questions determining student skill')
        reg.add_property(schema_fields.SchemaField(
            'unit_id', 'Unit ID', 'string',
            description='Key uniquely identifying this particular assessment'))
        reg.add_property(schema_fields.SchemaField(
            'title', 'Title', 'string',
            description='Human-readable title describing the assessment'))
        reg.add_property(schema_fields.SchemaField(
            'weight', 'Weight', 'number',
            description='Scalar indicating how the results of this assessment '
            'are to be weighted versus the results of peer assessments.'))
        reg.add_property(schema_fields.SchemaField(
            'html_check_answers', 'Check Answers', 'boolean',
            description='Whether students may check their answers before '
            'submitting the assessment.'))
        reg.add_property(schema_fields.SchemaField(
            'props', 'Properties', 'string',
            description='JSON string containing key/value additional '
            'properties, not further defined.'))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def fetch_values(cls, app_context, *args, **kwargs):
        course = courses.Course(handler=None, app_context=app_context)
        assessments = course.get_units_of_type(verify.UNIT_TYPE_ASSESSMENT)
        ret = []
        for assessment in assessments:
            ret.append({
                'unit_id': str(assessment.unit_id),
                'title': assessment.title,
                'weight': assessment.weight,
                'html_check_answers': assessment.html_check_answers,
                'props': transforms.dumps(assessment.properties)})
        return ret, 0


class UnitsDataSource(data_sources.AbstractSmallRestDataSource):

    @classmethod
    def get_name(cls):
        return 'units'

    @classmethod
    def get_title(cls):
        return 'Units'

    @classmethod
    def get_schema(cls, unused_app_context, unused_catch_and_log,
                   unused_source_context):
        reg = schema_fields.FieldRegistry(
            'Units',
            description='Sets of lessons providing course content')
        reg.add_property(schema_fields.SchemaField(
            'unit_id', 'Unit ID', 'string',
            description='Key uniquely identifying this particular unit'))
        reg.add_property(schema_fields.SchemaField(
            'title', 'Title', 'string',
            description='Human-readable title describing the unit'))
        reg.add_property(schema_fields.SchemaField(
            'props', 'Properties', 'object',
            'Set of key/value additional properties, not further defined.'))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def fetch_values(cls, app_context, *args, **kwargs):
        course = courses.Course(handler=None, app_context=app_context)
        units = course.get_units_of_type(verify.UNIT_TYPE_UNIT)
        ret = []
        for unit in units:
            ret.append({
                'unit_id': str(unit.unit_id),
                'title': unit.title,
                'props': unit.properties,
            })
        return ret, 0


class LessonsDataSource(data_sources.AbstractSmallRestDataSource):

    @classmethod
    def get_name(cls):
        return 'lessons'

    @classmethod
    def get_title(cls):
        return 'Lessons'

    @classmethod
    def exportable(cls):
        return True

    @classmethod
    def get_schema(cls, unused_app_context, unused_catch_and_log,
                   unused_source_context):
        reg = schema_fields.FieldRegistry(
            'Lessons',
            description='Sets of lessons providing course content')
        reg.add_property(schema_fields.SchemaField(
            'lesson_id', 'Unit ID', 'string',
            description='Key uniquely identifying which lesson this is'))
        reg.add_property(schema_fields.SchemaField(
            'unit_id', 'Unit ID', 'string',
            description='Key uniquely identifying unit lesson is in'))
        reg.add_property(schema_fields.SchemaField(
            'title', 'Title', 'string',
            description='Human-readable title describing the unit'))
        reg.add_property(schema_fields.SchemaField(
            'scored', 'Scored', 'boolean',
            description='Boolean: Whether questions in this lesson count '
            'for scoring.'))
        reg.add_property(schema_fields.SchemaField(
            'has_activity', 'Has Activity', 'boolean',
            description='Boolean: does this lesson contain an activity?'))
        reg.add_property(schema_fields.SchemaField(
            'activity_title', 'Activity Title', 'string',
            description='Title of the activity (if lesson has an activity)'))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def fetch_values(cls, app_context, *args, **kwargs):
        course = courses.Course(handler=None, app_context=app_context)
        lessons = course.get_lessons_for_all_units()
        ret = []
        for lesson in lessons:
            ret.append({
                'lesson_id': str(lesson.unit_id),
                'unit_id': str(lesson.unit_id),
                'title': lesson.title,
                'scored': lesson.scored,
                'has_activity': lesson.has_activity,
                'activity_title': lesson.activity_title,
            })
        return ret, 0


class StudentAssessmentScoresDataSource(
    data_sources.AbstractDbTableRestDataSource):
    """Unpack student assessment scores from student record.

    NOTE: Filtering/ordering, if present, will be done based on Student
    attributes, not scores.  (The scores are in an encoded string in a
    field which is not indexed anyhow.)  The only meaningful field to
    index or filter on is enrolled_on.
    """

    @classmethod
    def get_name(cls):
        return 'assessment_scores'

    @classmethod
    def get_title(cls):
        return 'Assessment Scores'

    @classmethod
    def get_context_class(cls):
        return data_sources.DbTableContext

    @classmethod
    def get_schema(cls, unused_app_context, unused_catch_and_log,
                   unused_source_context):
        reg = schema_fields.FieldRegistry('Unit',
                                          description='Course sub-components')
        reg.add_property(schema_fields.SchemaField(
            'user_id', 'User ID', 'string',
            description='Student ID encrypted with a session-specific key'))
        reg.add_property(schema_fields.SchemaField(
            'id', 'Unit ID', 'string',
            description='ID of assessment for this score.'))
        reg.add_property(schema_fields.SchemaField(
            'title', 'Title', 'string',
            description='Title of the assessment for this score.'))
        reg.add_property(schema_fields.SchemaField(
            'score', 'Score', 'integer',
            description='Value from 0 to 100 indicating % correct.'))
        reg.add_property(schema_fields.SchemaField(
            'weight', 'Weight', 'number',
            description='Weight applied to the score for computing total '
            'grade.'))
        reg.add_property(schema_fields.SchemaField(
            'attempted', 'Attempted', 'boolean',
            description='Whether the assessment was attempted.'))
        reg.add_property(schema_fields.SchemaField(
            'completed', 'Completed', 'boolean',
            description='Whether the assessment was completed.'))
        reg.add_property(schema_fields.SchemaField(
            'human_graded', 'Human Graded', 'boolean',
            description='Score is from a human (vs. automatic) grading.'))
        reg.add_property(schema_fields.SchemaField(
            'assessment_rank', 'Assessment Rank', 'integer',
            description='Rank of assessment from zero to number of assessments '
            '- 1, in order by total score achieved by all students taking that '
            'assessment.'))
        reg.add_property(schema_fields.SchemaField(
            'user_rank', 'User Rank', 'integer',
            description='Rank of student from zero to number of students '
            '- 1, in order by total score achieved on all assessments taken '
            'by that student.'))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def get_entity_class(cls):
        return models.Student

    @classmethod
    def _postprocess_rows(cls, app_context, source_context,
                          unused_schema, unused_log, unused_page_number,
                          students):
        transform_fn = cls._build_transform_fn(source_context)

        with utils.Namespace(app_context.get_namespace_name()):
            course = courses.Course(handler=None, app_context=app_context)
            students_with_scores = [s for s in students if s.scores]
            student_scores = []
            for student in students_with_scores:
                scores = course.get_all_scores(student)
                for score in scores:
                    if not score['attempted']:
                        continue
                    # user_id is PII and must be encoded to obscure its value.
                    score['user_id'] = transform_fn(student.user_id)
                    student_scores.append(score)

            # Provide a ranking by student, 0 ... #students, low to high.
            scored_students = {}
            for score in student_scores:
                current_score = scored_students.get(score['user_id'], 0)
                scored_students[score['user_id']] = current_score + (
                    score['weight'] * score['score'])
            ranked_students = {kv[0]: rank for rank, kv in
                               enumerate(
                                   sorted(scored_students.items(),
                                          lambda i1, i2: cmp(i1[1], i2[1])))}

            # Provide a ranking by assessment, 0 ... #assessments, low to high
            scored_assessments = {}
            for score in student_scores:
                title = score['title']
                if title not in scored_assessments:
                    scored_assessments[title] = []
                scored_assessments[title].append(
                    score['weight'] * score['score'])
            for title in scored_assessments:
                avg = (sum(scored_assessments[title]) * 1.0 /
                       len(scored_assessments[title]))
                scored_assessments[title] = avg
            ranked_assessments = {kv[0]: rank for rank, kv in
                                  enumerate(
                                      sorted(scored_assessments.items(),
                                             lambda i1, i2: cmp(i1[1], i2[1])))}

            for score in student_scores:
                score['user_rank'] = ranked_students[score['user_id']]
                score['assessment_rank'] = ranked_assessments[score['title']]
            return student_scores


class LabelsDataSource(data_sources.AbstractSmallRestDataSource):

    @classmethod
    def get_name(cls):
        return 'labels'

    @classmethod
    def get_title(cls):
        return 'Labels'

    @classmethod
    def exportable(cls):
        return True

    @classmethod
    def get_schema(cls, app_context, log, source_context):
        reg = schema_fields.FieldRegistry(
            'Labels',
            description='All labels used in course')
        reg.add_property(schema_fields.SchemaField(
            'label_id', 'Label ID', 'string',
            description='Key uniquely identifying this particular label'))
        reg.add_property(schema_fields.SchemaField(
            'title', 'Title', 'string',
            description='Human-readable title for the label'))
        reg.add_property(schema_fields.SchemaField(
            'description', 'Description', 'string',
            description='Description for the label.'))
        reg.add_property(schema_fields.SchemaField(
            'type', 'Type', 'string',
            description='Sub-type of label indicating what this kind of '
            'label is used for.  E.g., setting track through a course or '
            'selecting a display language.'))
        reg.add_property(schema_fields.SchemaField(
            'user_editable', 'User Editable', 'boolean',
            description='Set to true if regular users are permitted to '
            'set/remove labels of this type.'))
        reg.add_property(schema_fields.SchemaField(
            'system_editable', 'System Editable', 'boolean',
            description='Set to true if only admin users are permitted to '
            'set/remove labels of this type.'))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def fetch_values(cls, app_context, source_context, schema, log,
                     page_number):
        ret = []
        for label in models.LabelDAO.get_all_iter():
            label_type = None
            for label_type in models.LabelDTO.LABEL_TYPES:
                if label_type.type == label.type:
                    break
            user_editable = (
                label_type in models.LabelDTO.USER_EDITABLE_LABEL_TYPES)
            system_editable = (
                label_type in models.LabelDTO.SYSTEM_EDITABLE_LABEL_TYPES)

            ret.append({
                'label_id': str(label.id),
                'title': label.title,
                'description': label.description,
                'type': label_type.name,
                'user_editable': user_editable,
                'system_editable': system_editable,
                })
        return ret, 0


class AdditionalFieldNamesEntity(models.BaseEntity):
    SINGLETON_KEY_NAME = 'singleton'

    data = db.TextProperty()


class AdditionalFieldNamesDTO(object):
    ADDITIONAL_FIELD_NAMES = 'additional_field_names'

    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict
        self._additional_field_names = set(
            transforms.loads(self.dict.get(self.ADDITIONAL_FIELD_NAMES, '{}')))

    @property
    def additional_field_names(self):
        return frozenset(self._additional_field_names)

    @additional_field_names.setter
    def additional_field_names(self, names_set):
        # Maintain in-memory representation in parallel w/ persisted dict.
        self._additional_field_names = names_set
        self.dict[self.ADDITIONAL_FIELD_NAMES] = transforms.dumps(
            list(self._additional_field_names))


class AdditionalFieldNamesDAO(models.BaseJsonDao):
    DTO = AdditionalFieldNamesDTO
    ENTITY = AdditionalFieldNamesEntity
    ENTITY_KEY_TYPE = models.BaseJsonDao.EntityKeyTypeName

    @classmethod
    def get_or_default(cls):
        ret = cls.load(AdditionalFieldNamesEntity.SINGLETON_KEY_NAME)
        if not ret:
            ret = AdditionalFieldNamesDTO(
                AdditionalFieldNamesEntity.SINGLETON_KEY_NAME, {})
        return ret

    @classmethod
    def get_field_names(cls):
        return cls.get_or_default().additional_field_names

    @classmethod
    def update_additional_field_names(cls, additional_field_names):
        dto = cls.get_or_default()
        dto.additional_field_names |= set(additional_field_names)
        cls.save(dto)

    @classmethod
    def user_added_callback(cls, user_id, timestamp):
        student = models.Student.get_by_user_id(user_id)
        if not student:
            logging.warning(
                'Could not load student for user ID %s.  Either ' % user_id +
                'student added and removed themselves very very '
                'quickly, or something is badly wrong.')
            return
        additional_field_names = [
            key_value_2_tuple[0] for key_value_2_tuple in
            transforms.loads(student.additional_fields or '{}')]
        cls.update_additional_field_names(additional_field_names)


class StudentsDataSource(data_sources.AbstractDbTableRestDataSource):

    @classmethod
    def get_entity_class(cls):
        return models.Student

    @classmethod
    def get_name(cls):
        return 'students'

    @classmethod
    def get_title(cls):
        return 'Students'

    @classmethod
    def exportable(cls):
        return True

    @classmethod
    def get_default_chunk_size(cls):
        return 100

    @classmethod
    def get_schema(cls, app_context, log, source_context):
        """Override default entity-based schema to reflect our upgrades.

        In the entity, labels are stored as a single string property,
        rather than an arraylist of string or integer for backward
        compatibility.  Current (2014-12-05) usage is that the 'labels'
        property is a stringified representation of a list of IDs
        to LabelEntity.  On export, we convert the string to an array
        of string to permit easier correlation from student labels to
        exported LabelEntity items.

        We provide external references to labels in preference to simply
        resolving the labels, because of potential data bloat (minor) and
        to avoid any future complications due to expansion of the role
        of labels (as was seen when labels-as-language-indicator was
        added).

        Args:
          app_context: Standard CB application context object
          log: a catch_and_log object for reporting any exceptions.
             Not used here, but useful for data source types that are
             dynamically generated, rather than statically coded.
        Returns:
          A JSON schema describing contents.  A dict as produced by
          FieldRegistry.get_json_schema_dict().
        """
        clazz = cls.get_entity_class()
        if source_context.send_uncensored_pii_data:
            registry = entity_transforms.get_schema_for_entity_unsafe(clazz)
            registry.add_property(schema_fields.SchemaField(
                'email', 'Email', 'string',
                optional=True,
                description='Email address for this Student.'))
        else:
            registry = entity_transforms.get_schema_for_entity(clazz)
        ret = registry.get_json_schema_dict()['properties']

        # Scores are deprecated now that regularized scores are available
        # in StudentAggregation data source.
        if 'scores' in ret:
            del ret['scores']

        # We are replacing the labels string with a version that shows
        # labels as separate items so that the amount of insanity
        # required in BigQuery SQL is minimized.
        ret['labels'] = schema_fields.FieldArray(
          'labels', 'Labels',
          description='Labels on students',
          item_type=schema_fields.SchemaField(
            'label', 'Label', 'string',
            description='ID of a LabelEntity applied to a student')
          ).get_json_schema_dict()

        # If a course owner has allowed some or all portions of
        # 'additional_fields'...
        if 'additional_fields' in ret:

            # Send additional fields as a list of key/value pairs
            additional_field = schema_fields.FieldRegistry('additional_field')
            additional_field.add_property(schema_fields.SchemaField(
                'name', 'Name', 'string',
                description='HTML form field name.  Not necessarily unique.'))
            additional_field.add_property(schema_fields.SchemaField(
                'value', 'Value', 'string',
                description='HTML form field value.'))
            ret['additional_fields'] = schema_fields.FieldArray(
                'additional_fields', 'Additional Fields',
                item_type=additional_field,
                description='List of name/value pairs entered on the '
                'course registration form.  Note that for names are not '
                'necessarily unique.  E.g., a group of checkboxes for '
                '"select all reasons you are taking this course" may well '
                'all have the same name.').get_json_schema_dict()

            # And as separate fields named by the name of the field.  Values
            # always go as strings, since we don't have a good way to specify
            # the schema for these items.
            field_names = AdditionalFieldNamesDAO.get_field_names()
            if field_names:
                registration_fields = schema_fields.FieldRegistry(
                    'registration_fields')
                for field_name in field_names:
                    registration_fields.add_property(schema_fields.SchemaField(
                        field_name, field_name.replace('_', ' ').title(),
                        'string', optional=True))
                ret['registration_fields'] = (
                    registration_fields.get_json_schema_dict())
        return ret

    @classmethod
    def _postprocess_rows(cls, app_context, source_context, schema,
                          log, page_number, rows):
        ret = super(StudentsDataSource, cls)._postprocess_rows(
            app_context, source_context, schema, log, page_number, rows)
        # These don't add any value, and do add substantially to data volume.
        # (The user_id field is what's valuable for matching to other items
        # such as StudentAnswersEntity records.)
        for item in ret:
            if 'key' in item:
                del item['key']
            if 'key_by_user_id' in item:
                del item['key_by_user_id']
            if 'safe_key' in item:
                del item['safe_key']
            if 'scores' in item:
                del item['scores']
            item['labels'] = (
                [x for x in utils.text_to_list(item['labels'])])
            if 'scores' in ret:
                del item['scores']
            if item.get('additional_fields'):
                additional_fields = transforms.loads(item['additional_fields'])
                item['additional_fields'] = [
                    {'name': l[0], 'value': l[1]} for l in additional_fields]
                known_names = AdditionalFieldNamesDAO.get_field_names()
                if known_names:
                    reg_fields = dict(additional_fields)
                    for unknown_name in set(reg_fields.keys()) - known_names:
                        del reg_fields[unknown_name]
                    if reg_fields:
                        item['registration_fields'] = reg_fields

        # Here, run through the Student entities to pick up the email address.
        # Since the email is not stored as an actual property in the entity, but
        # instead is just part of the key, we have to manually extract it.  Note
        # that here we are making the entirely reasonable assumption that the
        # cardinality of the list of Student entity and the dict-of-properties
        # list in 'ret' is the same.
        if source_context.send_uncensored_pii_data:
            for student, output_dict in zip(rows, ret):
                output_dict['email'] = student.email
        return ret


class LabelsOnStudentsGenerator(jobs.AbstractCountingMapReduceJob):

    @staticmethod
    def get_description():
        return 'students by track'

    @staticmethod
    def entity_class():
        return models.Student

    @staticmethod
    def map(student):
        for label_id_str in utils.text_to_list(student.labels):
            yield (label_id_str, 1)


class LabelsOnStudentsDataSource(data_sources.AbstractRestDataSource):

    @staticmethod
    def required_generators():
        return [LabelsOnStudentsGenerator]

    @classmethod
    def get_name(cls):
        return 'labels_on_students'

    @classmethod
    def get_title(cls):
        return 'Students by Track'

    @classmethod
    def get_default_chunk_size(cls):
        return 0  # Meaning we don't need pagination

    @classmethod
    def get_context_class(cls):
        return data_sources.NullContextManager

    @classmethod
    def get_schema(cls, app_context, log, source_context):
        reg = schema_fields.FieldRegistry(
            'Students By Label',
            description='Count of students marked with each label')
        reg.add_property(schema_fields.SchemaField(
            'title', 'Title', 'string',
            description='Name for this label'))
        reg.add_property(schema_fields.SchemaField(
            'description', 'Description', 'string',
            description='Human-readable text describing the label'))
        reg.add_property(schema_fields.SchemaField(
            'type', 'Type', 'string',
            description='Title of label group to which this label belongs.'))
        reg.add_property(schema_fields.SchemaField(
            'count', 'Count', 'integer',
            description='Number of students with this label applied'))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def fetch_values(cls, app_context, source_context, schema, log, page_number,
                     labels_on_students_job):
        label_counts = jobs.MapReduceJob.get_results(labels_on_students_job)
        counts = {int(x[0]): int(x[1]) for x in label_counts}
        type_titles = {lt.type: lt.title for lt in models.LabelDTO.LABEL_TYPES}
        ret = []
        for label in models.LabelDAO.get_all():
            ret.append({
                'title': label.title,
                'description': label.description,
                'type': type_titles[label.type],
                'count': counts.get(label.id, 0),
                })
        return ret, 0
