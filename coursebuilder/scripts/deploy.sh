#!/bin/bash

# Copyright 2014 Google Inc. All Rights Reserved.
#
# Usage:
#
# Run this script from the Course Builder folder. It can be run with the
# following arguments:
#
# Deploy Course Builder to the App Engine app named in app.yaml:
#     sh ./scripts/deploy.sh
#
# Deploy Course Builder to the given App Engine app:
#     sh ./scripts/deploy.sh my_app_name
#
# Deploy Course Builder with optional arguments passed to appcfg.py:
#     sh ./scripts/deploy.sh <optional_args>
# E.g.,
#   Authenticate on App Engine with OAuth2:
#     sh ./scripts/deploy.sh --oauth2
# See the documentation for appcfg.py for more details:
#   https://developers.google.com/appengine/docs/python/tools/uploadinganapp

set -e

# local environment may contain non-default value for GCB_ALLOW_STATIC_SERV;
# remove it here, so the proper default is picked up from script/config.sh
echo "Removing GCB_ALLOW_STATIC_SERV set to '"$GCB_ALLOW_STATIC_SERV"'"
unset GCB_ALLOW_STATIC_SERV

. "$(dirname "$0")/common.sh"

if [[ $# == 1 && $1 != -* ]]; then
  application="--application=$1"
  shift
fi

python "$GOOGLE_APP_ENGINE_HOME/appcfg.py" \
  $application \
  "$@" update \
  "$SOURCE_DIR"
