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

# Add Cygwin install to path before script uses any utilities.
if [[ $OSTYPE == cygwin* ]] ; then
  export PATH="$COURSE_BUILDER_CYGWIN_ROOT:/usr/bin:$PATH"
fi

. "$(dirname "$0")/parse_start_args.sh"

echo Starting GAE development server
exec "${start_cb_server[@]}"
