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

from common import schema_fields
from common import utils
from models import courses
from models import data_sources
from models import models
from models import transforms
from tools import verify


class CourseElementsDataSource(data_sources.AbstractRestDataSource):

    @classmethod
    def get_context_class(cls):
        # Expect at most hundreds of course elements; no need for pagination,
        # so null context is fine.
        return data_sources.NullContextManager

    @classmethod
    def _build_query(cls, *args, **kwargs):
        return None

    @classmethod
    def _acquire_necessary_cursors(cls, *args, **kwargs):
        pass

    @classmethod
    def _sanitize_values(cls, source_context, rows):
        return rows

    @classmethod
    def _transform_to_dict(cls, rows):
        return rows


class AssessmentsDataSource(CourseElementsDataSource):

    @classmethod
    def get_name(cls):
        return 'assessments'

    @classmethod
    def get_schema(cls, unused_app_context, unused_catch_and_log):
        reg = schema_fields.FieldRegistry(
            'Analytics',
            description='Sets of questions determining student skill')
        reg.add_property(schema_fields.SchemaField(
            'unit_id', 'Unit ID', 'integer',
            description='Key uniquely identifying this particular assessment'))
        reg.add_property(schema_fields.SchemaField(
            'title', 'Title', 'string',
            description='Human-readable title describing the assessment'))
        reg.add_property(schema_fields.SchemaField(
            'weight', 'Weight', 'number',
            'Scalar indicating how the results of this assessment are '
            'to be weighted versus the results of peer assessments.'))
        reg.add_property(schema_fields.SchemaField(
            'html_check_answers', 'Check Answers', 'boolean',
            'Whether students may check their answers before submitting '
            'the assessment.'))
        reg.add_property(schema_fields.SchemaField(
            'properties', 'Properties', 'object',
            'Set of key/value additional properties, not further defined.'))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def fetch_values(cls, app_context, *args, **kwargs):
        course = courses.Course(handler=None, app_context=app_context)
        assessments = course.get_units_of_type(verify.UNIT_TYPE_ASSESSMENT)
        ret = []
        for assessment in assessments:
            ret.append({
                'unit_id': assessment.unit_id,
                'title': assessment.title,
                'weight': assessment.weight,
                'html_check_answers': assessment.html_check_answers,
                'properties': assessment.properties})
        return ret


class UnitsDataSource(CourseElementsDataSource):

    @classmethod
    def get_name(cls):
        return 'units'

    @classmethod
    def get_schema(cls, unused_app_context, unused_catch_and_log):
        reg = schema_fields.FieldRegistry(
            'Units',
            description='Sets of lessons providing course content')
        reg.add_property(schema_fields.SchemaField(
            'unit_id', 'Unit ID', 'integer',
            description='Key uniquely identifying this particular unit'))
        reg.add_property(schema_fields.SchemaField(
            'title', 'Title', 'string',
            description='Human-readable title describing the unit'))
        reg.add_property(schema_fields.SchemaField(
            'properties', 'Properties', 'object',
            'Set of key/value additional properties, not further defined.'))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def fetch_values(cls, app_context, *args, **kwargs):
        course = courses.Course(handler=None, app_context=app_context)
        units = course.get_units_of_type(verify.UNIT_TYPE_UNIT)
        ret = []
        for unit in units:
            ret.append({
                'unit_id': unit.unit_id,
                'title': unit.title,
                'properties': unit.properties,
            })
        return ret


class LessonsDataSource(CourseElementsDataSource):

    @classmethod
    def get_name(cls):
        return 'lessons'

    @classmethod
    def get_schema(cls, unused_app_context, unused_catch_and_log):
        reg = schema_fields.FieldRegistry(
            'Lessons',
            description='Sets of lessons providing course content')
        reg.add_property(schema_fields.SchemaField(
            'lesson_id', 'Unit ID', 'integer',
            description='Key uniquely identifying which lesson this is'))
        reg.add_property(schema_fields.SchemaField(
            'unit_id', 'Unit ID', 'integer',
            description='Key uniquely identifying unit lesson is in'))
        reg.add_property(schema_fields.SchemaField(
            'title', 'Title', 'string',
            description='Human-readable title describing the unit'))
        reg.add_property(schema_fields.SchemaField(
            'scored', 'Scored', 'boolean',
            'Boolean: Whether questions in this lesson count for scoring.'))
        reg.add_property(schema_fields.SchemaField(
            'has_activity', 'Has Activity', 'boolean',
            'Boolean: does this lesson contain an activity?'))
        reg.add_property(schema_fields.SchemaField(
            'activity_title', 'Activity Title', 'string',
            'Title of the activity (if lesson has an activity)'))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def fetch_values(cls, app_context, *args, **kwargs):
        course = courses.Course(handler=None, app_context=app_context)
        lessons = course.get_lessons_for_all_units()
        ret = []
        for lesson in lessons:
            ret.append({
                'lesson_id': lesson.unit_id,
                'unit_id': lesson.unit_id,
                'title': lesson.title,
                'scored': lesson.scored,
                'has_activity': lesson.has_activity,
                'activity_title': lesson.activity_title,
            })
        return ret


# TODO(mgainer): Provide a REST service to list the locations from which
# questions/question groups are referenced within unit/assessment/lesson
# HTML contents.  Do this when we decide how to handle question answer
# entities (which use IDs referencing the point-of-use of questions or
# question groups in unit/assessment/lesson, rather than the question ID
# itself.


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
    def get_context_class(cls):
        return data_sources.DbTableContext

    @classmethod
    def get_schema(cls, unused_app_context, unused_catch_and_log):
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
            'weight', 'Weight', 'integer',
            description='Value from 0 to 100 indicating % correct.'))
        reg.add_property(schema_fields.SchemaField(
            'completed', 'Completed', 'boolean',
            description='Whether the assessment was completed.'))
        reg.add_property(schema_fields.SchemaField(
            'human_graded', 'Human Graded', 'boolean',
            description='Score is from a human (vs. automatic) grading.'))
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
                    # user_id is PII and must be encoded to obscure its value.
                    score['user_id'] = transform_fn(student.user_id)
                    student_scores.append(score)
            return student_scores


class StudentsDataSource(data_sources.AbstractDbTableRestDataSource):

    @classmethod
    def get_entity_class(cls):
        return models.Student

    @classmethod
    def get_name(cls):
        return 'students'

    @classmethod
    def _postprocess_rows(cls, app_context, source_context, schema,
                          log, page_number, rows):
        ret = super(StudentsDataSource, cls)._postprocess_rows(
            app_context, source_context, schema, log, page_number, rows)
        # These don't add any value, and do add substantially to data volume.
        # (The user_id field is what's valuable for matching to other items
        # such as StudentAnswersEntity records.)
        for item in ret:
            del item['key']
            del item['key_by_user_id']
            if 'additional_fields' not in item or not item['additional_fields']:
                item['additional_fields'] = {}
            else:
                item['additional_fields'] = (
                    transforms.nested_lists_as_string_to_dict(
                        item['additional_fields']))
        return ret
