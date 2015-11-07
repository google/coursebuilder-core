# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Handlers for generating various frontend pages."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import collections

from models import courses
from models import custom_modules
from models import custom_units
from models import models
from models import progress
from models import resources_display
from models import review
from models import roles


class StudentCourseView(object):
    """A class that gives access to course, enforcing student permissions."""

    def __init__(self, course, student):
        self.course = course
        self.student = student

        availability = course.get_course_availability()
        self.units_by_unit_id = None

    def _get_units(self):
        if self.units_by_unit_id is None:
            if self.student:
                units = self.course.get_track_matching_student(self.student)
            else:
                units = self.course.get_units()

            self.units_by_unit_id = collections.OrderedDict()
            for unit in units:
                if not self.course.is_unit_available(unit):
                    continue
                self.units_by_unit_id[str(unit.unit_id)] = unit

        return self.units_by_unit_id

    def get_units(self):
        if roles.Roles.is_course_admin(self.course.app_context):
            return self.course.get_units()
        return self._get_units().values()

    def get_lessons(self, unit_id):
        if roles.Roles.is_course_admin(self.course.app_context):
            return self.course.get_lessons(unit_id)

        if not str(unit_id) in self._get_units():
            return []

        lessons = []
        unit = self.course.find_unit_by_id(unit_id)
        for lesson in self.course.get_lessons(unit_id):
            if not self.course.is_lesson_available(unit, lesson):
                continue
            lessons.append(lesson)
        return lessons


def is_progress_recorded(handler, student):
    if student.is_transient:
        return False
    if handler.can_record_student_events():
        return True
    course = handler.get_course()
    units = handler.get_track_matching_student(student)
    for unit in units:
        if unit.manual_progress:
            return True
        for lesson in course.get_lessons(unit.unit_id):
            if lesson.manual_progress:
                return True
    return False


Displayability = collections.namedtuple(
    'Displayability', [
        'is_displayed',  # Whether this element should be available at all.
        'is_link_displayed',  # Whether title is a clickable link to content.
        'is_available_to_students',  # For annotation in admin-only views.
        'is_available_to_visitors'],  # For annotation in admin-only views.
    )


class OutlineElement(dict):
    """Plain-old-data container for course outline elements.

    Note that this contains only facts and derived facts about the course
    outline; it does _not_ contain any opinions about displaying these
    contents.  Thus, this class does not contain any information about CSS,
    or whether elements should be rendered as <div> or <li>, or similar.
    """

    def __init__(self):
        super(OutlineElement, self).__init__(self)
        self.contents = []

    # Save ourselves some typing when using completion states.
    PROGRESS_NOT_STARTED = (
        progress.UnitLessonCompletionTracker.NOT_STARTED_STATE)
    PROGRESS_IN_PROGRESS = (
        progress.UnitLessonCompletionTracker.IN_PROGRESS_STATE)
    PROGRESS_COMPLETED = progress.UnitLessonCompletionTracker.COMPLETED_STATE

    ALLOWED_FIELDS = [
        'id',  # ID of Unit13 or Lesson13
        'contents',  # Array of OutlineElement sub-items, possibly empty.
        'is_active',  # True if outline is for page showing this item's content.
        'kind',  # {'unit', 'assessment', 'link', 'lesson', 'peer_review'}
        'title',  # Unit/lesson title string.
        'link',  # Optional: URL to this item's primary display page
        'link_is_last_page_visited',  # Optional: If link is present, whether
            # that was the last page visited by the logged-in student.
        'description',  # Optional: string containing description
        'parent_id',  # Optional: ID of containing unit
        'prev_link',  # Optional: URL of previous sibling at same level.
        'next_link',  # Optional: URL of next sibling at same level
        'is_progress_recorded',  # True or False.
        'progress',  # Optional: PROGRESS_{NOT_STARTED,IN_PROGRESS,COMPLETED}
        'is_available_to_students',  # True/False; Meaningful only to admins
        'is_available_to_visitors',  # True/False; Meaningful only to admins
        ]

    def __setattr__(self, name, value):
        if name not in self.ALLOWED_FIELDS:
            raise ValueError('Name %s not allowed in OutlineElement' % name)
        super(OutlineElement, self).__setitem__(name, value)

    def __getattr__(self, name):
        try:
            return self.__getitem__(name)
        except KeyError:
            return None


class CourseOutline(object):
    """Produces an iterable list of OutlineElement course outline elements.

    The list of items is adjusted according to permissions, course settings,
    course availability policy, unit/lesson availability policy, user login
    status, and specific kind of outline desired (overall outline, or
    unit/lesson-specific).

    The elements available are redacted to only those components which are
    visible in the current situation.  E.g., course and site admins will have
    all or nearly all of the Optional items populated; visitors who are not
    even registered students will have a more limited view, possibly reduced
    to as little as an empty list for a course which requires registration.

    This contains only information related to structure and permissions
    related to visibility of that structure.  Display-level concerns are left
    to the caller.  E.g., descriptions are always added.  If the display layer
    wants to suppress descriptions due to lack of space in a UI, that's up to
    that layer to accomplish.  Objects passed out of this function is entirely
    derived, and so can be modified in place without making defensive copies.

    TODO: Eventually make results of this class available as a REST service.
    """

    def __init__(self, handler, student, unit=None, lesson_or_assessment=None):
        self._handler = handler
        self._course = handler.get_course()
        self._reviews_processor = self._course.get_reviews_processor()
        self._app_context = self._course.app_context
        self._student = student
        self._student_preferences = (
            models.StudentPreferencesDAO.load_or_default())
        self._settings = self._app_context.get_environ()

        self._outer_id = self._inner_id = None
        if unit:
            self._outer_id = unit.unit_id
            if lesson_or_assessment:
                if hasattr(lesson_or_assessment, 'lesson_id'):
                    self._inner_id = lesson_or_assessment.lesson_id
                else:
                    self._inner_id = lesson_or_assessment.unit_id

        # Find out course availability policy.  Mostly this is for
        # distinguishing whether we are in 'registration_required' versus
        # 'registration_optional' or 'public'; in the former case, unit and
        # lesson policy governs visibility/linkability; in the latter, every
        # item is available.
        self._course_availability = (
            self._course.get_course_availability())

        # Whether current user is permitted to see drafts.  This is a
        # permission granted to lesser admins who still need to see course
        # content in pages showing student views.
        self._can_see_drafts = custom_modules.can_see_drafts(self._app_context)

        # Sometimes we do want to show progress, sometimes not.  Use common
        # function also referenced elsewhere to decide this.  Note that
        # assessment progress is always recorded due to saving answers/scores;
        # is_progress_recorded refers to event-based progress items.
        self._is_progress_recorded = is_progress_recorded(handler, student)
        if student and not student.is_transient:
            self._tracker = self._course.get_progress_tracker()
            self._progress = self._tracker.get_or_create_progress(student)
        else:
            self._tracker = None
            self._progress = None

        self._contents = []
        self._traverse_course()

    @property
    def contents(self):
        return self._contents

    def find_element(self, ids):
        element = self
        for element_id in ids:
            found_element = False
            for sub_element in element.contents:
                if sub_element.id == element_id:
                    found_element = True
                    element = sub_element
                    break
            if not found_element:
                return None
        return element

    def _traverse_course(self):
        units = self._handler.get_track_matching_student(self._student)

        for unit in units:
            # If this is a pre/post assessment, defer and let the unit it's
            # in add the item.
            if unit.is_assessment() and self._course.get_parent_unit(
                unit.unit_id):
                continue

            # If item is not available to this user, skip it.
            displayability = self._determine_displayability(unit)
            if not displayability.is_displayed:
                continue

            e = []
            if unit.is_unit():
                e = self._build_elements_for_unit(unit, displayability)
            elif unit.is_link():
                e = self._build_elements_for_link(unit, displayability)
            elif (unit.is_assessment() and
                  not self._course.get_parent_unit(unit)):
                e = self._build_elements_for_assessment(unit, displayability)
            elif unit.is_custom_unit():
                e = self._build_elements_for_custom_unit(unit, displayability)
            self._contents.extend(e)

    def _determine_displayability(self, course_element,
                                  parent_displayability=None):
        """Determine whether an element is visible and/or linkable.

        Here, we are relying on a behavior of the rest of this class, to wit:
        If the parent is not displayable, then this function is not called to
        establish displayability of any contents.  E.g., suppose we have a
        registration-required course, and a unit that is private, and does not
        permit display of its title on the syllabus.  No lesson or pre/post
        assessment in that unit can have its title displayed since the unit
        is suppressed.  Rather than writing some seriously nasty convoluted
        logic here, we just presume the rest of the world will be wise enough
        to just not call us to ask about it.

        Args:
          course_elment: A unit or lesson object.  Anything that can respond to
              .availability -> public, private, use-course and
              .shown_when_unavailable -> True/False
          parent_element: Displayability instance, as determined by this
              function, for the parent of the element, or None if there is no
              parent.
        Returns:
          A Displayability instance.
        """

        is_displayed = False
        is_link_displayed = False
        is_available_to_students = False
        is_available_to_visitors = False

        # Course being set to private trumps permissions in units.  This
        # is because we need to have one single place where we can force
        # the course offline without any "well, except when...." cases.
        if self._course_availability == courses.COURSE_AVAILABILITY_PRIVATE:
            pass

        # If course is browse-only or browse-available, every element which
        # does not explicitly make itself private is available.
        elif self._course_availability in (
            courses.COURSE_AVAILABILITY_REGISTRATION_OPTIONAL,
            courses.COURSE_AVAILABILITY_PUBLIC):

            if course_element.availability == courses.AVAILABILITY_UNAVAILABLE:
                if course_element.shown_when_unavailable:
                    is_displayed = True
                    is_link_displayed = False
                    is_available_to_students = False
                    is_available_to_visitors = False
            if course_element.availability in (courses.AVAILABILITY_AVAILABLE,
                                               courses.AVAILABILITY_COURSE):
                is_displayed = True
                is_link_displayed = True
                is_available_to_students = True
                is_available_to_visitors = True

        # If course is registration-only, then availablity is conditional on
        # whether the current student is registered.
        elif self._course_availability == (
            courses.COURSE_AVAILABILITY_REGISTRATION_REQUIRED):
            if course_element.availability == courses.AVAILABILITY_UNAVAILABLE:
                if course_element.shown_when_unavailable:
                    is_displayed = True
                    is_link_displayed = False
                    is_available_to_students = False
                    is_available_to_visitors = False

            elif course_element.availability == courses.AVAILABILITY_AVAILABLE:
                is_displayed = True
                is_link_displayed = True
                is_available_to_students = True
                is_available_to_visitors = True

            elif course_element.availability == courses.AVAILABILITY_COURSE:
                if self._student.is_transient:
                    is_displayed = True
                    is_link_displayed = False
                    is_available_to_students = True
                    is_available_to_visitors = False
                else:
                    is_displayed = True
                    is_link_displayed = True
                    is_available_to_students = True
                    is_available_to_visitors = False

        # If the parent is not available in display/link mode, then neither
        # is the child.
        if parent_displayability:
            is_displayed = min(
                parent_displayability.is_displayed,
                is_displayed)
            is_link_displayed = min(
                parent_displayability.is_link_displayed,
                is_link_displayed)
            is_available_to_students = min(
                parent_displayability.is_available_to_students,
                is_available_to_students)
            is_available_to_visitors = min(
                parent_displayability.is_available_to_visitors,
                is_available_to_visitors)

        # Users with this permission (which includes course and site admins)
        # can always see and navigate to every item in student-view contexts.
        # This trumps even the course being private, since admins need to be
        # able to actually see what students _would_ see if they could.
        if self._can_see_drafts:
            is_displayed = True
            is_link_displayed = True

        return Displayability(is_displayed,
                              is_link_displayed,
                              is_available_to_students,
                              is_available_to_visitors)

    def _build_element_common(self, element, displayability, link,
                              parent_element=None):
        if not displayability.is_displayed:
            raise ValueError('Should not add non-displayble elements')
        ret = OutlineElement()
        ret.is_available_to_students = displayability.is_available_to_students
        ret.is_available_to_visitors = displayability.is_available_to_visitors
        if hasattr(element, 'lesson_id'):
            ret.id = element.lesson_id
            ret.title = resources_display.display_lesson_title(
                parent_element, element, self._app_context)
        else:
            ret.id = element.unit_id
            if element.is_unit():
                ret.title = resources_display.display_unit_title(
                    element, self._app_context)
            else:
                ret.title = element.title

        if parent_element:
            ret.is_active = (ret.id == self._inner_id)
            ret.parent_id = parent_element.unit_id
        else:
            ret.is_active = (ret.id == self._outer_id)

        if displayability.is_link_displayed:
            ret.link = link
            if (self._student_preferences and
                self._student_preferences.last_location and link and
                self._student_preferences.last_location.endswith(link)):
                ret.link_is_last_page_visited = True

        if hasattr(element, 'description'):
            ret.description = element.description
        return ret

    def _build_elements_for_unit(self, unit, unit_displayability):
        element = self._build_element_common(
            unit, unit_displayability, 'unit?unit=%s' % unit.unit_id)
        element.kind = 'unit'
        if self._is_progress_recorded:
            element.is_progress_recorded = True
            element.progress = self._tracker.get_unit_status(self._progress,
                                                             unit.unit_id)

        if not unit.show_contents_on_one_page:
            if unit.pre_assessment:
                assessment = self._course.find_unit_by_id(unit.pre_assessment)
                assessment_displayability = self._determine_displayability(
                    assessment, unit_displayability)
                if assessment_displayability.is_displayed:
                    element.contents.extend(
                        self._build_elements_for_assessment(
                            assessment, assessment_displayability, unit))
            for lesson in self._course.get_lessons(unit.unit_id):
                lesson_displayability = self._determine_displayability(
                    lesson, unit_displayability)
                if lesson_displayability.is_displayed:
                    element.contents.extend(
                        self._build_elements_for_lesson(
                            unit, lesson, lesson_displayability))
            if unit.post_assessment:
                assessment = self._course.find_unit_by_id(unit.post_assessment)
                assessment_displayability = self._determine_displayability(
                    assessment, unit_displayability)
                if assessment_displayability.is_displayed:
                    element.contents.extend(
                        self._build_elements_for_assessment(
                            assessment, assessment_displayability, unit))

            # Stitch together previous/next links of sibling items, but only
            # those which have links - private items don't get linked up.
            prev_element = None
            for sub_element in element.contents:
                if sub_element.link:
                    if prev_element:
                        prev_element.next_link = sub_element.link
                        sub_element.prev_link = prev_element.link
                    prev_element = sub_element
        return [element]

    def _build_elements_for_link(self, unit, displayability):
        # Cast href to string to get rid of possible LazyTranslator wrapper.
        link = str(unit.href) if unit.href else None
        element = self._build_element_common(unit, displayability, link)
        element.kind = 'link'
        return [element]

    def _build_elements_for_assessment(self, unit, displayability,
                                    owning_unit=None):
        ret = []
        if owning_unit:
            link = 'unit?unit=%s&assessment=%s' % (
                owning_unit.unit_id, unit.unit_id)
        else:
            link = 'assessment?name=%s' % unit.unit_id
        element = self._build_element_common(unit, displayability, link,
                                             owning_unit)
        element.kind = 'assessment'
        ret.append(element)
        if not self._student.is_transient:
            element.is_progress_recorded = True
            if self._tracker:
                if self._tracker.is_assessment_completed(self._progress,
                                                         unit.unit_id):
                    element.progress = OutlineElement.PROGRESS_COMPLETED
                else:
                    element.progress = OutlineElement.PROGRESS_NOT_STARTED

        ret.extend(self._build_elements_for_assessment_review(
            unit, displayability))
        return ret

    def _build_elements_for_assessment_review(self, unit, displayability):
        # Don't bother showing outline element for the peer-review step of the
        # assessment unless we actually have a logged-in student.
        if not unit.needs_human_grader():
            return []

        # Do want to let course admins that the review steps will appear to
        # registered students, even if the admin account is not a registered
        # student him/her-self.
        if (self._student.is_transient and
            not roles.Roles.is_course_admin(self._app_context)):
            return []

        ret = OutlineElement()
        ret.id = unit.unit_id
        ret.parent_id = unit.unit_id
        ret.kind = 'peer_review'
        ret.is_available_to_students = displayability.is_available_to_students
        ret.is_available_to_visitors = displayability.is_available_to_visitors
        # I18N: Displayed in the course contents page. Indicates a page to
        # which students can go to review other students' assignments.
        ret.title = self._handler.gettext('Review peer assignments')

        if not self._student.is_transient:
            ret.is_progress_recorded = True
            # Linkability is defined by whether the student has submitted
            # their own response to the assessment.  After they've done that,
            # only then they can review other students' work.
            if self._reviews_processor.does_submission_exist(
                unit.unit_id, self._student.get_key()):
                review_steps = self._reviews_processor.get_review_steps_by(
                    unit.unit_id, self._student.get_key())
                workflow = unit.workflow
                review_min_count = workflow.get_review_min_count()

                ret.progress = review.ReviewUtils.get_review_progress(
                    review_steps, review_min_count)
                ret.link = "reviewdashboard?unit=%s" % unit.unit_id
            else:
                ret.progress = OutlineElement.PROGRESS_NOT_STARTED
        return [ret]

    def _build_element_for_custom_unit(self, unit, displayability):
        cu = custom_units.UnitTypeRegistry.get(unit.custom_unit_type)
        if not cu:
            return None

        link_dest = self._app_context.canonicalize_url(cu.visible_url(unit))
        element = self._build_element_common(
            unit, displayability, link_dest)
        element.kind = unit.custom_unit_type

        if self._is_progress_recorded:
            element.progress = self._tracker.get_custom_unit_status(
                self._progress, unit.unit_id)
            if element.progress is not None:
                element.is_progress_recorded = True
        return element

    def _build_elements_for_lesson(self, unit, lesson, displayability):
        link = 'unit?unit=%s&lesson=%s' % (unit.unit_id, lesson.lesson_id)
        element = self._build_element_common(lesson, displayability, link, unit)
        element.kind = 'lesson'
        if self._is_progress_recorded:
            element.is_progress_recorded = True
            element.progress = self._tracker.get_lesson_status(
                self._progress, unit.unit_id, lesson.lesson_id)
        return [element]
