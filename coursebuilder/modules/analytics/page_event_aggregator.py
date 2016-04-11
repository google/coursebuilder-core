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

"""Student aggregate collection of page enter/exit events."""

__author__ = ['Michael Gainer (mgainer@google.com)']

import collections
import urlparse

from common import schema_fields
from models import courses
from models import transforms
from modules.analytics import student_aggregate
from tools import verify


class AbstractPageEventMatcher(object):

    def get_name(self):
        """Return a short string identifying this matcher."""
        raise NotImplementedError()

    def get_path_match(self):
        """Provide the exact portion of a location URL to match.

        E.g., "/unit", "/course", etc.
        """
        raise NotImplementedError()

    def match(self, static_params, query_params):
        """Perform matching on the given query parameters.

        This function is only called if the URL matches on the path
        component.  Return a 2-tuple of name and item_id (as described
        above in PageEvent) if the given params match, or None if they
        do not.

        Args:
          static_params: the value returned from build_static_params(), or None.
          query_params: a dict of URL parameters.
        Returns:
          A 2-tuple of name, item_id or None.
        """
        raise NotImplementedError()

    @classmethod
    def build_static_params(cls, unused_app_context):
        """Build any expensive-to-calculate items at course level.

        If this class needs to pre-calculate any facts that would be expensive
        to regenerate on each call to process_event(), those facts can be
        returned as a single object from this method.  If no such facts are
        required, return None.  This function is called once when each
        map/reduce job starts.  Any type of object may be returned.
        Args:
          unused_app_context: A standard CB application context object.
        Returns:
          Any.
        """
        return None


class PathOnlyMatcher(AbstractPageEventMatcher):

    def __init__(self, name, path_match):
        self._name = name
        self._path_match = path_match

    def get_name(self):
        return self._path_match

    def get_path_match(self):
        return self._path_match

    def match(self, static_params, query_params):
        return (self._name, None)


class AssessmentMatcher(AbstractPageEventMatcher):

    @classmethod
    def get_name(cls):
        return 'assessment'

    @classmethod
    def get_path_match(cls):
        return '/assessment'

    @classmethod
    def match(cls, static_params, query_params):
        if 'name' in query_params:
            return ('assessment', query_params['name'][0])
        return None


class UnitMatcher(AbstractPageEventMatcher):

    @classmethod
    def get_name(cls):
        return 'unit'

    @classmethod
    def get_path_match(cls):
        return '/unit'

    @classmethod
    def match(cls, static_params, query_params):
        if 'lesson' in query_params:
            return 'lesson', query_params['lesson'][0]

        if 'assessment' in query_params:
            # Occurs for pre/post assessment in unit.
            return 'assessment', query_params['assessment'][0]

        # OK, now we get ambiguous.  If we have a unit ID, then either we are
        # going to be returning a lesson or asssessment, depending on what's
        # first in the unit, or just the unit if the unit is marked as
        # show-all-lessons.  Here, we start to realize that the whole reliance
        # on URLs is silly, and we wish that we were actually recording what
        # was shown as part of the event.  Particularly note that we are only
        # best-guessing about what actually showed if we don't have full data,
        # since we are looking at the course now and just believing that the
        # arrangement hasn't changed since the event was emitted.  This is
        # reasonable, but not _necessarily_ true.
        if 'unit' in query_params:
            unit_id = query_params['unit'][0]
        else:
            unit_id = static_params['first_unit_id']

        if unit_id in static_params:
            return static_params[unit_id]

    @classmethod
    def build_static_params(cls, app_context):
        """Provide map of unit ID to result to report for partial unit URLs.

        The result returned by this function is passed in to the map/reduce
        job aggregating event data on a per-Student basis.  It is retrieved
        just above via "units_info = params['unit_page_disambiguation']".
        When a URL referencing a unit is not fully specified, the first
        item in the unit is shown.  This function pre-computes the
        result that get_mapper_result() should return when it has only
        the unit ID provided.

        Args:
            app_context: Standard CB application context object.
        Returns:
            A map from Unit ID to a 2-tuple of page-type name and ID.
        """

        ret = {}
        course = courses.Course(None, app_context=app_context)
        for unit in course.get_units_of_type(verify.UNIT_TYPE_UNIT):
            if 'first_unit_id' not in ret:
                ret['first_unit_id'] = str(unit.unit_id)
            lessons = course.get_lessons(unit.unit_id)
            if unit.show_contents_on_one_page:
                ret[unit.unit_id] = ('unit', str(unit.unit_id))
            elif unit.pre_assessment:
                ret[unit.unit_id] = ('assessment', str(unit.pre_assessment))
            elif lessons:
                ret[unit.unit_id] = ('lesson', str(lessons[0].lesson_id))
            elif unit.post_assessment:
                ret[unit.unit_id] = ('assessment', str(unit.post_assessment))
            else:
                ret[unit.unit_id] = ('unit', str(unit.unit_id))
        return ret


class PageEventAggregator(
    student_aggregate.AbstractStudentAggregationComponent):

    _matchers_by_name = {}
    _matchers_by_path = collections.defaultdict(list)

    @classmethod
    def get_name(cls):
        return 'page_event'

    @classmethod
    def get_event_sources_wanted(cls):
        return ['enter-page', 'exit-page', 'tag-youtube-event', 'click-link']

    @classmethod
    def build_static_params(cls, app_context):
        ret = {}
        slug = app_context.get_slug()
        if not slug or slug == '/':
            slug = ''
        ret['slug'] = slug
        for name, matcher in cls._matchers_by_name.iteritems():
            value = matcher.build_static_params(app_context)
            if value:
                ret[name] = value
        return ret

    @classmethod
    def process_event(cls, event, static_params):
        ret = []
        data = transforms.loads(event.data)
        url_parts = urlparse.urlparse(data.get('location', ''))
        query_params = urlparse.parse_qs(url_parts.query)
        path = url_parts.path.replace(static_params['slug'], '')

        for matcher in cls._matchers_by_path.get(path, []):
            matcher_params = static_params.get(matcher.get_name())
            value = matcher.match(matcher_params, query_params)
            if value:
                name, item_id = value
                timestamp = cls._fix_timestamp(event.recorded_on)
                ret.append([name, item_id, timestamp, event.source])
        return ret

    @classmethod
    def produce_aggregate(cls, course, student, static_value, event_items):
        # separate events by location.
        location_events = collections.defaultdict(list)
        for sub_list in event_items:
            for name, item_id, timestamp, source in sub_list:
                location_events[(name, item_id)].append((timestamp, source))

        # Sort events in each location by timestamp.
        for events_list in location_events.itervalues():
            events_list.sort()

        # Cluster events into groups delimited by enter-page and exit-page
        current_view = None
        page_views = []
        for location, events in location_events.iteritems():
            name, item_id = location
            for timestamp, source in events:
                activity = {
                    'action': source,
                    'timestamp': timestamp,
                    }
                if not current_view or source == 'enter-page':
                    current_view = {
                        'name': name,
                        'item_id': item_id,
                        'start': timestamp,
                        'activities': [activity]
                        }
                    page_views.append(current_view)
                else:
                    current_view['activities'].append(activity)
                if source == 'exit-page':
                    current_view['end'] = timestamp
                    current_view = None
        page_views.sort(key=lambda v: v['start'])
        return {'page_views': page_views}

    @classmethod
    def get_schema(cls):
        activity = schema_fields.FieldRegistry('activity')
        activity.add_property(schema_fields.SchemaField(
            'action', 'Action', 'string',
            description='A short string indicating the nature of the event, '
            'such as "enter", "exit", "submit_assessment", "check_answer"'))
        activity.add_property(schema_fields.SchemaField(
            'timestamp', 'Timestamp', 'timestamp',
            description='Timestamp when the event occurred'))

        page_view = schema_fields.FieldRegistry('page_view')
        page_view.add_property(schema_fields.SchemaField(
            'name', 'Name', 'string',
            description='Name of the kind of page being shown.  This is a '
            'short string, such as "unit", "lesson", "enroll", "unenroll", '
            'etc.  The full list of these can be found in '
            'coursebuilder/modules/analytics/student_events.py.'))
        page_view.add_property(schema_fields.SchemaField(
            'item_id', 'Item ID', 'string', optional=True,
            description='Identity of the kind of page in question, if '
            'the page may have more than one instance.  E.g., units and '
            'lessons have IDs; the forum, enroll and unenroll pages do not.'))
        page_view.add_property(schema_fields.SchemaField(
            'start', 'Start', 'timestamp',
            description='Timestamp when the page was entered.'))
        page_view.add_property(schema_fields.SchemaField(
            'end', 'End', 'timestamp', optional=True,
            description='Timestamp when the page was exited.  '
            'Note that this field may be blank if we are missing '
            'the exit event.  Also note that this field may be '
            'extremely misleading - users may leave the page open while '
            'doing other things.  You should arrange to clip this value '
            'at some reasonable maximum, and impute either the average '
            'or the median value when this field is blank.'))
        page_view.add_property(schema_fields.FieldArray(
            'activities', 'Activities', item_type=activity))

        page_views = schema_fields.FieldArray(
            'page_views', 'Page Views', item_type=page_view,
            description='User activity events for this student, grouped by '
            'page enter/exit.')
        return page_views

    @classmethod
    def register_matcher(cls, matcher):
        name = matcher.get_name()
        if name in cls._matchers_by_name:
            raise ValueError(
                'Page event matcher named "%s" already registered.' % name)
        cls._matchers_by_name[name] = matcher
        cls._matchers_by_path[matcher.get_path_match()].append(matcher)

    @classmethod
    def unregister_matcher(cls, matcher):
        name = matcher.get_name()
        if name in cls._matchers_by_name:
            matcher = cls._matchers_by_name[name]
            del cls._matchers_by_name[name]
            for matcher_list in cls._matcher_by_path.itervalues():
                matcher_list.remove(matcher)


def register_base_course_matchers():
    PageEventAggregator.register_matcher(UnitMatcher)
    PageEventAggregator.register_matcher(AssessmentMatcher)
    PageEventAggregator.register_matcher(
        PathOnlyMatcher('course', '/course'))
    PageEventAggregator.register_matcher(
        PathOnlyMatcher('enroll', '/register_matcher'))
    PageEventAggregator.register_matcher(
        PathOnlyMatcher('announcements', '/announcements'))
    PageEventAggregator.register_matcher(
        PathOnlyMatcher('forum', '/forum'))
    PageEventAggregator.register_matcher(
        PathOnlyMatcher('answer', '/answer'))
    PageEventAggregator.register_matcher(
        PathOnlyMatcher('unenroll', '/student/unenroll'))


def unregister_base_course_matchers():
    PageEventAggregator.unregister_matcher(UnitMatcher)
    PageEventAggregator.unregister_matcher(AssessmentMatcher)
    PageEventAggregator.unregister_matcher(
        PathOnlyMatcher('course', '/course'))
    PageEventAggregator.unregister_matcher(
        PathOnlyMatcher('enroll', '/register_matcher'))
    PageEventAggregator.unregister_matcher(
        PathOnlyMatcher('announcements', '/announcements'))
    PageEventAggregator.unregister_matcher(
        PathOnlyMatcher('forum', '/forum'))
    PageEventAggregator.unregister_matcher(
        PathOnlyMatcher('answer', '/answer'))
    PageEventAggregator.unregister_matcher(
        PathOnlyMatcher('unenroll', '/student/unenroll'))
