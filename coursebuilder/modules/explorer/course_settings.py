from models import courses
from common import schema_fields
from modules.explorer import messages


def register():
    classNames = (
        'inputEx-CombineField gcb-datetime inputEx-fieldWrapper date-only')

    courses.Course.OPTIONS_SCHEMA_PROVIDERS[
        courses.Course.SCHEMA_SECTION_COURSE] += [
            lambda _: schema_fields.SchemaField(
                'course:start_date', 'Displayed Start Date', 'datetime',
                description=messages.COURSE_START_DATE_DESCRIPTION,
                extra_schema_dict_values={'className': classNames},
                optional=True, i18n=False,
            ),
            lambda _: schema_fields.SchemaField(
                'course:end_date', 'Displayed End Date', 'datetime',
                description=messages.COURSE_END_DATE_DESCRIPTION,
                extra_schema_dict_values={'className': classNames},
                optional=True, i18n=False,
            ),
            lambda _: schema_fields.SchemaField(
                'course:estimated_workload', 'Estimated Workload', 'string',
                description=messages.COURSE_ESTIMATED_WORKLOAD_DESCRIPTION,
                optional=True, i18n=False,
            ),
            lambda _: schema_fields.SchemaField(
                'course:category_name', 'Category', 'string',
                description=messages.COURSE_CATEGORY_DESCRIPTION,
                optional=True, i18n=False,
            ),
        ]
