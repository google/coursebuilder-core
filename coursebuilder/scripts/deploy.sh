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

# Add Cygwin install to path before script uses any utilities.
if [[ $OSTYPE == cygwin* ]] ; then
  export PATH="$COURSE_BUILDER_CYGWIN_ROOT:/usr/bin:$PATH"
fi

# local environment may contain non-default value for GCB_ALLOW_STATIC_SERV;
# remove it here, so the proper default is picked up from script/config.sh
echo "Removing GCB_ALLOW_STATIC_SERV set to '"$GCB_ALLOW_STATIC_SERV"'"
unset GCB_ALLOW_STATIC_SERV

. "$(dirname "$0")/common.sh"

# -----------------------------------------------------------------------------
# Argument parsing helper: If there is a command line argument that does
# not start with a hyphen, treat that as the name of the App Engine instance
# to which to deploy.  Pass through any arguments to appcfg.py
# (Here, we cannot use getopt since we do not know the universe of all legal
# arguments.)
#
declare -a args=( $@ )
declare -a passthrough_args
# Loop over command line arguments, as copied into 'args'.
for i in $( seq 0 $(( ${#args[@]} - 1)) ); do
  if [[ ${args[$i]:0:1} != '-' ]] ; then
    # If first character of the $i'th argument is not a hyphen, treat it as
    # the name of the App Engine instance.
    application="--application=${args[$i]}"
  else
    # First char is a hyphen; append to a list of arguments passed through to
    # appcfg.py
    passthrough_args+=(${args[$i]})
  fi
done

python "$GOOGLE_APP_ENGINE_HOME/appcfg.py" \
  $application \
  "${passthrough_args[@]}" \
  update \
  "$SOURCE_DIR"

echo ""
echo ""
echo ""
echo "Deployment complete."
