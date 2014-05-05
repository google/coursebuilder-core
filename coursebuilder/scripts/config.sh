# Copyright 2014 Google Inc. All Rights Reserved.
#
# Set common config variables for developer runtime environment scripts.

# NOTE: This file is also evaluated by Python scripts to get configurations
# from environment variables.  Do not add any non-idempotent side-effects
# to this script.
export SOURCE_DIR="$( cd "$( dirname "${BASH_ARGV[0]}" )" && cd .. && pwd )"
export COURSEBUILDER_HOME=$SOURCE_DIR
export SCRIPTS_DIR=$SOURCE_DIR/scripts
export INTERNAL_SCRIPTS_DIR=$SOURCE_DIR/internal/scripts
export DISTRIBUTED_LIBS_DIR=$SOURCE_DIR/lib
export COURSEBUILDER_RESOURCES=~/coursebuilder_resources
export RUNTIME_HOME=$COURSEBUILDER_RESOURCES/runtime
export RELEASE_HOME=$COURSEBUILDER_RESOURCES/releases
export SERVER=appengine.google.com
export GOOGLE_APP_ENGINE_HOME=$RUNTIME_HOME/google_appengine_1_8_9
export GOLDEN_INSTALL_LIST=$INTERNAL_SCRIPTS_DIR/golden_install_list
