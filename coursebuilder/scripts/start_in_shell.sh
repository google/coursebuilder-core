#! /bin/bash

# Copyright 2012 Google Inc. All Rights Reserved.
#
# author: psimakov@google.com (Pavel Simakov)

#
# This script starts local developer Google AppEngine server for integration
# tests and initializes it with a default data set.
#
# Run this script from the coursebuilder/ folder:
#     sh ./scripts/start_in_shell.sh
#

# Force shell to fail on any errors.
set -e

. "$(dirname "$0")/parse_start_args.sh"

echo Starting GAE development server

# Maintain this list of arguments in parallel with those in start.sh
exec python $GOOGLE_APP_ENGINE_HOME/dev_appserver.py \
    --host=0.0.0.0 --port=$CB_PORT --admin_port=$ADMIN_PORT \
    --clear_datastore=$CLEAR_DATASTORE \
    --datastore_consistency_policy=consistent \
    --max_module_instances=1 \
    --skip_sdk_update_check=true \
    $STORAGE_PATH_ARGUMENT \
    "$SOURCE_DIR"
