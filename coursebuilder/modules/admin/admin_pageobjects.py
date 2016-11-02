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

"""Page objects for all-courses admin integration tests for Course Builder."""

__author__ = [
    'Mike Gainer (mgainer@google.com)'
]

import collections
import logging
import re
import time

from modules.admin import enrollments
from selenium.common import exceptions
from selenium.webdriver.common import action_chains
from selenium.webdriver.support import select
from selenium.webdriver.support import expected_conditions

from tests.integration import pageobjects


def _norm_url(url):
    """Returns the supplied URL in "canonical" form for a course URL."""
    url = url.strip()  # No leading/trailing whitespace.
    if not url:
        return '/'  # Special-case 'Power Searching with Google' sample.
    if url[0] != '/':
        url = '/' + url  # Prepend missing leading URL path delimiter.
    url = url.split()[0]  # Any text after 1st space in elem is not URL.
    return url


def _norm_enrolled(enrolled):
    """Returns the supplied 'Registered Students' text as an int."""
    try:
        return int(enrolled.strip())
    except ValueError as err:
        if enrolled == enrollments.NONE_ENROLLED:
            return 0
        raise err


def _cmp_by_url(a, b):
    """sorted() cmp to simulate clicking the 'URL Component' column."""
    a_url = _norm_url(a.url)
    b_url = _norm_url(b.url)
    if a_url < b_url:
        return -1
    if a_url > b_url:
        return 1
    return 0


def _cmp_by_title_then_url(a, b):
    """sorted() cmp to simulate clicking the 'Title' column."""
    a_title = a.title.strip().lower()
    b_title = b.title.strip().lower()

    if a_title == b_title:
        return _cmp_by_url(a, b)

    if not a_title:
        return 1
    if not b_title:
        return -1
    if a_title < b_title:
        return -1
    return 1  # a_title > b_title


def _cmp_by_avail_then_title_then_url(a, b):
    """sorted() cmp to simulate clicking the 'Availability' column."""
    a_avail = a.avail.lower()
    b_avail = b.avail.lower()
    if a_avail < b_avail:
        return -1
    if a_avail > b_avail:
        return 1
    return _cmp_by_title_then_url(a, b)


def _cmp_by_enrolled_then_title_then_url(a, b):
    """sorted() cmp to simulate clicking the 'Registered Students' column."""
    if a.enroll != b.enroll:
        return a.enroll - b.enroll
    return _cmp_by_title_then_url(a, b)


class CoursesListPage(pageobjects.CoursesListPage):
    _FIXED_TABLE_CSS_SEL = 'div.gcb-list .table-container > table.fixed.thead'
    _SCROLLED_TABLE_CSS_SEL = 'div.gcb-list .table-scroller > table:not(.fixed)'

    _FIXED_COL_HDR_CSS_SEL = _FIXED_TABLE_CSS_SEL + ' > thead > tr > th'
    _SCROLLED_COL_HDR_CSS_SEL = _SCROLLED_TABLE_CSS_SEL + ' > thead > tr > th'

    _SELECT_COURSE_CELL_CLASS = 'gcb-list-select-course'
    _SELECT_ALL_COURSES_CHECKBOX_ID = 'all_courses_select'

    _SELECT_ALL_COURSES_CHECKBOX_SEL = '.{} input#{}'.format(
        _SELECT_COURSE_CELL_CLASS, _SELECT_ALL_COURSES_CHECKBOX_ID)

    _FIXED_SELECT_ALL_CHECKBOX_CSS_SEL = '{}{}'.format(
        _FIXED_COL_HDR_CSS_SEL, _SELECT_ALL_COURSES_CHECKBOX_SEL)
    _SCROLLED_SELECT_ALL_CHECKBOX_CSS_SEL = '{}{}'.format(
        _SCROLLED_COL_HDR_CSS_SEL, _SELECT_ALL_COURSES_CHECKBOX_SEL)

    _SCROLLED_ROWS_CSS_SEL = _SCROLLED_TABLE_CSS_SEL + ' > tbody > tr'

    _COURSE_CHECKBOX_CSS_CLASS = 'gcb-course-checkbox'
    _COURSE_CHECKBOX_SEL_FMT = '{} > td.{} input#select_{{}}.{}'.format(
        _SCROLLED_ROWS_CSS_SEL, _SELECT_COURSE_CELL_CLASS,
        _COURSE_CHECKBOX_CSS_CLASS)

    CMP_SORTABLE_COLUMNS = collections.OrderedDict([
        ('title', _cmp_by_title_then_url),
        ('url', _cmp_by_url),
        ('availability', _cmp_by_avail_then_title_then_url),
        ('enrolled', _cmp_by_enrolled_then_title_then_url),
    ])
    SORTABLE_COLUMNS_ORDER = CMP_SORTABLE_COLUMNS.keys()
    SORTABLE_COLUMNS = frozenset(SORTABLE_COLUMNS_ORDER)

    LOG_LEVEL = logging.INFO

    def _get_admin_operation_count(self, driver=None):
        if driver is None:
            driver = self._tester.driver
        count = driver.execute_script('return gcbAdminOperationCount;')
        return count

    def _click_checkbox_and_wait_for_effects_to_propagate(self, checkbox):
        prev_counter = self._get_admin_operation_count()
        checkbox.click()
        def effects_have_propagated(driver):
            current_counter = self._get_admin_operation_count(driver=driver)
            return current_counter > prev_counter
        self.wait().until(effects_have_propagated)

    def _toggle_checkbox(self, checkbox_css_sel):
        checkbox = self.find_element_by_css_selector(checkbox_css_sel)
        self._click_checkbox_and_wait_for_effects_to_propagate(checkbox)

    def _get_checkbox_state(self, checkbox_css_sel):
        return self.find_element_by_css_selector(
            checkbox_css_sel).get_attribute('checked') == 'true'

    def toggle_course_checkbox(self, course_namespace):
        cbox_sel = self._COURSE_CHECKBOX_SEL_FMT.format(course_namespace)
        self._toggle_checkbox(cbox_sel)
        return self

    def toggle_all_courses_checkbox(self):
        self._toggle_checkbox(self._SCROLLED_SELECT_ALL_CHECKBOX_CSS_SEL)
        return self

    def _check_checkbox_state(self, checkbox_css_sel, expected_state):
        actual_state = self._get_checkbox_state(checkbox_css_sel)
        self._tester.assertEqual(expected_state, actual_state)

    def verify_course_checkbox_checked(self, course_namespace, expected_state):
        cbox_sel = self._COURSE_CHECKBOX_SEL_FMT.format(course_namespace)
        self._check_checkbox_state(cbox_sel, expected_state)
        return self

    def verify_all_courses_checkbox_checked(self, expected_state):
        self._check_checkbox_state(
            self._SCROLLED_SELECT_ALL_CHECKBOX_CSS_SEL, expected_state)
        self._check_checkbox_state(
            self._FIXED_SELECT_ALL_CHECKBOX_CSS_SEL, expected_state)
        return self

    def verify_all_courses_checkbox_indeterminate(self, expected_state):
        scrolled_state = self.find_element_by_css_selector(
            self._SCROLLED_SELECT_ALL_CHECKBOX_CSS_SEL
        ).get_attribute('indeterminate') == 'true'
        self._tester.assertEqual(expected_state, scrolled_state)
        fixed_state = self.find_element_by_css_selector(
            self._FIXED_SELECT_ALL_CHECKBOX_CSS_SEL
        ).get_attribute('indeterminate') == 'true'
        self._tester.assertEqual(expected_state, fixed_state)
        return self

    def _match_enrolled_count_and_tooltip(self, namespace, count, tooltip,
                                          delay_scale_factor):
        count_div_selector = '#enrolled_' + namespace
        tooltip_selector = '#activity_'+ namespace
        wait_timeout = pageobjects.DEFAULT_TIMEOUT

        if delay_scale_factor >= 1:
            reload_sleep = delay_scale_factor
            # Caller is slowing down this test, so adjust wait() to compensate.
            wait_timeout = wait_timeout * delay_scale_factor
        else:
            # For fraction, zero, or negative scale factors, use time.sleep(0)
            # (which is the no-op POSIX sleep(0) on Linux, at least).
            reload_sleep = 0

        def count_div_equals_count(driver):
            count_div = self.find_element_by_css_selector(count_div_selector)
            match = (count == count_div.text.strip())
            if not match:
                time.sleep(reload_sleep)
                self.load(self._base_url)
            return match

        # Verification will fail by timeout if expected count never appears.
        self.wait(timeout=wait_timeout).until(count_div_equals_count)

        def tooltip_match_pops_up(driver):
            count_div = self.find_element_by_css_selector(count_div_selector)
            action_chains.ActionChains(self._tester.driver).move_to_element(
                count_div).perform()
            tooltip_div = self.find_element_by_css_selector(tooltip_selector)
            match = re.match(tooltip, tooltip_div.text.strip())
            if not match:
                time.sleep(reload_sleep)
                self.load(self._base_url)
            return match

        # Verification will fail by timeout if expected count never appears.
        self.wait(timeout=wait_timeout).until(tooltip_match_pops_up)
        return self

    def verify_no_enrollments(self, namespace, title,
                              delay_scale_factor=0):
        text = enrollments.NONE_ENROLLED
        regexp = re.escape(
            '(registration activity is being computed for "%s")' % title)
        return self._match_enrolled_count_and_tooltip(
            namespace, text, regexp, delay_scale_factor)

    DATETIME_REGEXP = "[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"

    def verify_total_enrollments(self, namespace, title, count,
                                 delay_scale_factor=1):
        text = "%d" % count
        regexp = ('Most recent activity at %s UTC for %s' %
                  (self.DATETIME_REGEXP, re.escape('"%s".' % title)))
        return self._match_enrolled_count_and_tooltip(
            namespace, text, regexp, delay_scale_factor)

    def verify_availability(self, namespace, expected):
        a_href = self.find_element_by_id('availability_' + namespace)
        self._tester.assertEqual(expected, a_href.text.strip())
        return self

    def get_category_for(self, namespace, pre_wait=True):
        return self.find_element_by_id(
            'category_' + namespace, pre_wait=pre_wait).text.strip()

    def get_availability_for(self, namespace):
        return self.find_element_by_id(
            'availability_' + namespace).text.strip()

    def get_start_date_for(self, namespace, pre_wait=True):
        return self.find_element_by_id(
            'start_date_' + namespace, pre_wait=pre_wait).text.strip()

    def get_end_date_for(self, namespace, pre_wait=True):
        return self.find_element_by_id(
            'end_date_' + namespace, pre_wait=pre_wait).text.strip()

    def get_show_in_explorer_for(self, namespace):
        return self.find_element_by_id(
            'show_in_explorer_' + namespace).text.strip()

    def _open_multicourse_popup(self, item_id):
        field = self.find_element_by_css_selector('.dropdown-container')
        action_chains.ActionChains(self._tester.driver).move_to_element(
            field).perform()
        self.find_element_by_id(item_id).click()
        return MultiEditModalDialog(self._tester)

    def click_edit_availability(self):
        return self._open_multicourse_popup('edit_multi_course_availability')

    def click_edit_start_date(self):
        return self._open_multicourse_popup('edit_multi_course_start_date')

    def click_edit_end_date(self):
        return self._open_multicourse_popup('edit_multi_course_end_date')

    def click_edit_category(self):
        return self._open_multicourse_popup('edit_multi_course_category')

    def click_edit_show_in_explorer(self):
        return self._open_multicourse_popup(
            'edit_multi_course_show_in_explorer')

    def _col_hdr_id_sel(self, column):
        sel = '#{}_column'.format(column)
        return sel

    def _scrolled_col_hdr_id_sel(self, column):
        sel = self._SCROLLED_COL_HDR_CSS_SEL + self._col_hdr_id_sel(column)
        return sel

    def _fixed_col_hdr_id_sel(self, column):
        sel = self._FIXED_COL_HDR_CSS_SEL + self._col_hdr_id_sel(column)
        return sel

    def _sorted_th_icon_sel(self, th_sel):
        sel = th_sel + ' i.gcb-sorted-icon'
        return sel

    def _sorted_class(self, sort_dir):
        cls = 'gcb-sorted-' + sort_dir
        return cls

    def _sorted_arrow(self, sort_dir):
        if sort_dir == 'descending':
            return 'downward'
        if sort_dir == 'ascending':
            return 'upward'
        return ''

    def _next_arrow(self, arrow):
        if arrow == 'upward':
            return 'downward'
        return 'upward'

    def _md_arrow(self, arrow):
        if arrow:
            arrow_text = 'arrow_' + arrow
        else:
            arrow_text = ''
        return arrow_text

    def _check_sorted_arrow_state(self, th_sel, sort_dir, arrow):
        th = self.find_element_by_css_selector(th_sel)
        self._tester.assertIn(
            self._sorted_class(sort_dir), th.get_attribute('class'))
        icon_selector = self._sorted_th_icon_sel(th_sel)
        icon_i = self.find_element_by_css_selector(
            icon_selector, pre_wait=False)
        self._tester.assertEquals(self._md_arrow(arrow), icon_i.text.strip())

    def verify_sorted_arrow(self, column, sort_dir, arrow):
        col_hdr_selector = self._scrolled_col_hdr_id_sel(column)
        fixed_hdr_selector = self._fixed_col_hdr_id_sel(column)
        self._check_sorted_arrow_state(col_hdr_selector, sort_dir, arrow)
        self._check_sorted_arrow_state(fixed_hdr_selector, sort_dir, arrow)
        return self

    def verify_no_sorted_arrow(self, column):
        return self.verify_sorted_arrow(column, 'none', '')

    def _check_hover_arrow_state(self, th_sel, sort_dir, arrow):
        th = self.find_element_by_css_selector(th_sel)
        self._tester.assertIn(
            self._sorted_class(sort_dir), th.get_attribute('class'))
        icon_selector = self._sorted_th_icon_sel(th_sel)
        icon_i = self.find_element_by_css_selector(icon_selector)
        self._tester.assertIn(
            'gcb-sorted-hover', icon_i.get_attribute('class'))
        self._tester.assertEquals(self._md_arrow(arrow), icon_i.text.strip())

    def verify_hover_arrow(self, column, sort_dir, arrow):
        col_hdr_selector = self._scrolled_col_hdr_id_sel(column)
        fixed_hdr_selector = self._fixed_col_hdr_id_sel(column)
        col_hdr_th = self.find_element_by_css_selector(col_hdr_selector)
        action_chains.ActionChains(self._tester.driver).move_to_element(
            col_hdr_th).perform()
        self._check_hover_arrow_state(col_hdr_selector, sort_dir, arrow)
        self._check_hover_arrow_state(fixed_hdr_selector, sort_dir, arrow)
        return self

    def verify_sorted_by_arrows(self, column, sort_dir):
        arrow = self._sorted_arrow(sort_dir)
        self.verify_sorted_arrow(
            column, sort_dir, arrow
        )

        # All other columns should indicate gcb-sorted-none and no arrow,
        # then an upward arrow when hovered over ("next" for an unsorted
        # column is always gcb-sorted-ascending, so upward gray arrow).
        others = self.SORTABLE_COLUMNS.difference([column])
        for other in others:
            self.verify_no_sorted_arrow(
                other
            ).verify_hover_arrow(
                other, 'none', 'upward'
            )

        # Hovering over sorted-by columns should toggle the existing arrow,
        # but not the gcb-sorted class.
        self.verify_hover_arrow(
            column, sort_dir, self._next_arrow(arrow)
        )
        return self

    def click_sortable_column(self, column):
        self.find_element_by_css_selector(
            self._scrolled_col_hdr_id_sel(column)).click()
        return self

    def click_if_not_initial(self, column, initial):
        if not initial:
            self.click_sortable_column(column)
        return False  # Used to overwrite `initial` value passed by caller.

    # Course "Title", "URL Component", "Availability", "Registered Students",
    # tuples, with titles having mixed cases, leading and trailing whitespace,
    # etc.
    Course = collections.namedtuple('Course', 'title url avail enroll')

    def verify_rows_sorted_by_column(self, column, sort_dir, courses):
        # Course URLs are by definition unique, so save a set of known URLs.
        known = set([_norm_url(c.url) for c in courses])
        table_rows = self.find_elements_by_css_selector(
            self._SCROLLED_ROWS_CSS_SEL)
        logging.info('%s by %s:', sort_dir.upper(), column)

        sorted_courses = sorted(
            courses, reverse=(sort_dir == 'descending'),
            cmp=self.CMP_SORTABLE_COLUMNS[column])
        self._tester.assertTrue(len(table_rows) >= len(sorted_courses))

        for tr in table_rows:
            name = _norm_url(tr.find_element_by_css_selector(
                'td.gcb-courses-url .gcb-text-to-sort-by').text)
            if name not in known:
                # Ignore courses added by other tests accessing the same
                # integration server. The courses intentionally added for
                # this test should still end up in the desired sorted order,
                # regardless of what other unknown tests are interleaved
                # between them.
                continue
            else:
                known.remove(name)

            # This will result in test failure if more courses with "known"
            # URLs than sorted_courses somehow exist.
            course = sorted_courses.pop(0)
            want_name = _norm_url(course.url)
            logging.info('NAME:      %s\nexpected: %s', name, want_name)

            # Any leading/trailing whitespace is also removed while sorting.
            want_title = course.title.strip()
            title = tr.find_element_by_css_selector(
                'td.gcb-courses-title .gcb-text-to-sort-by').text.strip()
            logging.info('TITLE:     %s\nexpected: %s', title, want_title)

            want_avail = course.avail.strip()
            avail = tr.find_element_by_css_selector(
                'td.gcb-courses-availability .gcb-text-to-sort-by').text.strip()
            logging.info('AVAIL:     %s\nexpected: %s', avail, want_avail)

            # Course.enroll is already an int in the namedtuple.
            want_enroll = course.enroll
            enroll = _norm_enrolled(
                tr.find_element_by_css_selector(
                    'td.gcb-courses-enrolled .gcb-text-to-sort-by').text)
            logging.info('ENROLLED:  %s\nexpected: %s', enroll, want_enroll)

            self._tester.assertEqual(want_title, title)
            self._tester.assertEqual(want_name, name)
            self._tester.assertEqual(want_avail, avail)
            self._tester.assertEqual(want_enroll, enroll)

        # All of the sorted courses should have been consumed, regardless of
        # courses created by other tests interleaved in the courses list.
        self._tester.assertEqual(0, len(sorted_courses))
        self._tester.assertEqual(0, len(known))
        return self


class MultiEditModalDialog(pageobjects.CoursesListPage):

    def __init__(self, tester):
        super(MultiEditModalDialog, self).__init__(tester)
        # Wait for main div of modal dialog to be visible.
        self._dialog = self.find_element_by_id('multi-course-edit-panel')

    def _dialog_not_visible(self, unused_driver):
        try:
            return not self._dialog.is_displayed()
        except exceptions.StaleElementReferenceException:
            return True

    def click_cancel(self):
        self.find_element_by_id('multi-course-close').click()
        self.wait().until(self._dialog_not_visible)
        return CoursesListPage(self._tester)

    def click_save(self, alert_ok=True):
        self.find_element_by_id('multi-course-save').click()
        if alert_ok:
            self.accept_alert()
        spinner = self.find_element_by_id('multi-course-spinner')
        def spinner_not_visible(driver):
            try:
                return not spinner.is_displayed()
            except exceptions.StaleElementReferenceException:
                return True
        self.wait().until(spinner_not_visible)
        return self

    def get_save_button_is_enabled(self):
        save_button = self.find_element_by_id('multi-course-save')
        return save_button.is_enabled()

    def click_clear_value_radio(self):
        self.find_element_by_id('edit_multi_course_clear').click()

    def click_set_value_radio(self):
        self.find_element_by_id('edit_multi_course_set').click()

    def click_save_expecting_validation_failure(self):
        self.find_element_by_id('multi-course-save').click()
        self._tester.assertFalse(expected_conditions.alert_is_present()(
            self._tester.driver))

    def accept_alert(self):
        self.wait().until(expected_conditions.alert_is_present())
        self._tester.driver.switch_to_alert().accept()
        return self

    def set_category(self, value):
        category = self.find_element_by_id('multi-course-category')
        category.send_keys(value)

    def set_show_in_explorer(self, value):
        if value:
            radio = self.find_element_by_id('multi-course-show-in-explorer-yes')
            if not radio.get_attribute('checked'):
                radio.click()
        else:
            radio = self.find_element_by_id('multi-course-show-in-explorer-no')
            if not radio.get_attribute('checked'):
                radio.click()
        return self

    def are_show_buttons_marked_invalid(self):
        yes = self.find_element_by_css_selector(
            '.multi-course-show-in-explorer-yes')
        no = self.find_element_by_css_selector(
            '.multi-course-show-in-explorer-no')
        return ('input-invalid' in no.get_attribute('class').strip().split() and
                'input-invalid' in yes.get_attribute('class').strip().split())

    def set_availability(self, value):
        select_elt = self.find_element_by_id('multi-course-select-availability')
        select.Select(select_elt).select_by_visible_text(value)
        return self

    def is_availability_marked_invalid(self):
        field = self.find_element_by_id('multi-course-select-availability')
        return 'input-invalid' in field.get_attribute('class').strip().split()

    def is_category_marked_invalid(self):
        field = self.find_element_by_id('multi-course-category')
        return 'input-invalid' in field.get_attribute('class').strip().split()

    def set_date_time(self, the_date, the_time):
        """Set date/time field.

        Args:
          the_date: A string of the form mm/dd/yyyy
          the_time: A string of the form hh.  E.g., "03", "22", etc.
        """
        date_element = self.find_element_by_css_selector(
            '#datetime-container input[type="text"]')
        self._tester.driver.execute_script(
            'arguments[0].setAttribute("value", "' + the_date +'")',
            date_element)
        time_element = self.find_element_by_css_selector(
            '#datetime-container select')
        select.Select(time_element).select_by_visible_text(the_time)
        return self

    def is_date_time_marked_invalid(self):
        field = self.find_element_by_css_selector(
            '#datetime-container > '
            '.inputEx-CombineField > '
            '.inputEx-fieldWrapper')
        return 'inputEx-invalid' in field.get_attribute('class').strip().split()

    def assert_status(self, namespace, text):
        td = self.find_element_by_id('course_status_' + namespace)
        self._tester.assertEqual(text, td.text.strip())
        return self

    def set_availability_xsrf_token(self, new_value):
        self._tester.driver.execute_script(
            'gcb_multi_edit_dialog._xsrfToken = "%s";' % new_value)
        return self

    def get_current_value_for(self, namespace):
        return self.find_element_by_id(
            'current_value_' + namespace).text.strip()
