# Copyright 2012 Google Inc. All Rights Reserved.
#
# author: sll@google.com (Sean Lip)

#
# This script runs the functional tests in the tests/functional folder.
#
# Run this script from the Course Builder folder as follows:
#     sh ./scripts/test.sh --test_class <dotted test name>
# E.g.,
#     sh ./scripts/test.sh --test_class tests.unit.common_safe_dom
#     sh ./scripts/test.sh --test_class tests.unit.common_safe_dom.EntityTests
#     sh ./scripts/test.sh --test_class \
#       tests.unit.common_safe_dom.NodeListTests.test_list
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

# Force shell to fail on any errors.
set -e

# Reinstall AE runtime environment and CB-distributed libs if necessary.
. "$(dirname "$0")/common.sh"

PYTHONPATH=\
$SOURCE_DIR:\
$GOOGLE_APP_ENGINE_HOME:\
$JINJA_PATH:\
$WEBAPP_PATH:\
$WEBOB_PATH:\
$BEAUTIFULSOUP_PATH:\
$SELENIUM_PATH:\
$SIX_PATH:\
$WEBTEST_PATH

CB_SERVER_START=$SCRIPTS_DIR/start_in_shell.sh

echo Running functional tests
python "$SOURCE_DIR/tests/suite.py" \
  --integration_server_start_cmd="$CB_SERVER_START" $@

echo Done!
