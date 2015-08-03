#!/bin/bash

# Copyright 2012 Google Inc. All Rights Reserved.
#
# author: sll@google.com (Sean Lip)

# Run this script from the Course Builder folder as follows:
#     sh ./scripts/test.sh --test_class <dotted test name>
# E.g.,
#   Run all tests in a module:
#     sh ./scripts/test.sh tests.unit.common_safe_dom
#
#   Run all tests in a class:
#     sh ./scripts/test.sh tests.unit.common_safe_dom.EntityTests
#
#   Run a single test method:
#     sh ./scripts/test.sh tests.unit.common_safe_dom.NodeListTests.test_list
#
# Run this script and measure test coverage as follows:
#     install coverage:
#         pip install coverage
#     modify this script (python > coverage run + coverage report):
#         ...
#         coverage run tests/suite.py
#         coverage report
#         ...
#     run the script from coursebuilder/:
#         sh scripts/test.sh
#

usage () {
  echo
  echo "Usage: $0 <dotted_test_name>"
  echo "E.g.,"
  echo "  $0 tests.unit.common_safe_dom"
  echo
  echo
  echo "To set up tab completion for test names within bash, add the following"
  echo "command to your .bashrc file:"
  echo "export complete -o nospace -C scripts/test_completions.py test.sh"
  echo
  echo "You can also pass the test's name as it is printed in the test output,"
  echo "like so (single quotes are required):"
  echo "  $0 'my_test (tests.functional.modules_my.MyModuleTest)'"
  echo
}

# Force shell to fail on any errors.
set -e

if [[ -z $1 ]]; then
  usage
  exit 1
fi

# Reinstall AE runtime environment and CB-distributed libs if necessary.
. "$(dirname "$0")/common.sh"

. "$(dirname "$0")/test_config.sh"

echo Running functional tests
python "$SOURCE_DIR/scripts/run_all_tests.py" \
  --skip_pylint \
  --test_class_name "$1"

echo Done!
