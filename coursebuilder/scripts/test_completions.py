#!/usr/bin/python

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

"""Provides bash tab completions for running unit/functional/integration tests.

Add the following command to your .bashrc file:
export complete -o nospace -C scripts/test_completions.py test.sh

When running ./scripts/test.sh, you may wish to run an individual sub-section,
file, or individual test.  This file implements a command completion utility
used by bash to help users fill out command lines that name items to test.
"""

__author__ = 'Mike Gainer (mgainer@google.com)'

import os
import re
import sys

CLASS_REGEX = re.compile(r'^class (\w+)\(([^)]+)\):')
TEST_REGEX = re.compile(r'^    def (test_\w+)')


def enumerate_tests(filename, all_test_names):
    """List all test functions within a file."""

    with open(filename) as fp:
        lines = fp.readlines()

    cleaned_filename = filename.replace('.py', '').replace('/', '.').lstrip('.')
    current_class = None
    for line in lines:
        matches = CLASS_REGEX.match(line)
        if matches:
            test_class, base_class = matches.groups()
            if 'Base' not in test_class and 'Test' in base_class:
                current_class = test_class
        matches = TEST_REGEX.match(line)
        if matches:
            all_test_names.append(
                '%s.%s.%s' %
                (cleaned_filename, current_class, matches.group(1)))


def enumerate_test_files():
    """Build a list of all test .py files within Course Builder."""

    ret = []
    for dirpath, dirnames, filenames in os.walk('.'):
        for filename in filenames:
            if (dirpath.startswith('./modules/') and (
                filename.endswith('_test.py') or
                filename.endswith('_tests.py')) or
                (dirpath.startswith('./tests/') and filename.endswith('.py'))):

                path = os.path.join(dirpath, filename)
                ret.append(path)
    return ret


def prune_completions(prefix, all_test_names):
    """Filter returning only items that will complete the current prefix."""

    completions = set()
    for test_name in all_test_names:
        if test_name.startswith(prefix):
            next_break = test_name.find('.', len(prefix) + 1)
            if next_break >= 0:
                # Add only enough to complete this level; don't drown
                # the user with all the possible completions from
                # here.
                completions.add(test_name[:next_break])
            else:
                # If there are no more levels, then add the full name
                # of the leaf.
                completions.add(test_name)
    return completions


def get_completions(prefix):
    """Identify all completions, providng only those matching the prefix."""

    all_test_names = []
    for filename in enumerate_test_files():
        enumerate_tests(filename, all_test_names)
    return prune_completions(prefix, all_test_names)


def main():
    """Interface to outside world using sys.argv, stdout."""
    for item in get_completions(sys.argv[2]):
        print item


if __name__ == '__main__':
    main()
