#!/bin/bash

# Copyright 2014 Google Inc. All Rights Reserved.
#
# Wrapper script for modules.py that sets up paths correctly. Usage from your
# coursebuilder/ folder:
#
#   sh scripts/modules.sh [args]

set -e

. "$(dirname "$0")/common.sh"


python "$COURSEBUILDER_HOME/scripts/modules.py" "$@"
