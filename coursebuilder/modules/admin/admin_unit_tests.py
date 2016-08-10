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

"""Unit tests for modules/admin."""

__author__ = ['Abhinav Khandelwal (abhinavk@google.com)']

import unittest

from modules.admin import admin
from modules.dashboard import dashboard

class GlobalAdminHandlerTests(unittest.TestCase):
    """Unit tests for modules.dashboard.asset_paths.AllowedBases."""

    CUSTOM_ACTION_NAME = "get_test"
    @classmethod
    def custom_handler(cls, handler):
        pass

    @classmethod
    def custom_handler2(cls, handler):
        pass

    def test_custom_get_actions(self):
        """Tests the all_bases method."""
        # Action not specified
        self.assertFalse(admin.GlobalAdminHandler.add_custom_get_action(
            "", None))
        self.assertFalse(admin.GlobalAdminHandler._custom_get_actions.has_key(
            self.CUSTOM_ACTION_NAME))

        # Handler not specified
        self.assertFalse(admin.GlobalAdminHandler.add_custom_get_action(
            self.CUSTOM_ACTION_NAME, None))
        self.assertFalse(admin.GlobalAdminHandler._custom_get_actions.has_key(
            self.CUSTOM_ACTION_NAME))

        # All required fields specified
        self.assertTrue(admin.GlobalAdminHandler.add_custom_get_action(
            self.CUSTOM_ACTION_NAME, self.custom_handler))
        self.assertTrue(admin.GlobalAdminHandler._custom_get_actions.has_key(
            self.CUSTOM_ACTION_NAME))

        # Duplicate entry not allowed
        self.assertFalse(admin.GlobalAdminHandler.add_custom_get_action(
            self.CUSTOM_ACTION_NAME, self.custom_handler2))
        self.assertTrue(admin.GlobalAdminHandler._custom_get_actions.has_key(
            self.CUSTOM_ACTION_NAME))
        self.assertEqual(
            self.custom_handler,
            admin.GlobalAdminHandler
            ._custom_get_actions[self.CUSTOM_ACTION_NAME].handler)

        # Force overwrite existing entry
        self.assertTrue(admin.GlobalAdminHandler.add_custom_get_action(
            self.CUSTOM_ACTION_NAME, self.custom_handler2,
            overwrite=True))
        self.assertTrue(admin.GlobalAdminHandler._custom_get_actions.has_key(
            self.CUSTOM_ACTION_NAME))
        self.assertEqual(
            self.custom_handler2,
            admin.GlobalAdminHandler
            ._custom_get_actions[self.CUSTOM_ACTION_NAME].handler)

        # Remove the action
        admin.GlobalAdminHandler.remove_custom_get_action(
            self.CUSTOM_ACTION_NAME)
        self.assertFalse(admin.GlobalAdminHandler._custom_get_actions.has_key(
            self.CUSTOM_ACTION_NAME))

        # Should not overwrite Dashboard action
        self.assertTrue(dashboard.DashboardHandler.add_custom_get_action(
            self.CUSTOM_ACTION_NAME, handler=self.custom_handler))
        self.assertTrue(dashboard.DashboardHandler._custom_get_actions.has_key(
            self.CUSTOM_ACTION_NAME))
        self.assertFalse(admin.GlobalAdminHandler.add_custom_get_action(
            self.CUSTOM_ACTION_NAME, self.custom_handler))
        self.assertFalse(admin.GlobalAdminHandler._custom_get_actions.has_key(
            self.CUSTOM_ACTION_NAME))

    def test_custom_post_actions(self):
        """Tests the all_bases method."""
        # Action not specified
        self.assertFalse(admin.GlobalAdminHandler.add_custom_post_action(
            "", None))
        self.assertFalse(admin.GlobalAdminHandler._custom_post_actions.has_key(
            self.CUSTOM_ACTION_NAME))

        # Handler not specified
        self.assertFalse(admin.GlobalAdminHandler.add_custom_post_action(
            self.CUSTOM_ACTION_NAME, None))
        self.assertFalse(admin.GlobalAdminHandler._custom_post_actions.has_key(
            self.CUSTOM_ACTION_NAME))

        # All required fields specified
        self.assertTrue(admin.GlobalAdminHandler.add_custom_post_action(
            self.CUSTOM_ACTION_NAME, self.custom_handler))
        self.assertTrue(admin.GlobalAdminHandler._custom_post_actions.has_key(
            self.CUSTOM_ACTION_NAME))

        # Duplicate entry not allowed
        self.assertFalse(admin.GlobalAdminHandler.add_custom_post_action(
            self.CUSTOM_ACTION_NAME, self.custom_handler2))
        self.assertTrue(admin.GlobalAdminHandler._custom_post_actions.has_key(
            self.CUSTOM_ACTION_NAME))
        self.assertEqual(
            self.custom_handler,
            admin.GlobalAdminHandler
            ._custom_post_actions[self.CUSTOM_ACTION_NAME])

        # Force overwrite existing entry
        self.assertTrue(admin.GlobalAdminHandler.add_custom_post_action(
            self.CUSTOM_ACTION_NAME, self.custom_handler2,
            overwrite=True))
        self.assertTrue(admin.GlobalAdminHandler._custom_post_actions.has_key(
            self.CUSTOM_ACTION_NAME))
        self.assertEqual(
            self.custom_handler2,
            admin.GlobalAdminHandler
            ._custom_post_actions[self.CUSTOM_ACTION_NAME])

        # Remove the action
        admin.GlobalAdminHandler.remove_custom_post_action(
            self.CUSTOM_ACTION_NAME)
        self.assertFalse(admin.GlobalAdminHandler._custom_post_actions.has_key(
            self.CUSTOM_ACTION_NAME))

        # Should not overwrite Dashboard action
        self.assertTrue(dashboard.DashboardHandler.add_custom_post_action(
            self.CUSTOM_ACTION_NAME, self.custom_handler))
        self.assertTrue(dashboard.DashboardHandler._custom_post_actions.has_key(
            self.CUSTOM_ACTION_NAME))
        self.assertFalse(admin.GlobalAdminHandler.add_custom_post_action(
            self.CUSTOM_ACTION_NAME, self.custom_handler))
        self.assertFalse(admin.GlobalAdminHandler._custom_post_actions.has_key(
            self.CUSTOM_ACTION_NAME))
