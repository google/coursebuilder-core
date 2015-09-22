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

"""Menu items."""

__author__ = 'Nick Retallack (nretallack@google.com)'


class BaseMenu(object):
    DEFAULT_PLACEMENT = 1000000

    """Base class for commonalities between MenuGroup and MenuItem.

    Args:
      name: String key used to identify this menu item.
      title: Human-readable name.
      group: Menu group that this item should appear inside.
      can_view: A function that returns True if this menu item should be
        visible.
      placement: Sibling menu items appear in ascending order of placement,
        and then in alphabetical order if placement matches.  Conventionally,
        we will use increments of 1000 initially so it is easy to place items
        between other items later.  Defaults to one million.

        Using a value for 'placement' other than DEFAULT_PLACEMENT indicates a
        desire to get a strict ordering relative to other items which also
        choose a specific value.  Typical values for items wanting an early
        placement that will be in the low thousands.  Typical values for items
        wanting a later placement must be above DEFAULT_PLACEMENT.

        Since multiple modules may wish to appear first or last, and since that
        degenerates into an arms race of picking ever-lower/higher values, it is
        left as an exercise to the implementer to search through code to find
        what values other modules are using if your module Just Really Has To be
        first/last.
    """
    def __init__(
            self, name, title, group=None, can_view=None,
            placement=None):
        self.name = name
        self.title = title
        if placement is None:
            placement = self.DEFAULT_PLACEMENT
        self.placement = placement
        self._can_view = can_view

        if group:
            group.add_child(self)
        else:
            self.group = None

    def can_view(self, app_context, exclude_links=False):
        if self._can_view:
            return self._can_view(app_context)
        else:
            return True

    def __repr__(self):
        return "<{} name={}>".format(self.__class__.__name__, self.name)


class MenuGroup(BaseMenu):
    def __init__(
            self, name, title, group=None, can_view=None, placement=None):
        super(MenuGroup, self).__init__(
            name, title, group=group, can_view=can_view, placement=placement)
        self.children = []

    def add_child(self, child):
        child.group = self
        self.children.append(child)
        self.children.sort(key=lambda item: (item.placement, item.title))

    def remove_child(self, child):
        self.children.remove(child)

    def remove_all(self):
        self.children = []

    def get_child(self, name):
        for child in self.children:
            if child.name == name:
                return child

    def first_visible_child(
            self, app_context, exclude_names=None, exclude_links=False):
        if super(MenuGroup, self).can_view(app_context):
            for child in self.children:
                if exclude_links and child.is_link():
                    continue
                if exclude_names and child.name in exclude_names:
                    continue
                if child.can_view(app_context):
                    return child

    def first_visible_item(
            self, app_context, exclude_names=None, exclude_links=False):
        child = self.first_visible_child(
            app_context, exclude_names=exclude_names,
            exclude_links=exclude_links)
        if child:
            if isinstance(child, MenuItem):
                return child
            else:
                return child.first_visible_item(
                    app_context, exclude_names=exclude_names,
                    exclude_links=exclude_links)

    def can_view(self, app_context, exclude_links=False):
        return bool(
            self.first_visible_item(app_context, exclude_links=exclude_links))

    def computed_href(self, app_context):
        child = self.first_visible_item(app_context)
        if child:
            return child.computed_href(app_context)

    def is_link(self):
        return False

    def is_group(self):
        return True


class MenuItem(BaseMenu):
    def __init__(
            self, name, title, action=None, can_view=None, group=None,
            href=None, is_external=False, placement=None, target=None):
        assert can_view
        super(MenuItem, self).__init__(
            name, title, group=group, can_view=can_view, placement=placement)
        self.action = action
        self.href = href
        self.target = target
        self.is_external = is_external or bool(target)

    def computed_href(self, app_context):
        return self.href

    def is_link(self):
        return not self.action

    def is_group(self):
        return False
