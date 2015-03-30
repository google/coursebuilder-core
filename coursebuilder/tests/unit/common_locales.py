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

"""Unit tests for common/locale.py."""

__author__ = 'John Orr (jorr@google.com)'

import unittest

from common import locales


class ParseAcceptLanguageTests(unittest.TestCase):
    """Unit tests for parsing of Accept-Language HTTP header."""

    def test_parses_well_formatted_strings(self):
        well_formatted_strings_with_expectations = (
            ('en-US', [('en_US', 1.0)]),
            ('en-US,el-GR,fr', [('en_US', 1.0), ('el_GR', 1.0), ('fr', 1.0)]),
            ('en-US,el;q=0.8', [('en_US', 1.0), ('el', 0.8)]))
        for acc_lang, expectations in well_formatted_strings_with_expectations:
            parsed = locales.parse_accept_language(acc_lang)
            self.assertEquals(expectations, parsed)

    def test_arranges_quality_scores_in_decreasing_order(self):
        parsed = locales.parse_accept_language('en-US;q=0.8,el;q=1.0')
        expected = [('el', 1.0), ('en_US', 0.8)]
        self.assertEquals(expected, parsed)

    def test_appect_lang_header_length_capped_at_8k(self):
        with self.assertRaises(AssertionError):
            locales.parse_accept_language('x' * 8192)

    def test_coerces_case_to_standard_form(self):
        """Expect form xx_XX returned."""
        self.assertEqual(
            [('en_US', 1.0), ('el_GR', 1.0), ('fr', 1.0)],
            locales.parse_accept_language('en-us,EL-gr,FR'))

    def test_item_split_ignores_whitespace(self):
        """Expect form xx_XX returned."""
        self.assertEqual(
            [('en_US', 1.0), ('el_GR', 1.0), ('fr', 1.0)],
            locales.parse_accept_language('en-US,  el-gr ,    fr '))

    def test_rejects_invalid_syntax(self):
        self.assertEqual(
            [('el', 1.0), ('fr', 1.0)],
            locales.parse_accept_language('el,-us,en-,12-34,fr'))


class LocalesTests(unittest.TestCase):
    """Unit tests for the locale helper functions."""

    def test_supported_locale_count(self):
        # NOTE: If this count increases then locales.LOCALES_DISPLAY_NAMES must
        # be updated with the localized display names of the new locale.
        self.assertEquals(59, len(locales.get_system_supported_locales()))

    def test_localized_display_name(self):
        self.assertEquals('Deutsch (de)', locales.get_locale_display_name('de'))
