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

"""Unit tests for modules/dashboard."""

__author__ = [
    'John Cox (johncox@google.com)',
    'Todd Larsen (tlarsen@google.com)'
]

import random
import unittest

from modules.dashboard import asset_paths
from tests.unit import javascript_tests


class JavaScriptTests(javascript_tests.TestBase):

    def test_scripts(self):
        self.karma_test('modules/dashboard/javascript_tests')


# Capture copies of original binary, text, and all allowed bases.
BINARY_ONLY = frozenset(asset_paths.AllowedBases.binary_bases())
TEXT_ONLY = frozenset(asset_paths.AllowedBases.text_bases())
ALL_ALLOWED = frozenset(BINARY_ONLY.union(TEXT_ONLY))


class AllowedBasesTests(unittest.TestCase):
    """Unit tests for modules.dashboard.asset_paths.AllowedBases."""

    def setUp(self):
        """Resets all_bases, binary_bases, and text_bases between tests."""
        asset_paths.AllowedBases.del_text_bases(
            asset_paths.AllowedBases.text_bases())
        self.assertFalse(asset_paths.AllowedBases.text_bases())
        asset_paths.AllowedBases.del_binary_bases(
            asset_paths.AllowedBases.binary_bases())
        self.assertFalse(asset_paths.AllowedBases.binary_bases())
        self.assertFalse(asset_paths.AllowedBases.all_bases())

        asset_paths.AllowedBases.add_text_bases(TEXT_ONLY)
        self.assertEqual(TEXT_ONLY, asset_paths.AllowedBases.text_bases())
        asset_paths.AllowedBases.add_binary_bases(BINARY_ONLY)
        self.assertEqual(BINARY_ONLY, asset_paths.AllowedBases.binary_bases())
        self.assertEqual(ALL_ALLOWED, asset_paths.AllowedBases.all_bases())

    def test_all_bases(self):
        """Tests the all_bases method."""
        # No caller-supplied bases override, so return all allowed bases.
        self.assertEqual(
            ALL_ALLOWED,
            asset_paths.AllowedBases.all_bases())
        self.assertEqual(
            ALL_ALLOWED,
            asset_paths.AllowedBases.all_bases(bases=[]))

        # Non-empty caller-supplied bases override is simply returned.
        self.assertEqual(
            ["/foo/bar/"],
            asset_paths.AllowedBases.all_bases(bases=["/foo/bar/"]))

    def test_add_del_text_bases(self):
        """Tests methods that alter text_bases."""
        # Before testing add/del, confirm expected text bases.
        self.assertEqual(
            TEXT_ONLY,
            asset_paths.AllowedBases.text_bases())

        asset_paths.AllowedBases.add_text_bases([])
        self.assertEqual(
            TEXT_ONLY,
            asset_paths.AllowedBases.text_bases())
        self.assertEqual(
            ALL_ALLOWED,
            asset_paths.AllowedBases.all_bases())

        # New text asset bases, all missing canonical /.../ delimiters.
        new_malformed_bases = ["assets/text", "assets/dart/", "/assets/sgml"]
        new_text_bases = frozenset(asset_paths.as_bases(new_malformed_bases))

        # Add one new text asset base.
        some_new_text_base = random.choice(new_malformed_bases)
        asset_paths.AllowedBases.add_text_base(some_new_text_base)
        self.assertEqual(
            len(TEXT_ONLY) + 1,
            len(asset_paths.AllowedBases.text_bases()))
        self.assertEqual(
            TEXT_ONLY.union([asset_paths.as_base(some_new_text_base)]),
            asset_paths.AllowedBases.text_bases())
        # Should also update all_bases superset with one new base.
        self.assertEqual(
            len(ALL_ALLOWED) + 1,
            len(asset_paths.AllowedBases.all_bases()))
        self.assertEqual(
            ALL_ALLOWED.union([asset_paths.as_base(some_new_text_base)]),
            asset_paths.AllowedBases.all_bases())

        # Add multiple new text asset bases (some are already present).
        asset_paths.AllowedBases.add_text_bases(new_malformed_bases)
        self.assertEqual(
            TEXT_ONLY.union(new_text_bases),
            asset_paths.AllowedBases.text_bases())
        # Should also update all_bases superset with new bases.
        self.assertEqual(
            ALL_ALLOWED.union(new_text_bases),
            asset_paths.AllowedBases.all_bases())

        # Delete previously-added text asset base.
        another_new_text_base = random.choice(new_malformed_bases)
        asset_paths.AllowedBases.del_text_base(another_new_text_base)
        new_remaining = frozenset(new_text_bases.difference(
            [asset_paths.as_base(another_new_text_base)]))
        self.assertEqual(
            TEXT_ONLY.union(new_remaining),
            asset_paths.AllowedBases.text_bases())
        # Should also remove that base from all_bases superset.
        self.assertEqual(
            ALL_ALLOWED.union(new_remaining),
            asset_paths.AllowedBases.all_bases())

        # Delete multiple new text asset bases (some may already be gone).
        asset_paths.AllowedBases.del_text_bases(new_malformed_bases)
        self.assertEqual(
            TEXT_ONLY,
            asset_paths.AllowedBases.text_bases())
        # Should also remove those bases from all_bases superset.
        self.assertEqual(
            ALL_ALLOWED,
            asset_paths.AllowedBases.all_bases())

        # Can delete an original allowed text base (but, *please*, do not).
        some_original_text_base = random.choice([tb for tb in TEXT_ONLY])
        asset_paths.AllowedBases.del_text_base(some_original_text_base)
        self.assertEqual(
            len(TEXT_ONLY) - 1,
            len(asset_paths.AllowedBases.text_bases()))
        asset_paths.AllowedBases.del_text_base(some_original_text_base)

    def test_add_del_binary_bases(self):
        """Tests methods that alter binary_bases."""
        # Before testing add/del, confirm expected binary bases.
        self.assertEqual(
            BINARY_ONLY,
            asset_paths.AllowedBases.binary_bases())

        asset_paths.AllowedBases.add_binary_bases([])
        self.assertEqual(
            BINARY_ONLY,
            asset_paths.AllowedBases.binary_bases())
        self.assertEqual(
            ALL_ALLOWED,
            asset_paths.AllowedBases.all_bases())

        # New text asset bases, all missing canonical /.../ delimiters.
        new_malformed_bases = ["/assets/video/", "/assets/sound/"]
        new_binary_bases = frozenset(asset_paths.as_bases(new_malformed_bases))

        # Add one new text asset base.
        some_new_binary_base = random.choice(new_malformed_bases)
        asset_paths.AllowedBases.add_binary_base(some_new_binary_base)
        self.assertEqual(
            len(BINARY_ONLY) + 1,
            len(asset_paths.AllowedBases.binary_bases()))
        self.assertEqual(
            BINARY_ONLY.union([asset_paths.as_base(some_new_binary_base)]),
            asset_paths.AllowedBases.binary_bases())
        # Should also update all_bases superset with one new base.
        self.assertEqual(
            len(ALL_ALLOWED) + 1,
            len(asset_paths.AllowedBases.all_bases()))
        self.assertEqual(
            ALL_ALLOWED.union([asset_paths.as_base(some_new_binary_base)]),
            asset_paths.AllowedBases.all_bases())

        # Add multiple new text asset bases (some are already present).
        asset_paths.AllowedBases.add_binary_bases(new_malformed_bases)
        self.assertEqual(
            BINARY_ONLY.union(new_binary_bases),
            asset_paths.AllowedBases.binary_bases())
        # Should also update all_bases superset with new bases.
        self.assertEqual(
            ALL_ALLOWED.union(new_binary_bases),
            asset_paths.AllowedBases.all_bases())

        # Delete previously-added text asset base.
        another_new_binary_base = random.choice(new_malformed_bases)
        asset_paths.AllowedBases.del_binary_base(another_new_binary_base)
        new_remaining = frozenset(new_binary_bases.difference(
            [asset_paths.as_base(another_new_binary_base)]))
        self.assertEqual(
            BINARY_ONLY.union(new_remaining),
            asset_paths.AllowedBases.binary_bases())
        # Should also remove that base from all_bases superset.
        self.assertEqual(
            ALL_ALLOWED.union(new_remaining),
            asset_paths.AllowedBases.all_bases())

        # Delete multiple new text asset bases (some may already be gone).
        asset_paths.AllowedBases.del_binary_bases(new_malformed_bases)
        self.assertEqual(
            BINARY_ONLY,
            asset_paths.AllowedBases.binary_bases())
        # Should also remove those bases from all_bases superset.
        self.assertEqual(
            ALL_ALLOWED,
            asset_paths.AllowedBases.all_bases())

        # Can delete an original allowed text base (but, *please*, do not).
        some_original_binary_base = random.choice([bb for bb in BINARY_ONLY])
        asset_paths.AllowedBases.del_binary_base(some_original_binary_base)
        self.assertEqual(
            len(BINARY_ONLY) - 1,
            len(asset_paths.AllowedBases.binary_bases()))
        asset_paths.AllowedBases.del_binary_base(some_original_binary_base)

    def test_is_path_allowed(self):
        """."""
        pass # TEST with/without custom bases

    def test_match_allowed_bases(self):
        """."""
        pass # TEST default (all), caller-supplied


BOTH_DELIMS = "/both/delims/"
END_DELIM = "end/delim/"
START_DELIM = "/start/delim"
ALL_BASES = [BOTH_DELIMS, END_DELIM, START_DELIM]

ABS_KEY = "/assets/img/abs_img_path.jpg"
REL_KEY = "assets/img/rel_img_path.jpg"


class AssetPathsTests(unittest.TestCase):
    """Unit tests for modules.dashboard.asset_paths functions."""

    def test_asset_paths_as_key(self):
        """Tests the asset_paths.as_key function."""
        self.assertEqual(
            "both/delims",
            asset_paths.as_key(BOTH_DELIMS))
        self.assertEqual(
            "end/delim",
            asset_paths.as_key(END_DELIM))
        self.assertEqual(
            "start/delim",
            asset_paths.as_key(START_DELIM))
        self.assertEqual(
            "assets/img/abs_img_path.jpg",
            asset_paths.as_key(ABS_KEY))
        self.assertEqual(
            "assets/img/rel_img_path.jpg",
            asset_paths.as_key(REL_KEY))

    def test_asset_paths_as_base(self):
        """Tests the asset_paths.as_base function."""
        self.assertEqual(
            "/both/delims/",
            asset_paths.as_base(BOTH_DELIMS))
        self.assertEqual(
            "/end/delim/",
            asset_paths.as_base(END_DELIM))
        self.assertEqual(
            "/start/delim/",
            asset_paths.as_base(START_DELIM))

    def test_asset_paths_as_bases(self):
        """Tests the asset_paths.as_bases function."""
        bases = [ab for ab in asset_paths.as_bases(ALL_BASES)]
        golden = ["/both/delims/", "/end/delim/", "/start/delim/"]
        self.assertEqual(golden, bases)
        generated = (asset_paths.as_base(b) for b in ALL_BASES)
        self.assertEqual([gb for gb in generated], bases)

    def test_asset_paths_relative_base(self):
        """Tests the asset_paths.relative_base function."""
        self.assertEqual(
            "both/delims/",
            asset_paths.relative_base(BOTH_DELIMS))
        self.assertEqual(
            "end/delim/",
            asset_paths.relative_base(END_DELIM))
        self.assertEqual(
            "start/delim/",
            asset_paths.relative_base(START_DELIM))

    def test_does_path_match_base(self):
        """Tests the does_path_match_base function."""

        # as_base(base) canonicalizations:
        # 1) Not a file path, but a key query parameter for "Upload New...".
        self.assertTrue(asset_paths.does_path_match_base(
            "/canonical/base/", "canonical/base"))
        # 2) File path key query parameter, with absolute path.
        self.assertTrue(asset_paths.does_path_match_base(
            "/canonical/prefix/file.html", "canonical/prefix/"))

        # as_key(base) conversion.
        # Only leading and trailing / delimeter-stripped *exact* match, for
        # "Upload New..." key query paraemeter.
        self.assertTrue(asset_paths.does_path_match_base(
            "noncanonical/base", "/noncanonical/base/"))
        # Do *not* match partial prefixes without / delimiters.
        self.assertFalse(asset_paths.does_path_match_base(
            "noncanonical/basefile.jpg", "/noncanonical/base/"))

        # relative_base(base) conversion.
        # 1) Not a file path, but a key query parameter for "Upload New...".
        self.assertTrue(asset_paths.does_path_match_base(
            "relative/base/", "/relative/base"))
        # 2) File path key query parameter, with relative path.
        self.assertTrue(asset_paths.does_path_match_base(
            "relative/prefix/file.css", "/relative/prefix"))
