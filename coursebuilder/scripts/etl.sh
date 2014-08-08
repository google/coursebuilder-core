#!/bin/bash

# Copyright 2014 Google Inc. All Rights Reserved.
#
# Wrapper script for tools/etl/etl.py that sets up the environment correctly.
#
# Run this script as follows:
#     sh ./scripts/etl.sh <arguments>
#
# ETL's arguments are involved; pass --help for details. You will need to
# provide credentials when using ETL on one of your running instances.

set -e

. "$(dirname "$0")/common.sh"

# Configure the Python path so ETL can find all required libraries.
# NOTE: if you have customized Course Builder and put any code in locations not
# on this path, you will need to add your new paths here. Otherwise, ETL may
# fail at runtime (if it can't, for example, find some new models you wrote).
PYTHONPATH=\
$FANCY_URLLIB_PATH:\
$JINJA_PATH:\
$WEBAPP_PATH:\
$WEBOB_PATH:\
$YAML_PATH:\
$PYTHONPATH

python $TOOLS_DIR/etl/etl.py "$@"
