# Copyright 2014 Google Inc. All Rights Reserved.
#
# Set common config variables for developer runtime environment scripts.

# NOTE: This file is also evaluated by Python scripts to get configurations
# from environment variables.  Do not add any non-idempotent side-effects
# to this script.
export SOURCE_DIR="$( cd "$( dirname "${BASH_ARGV[0]}" )" && cd .. && pwd )"
export COURSEBUILDER_HOME=$SOURCE_DIR
export TOOLS_DIR=$SOURCE_DIR/tools
export SCRIPTS_DIR=$SOURCE_DIR/scripts
export INTERNAL_SCRIPTS_DIR=$SOURCE_DIR/internal/scripts
export DISTRIBUTED_LIBS_DIR=$SOURCE_DIR/lib
export COURSEBUILDER_RESOURCES=~/coursebuilder_resources
export MODULES_HOME=$COURSEBUILDER_RESOURCES/modules
export RUNTIME_HOME=$COURSEBUILDER_RESOURCES/runtime
export RELEASE_HOME=$COURSEBUILDER_RESOURCES/releases
export SERVER=appengine.google.com
export GOOGLE_APP_ENGINE_HOME=$RUNTIME_HOME/google_appengine_1_9_9
export GOLDEN_INSTALL_LIST=$INTERNAL_SCRIPTS_DIR/golden_install_list

# Paths for resources used by the Python runtime.
export FANCY_URLLIB_PATH=$GOOGLE_APP_ENGINE_HOME/lib/fancy_urllib
export JINJA_PATH=$GOOGLE_APP_ENGINE_HOME/lib/jinja2-2.6
export WEBAPP_PATH=$GOOGLE_APP_ENGINE_HOME/lib/webapp2-2.5.2
export WEBOB_PATH=$GOOGLE_APP_ENGINE_HOME/lib/webob-1.2.3
export BEAUTIFULSOUP_PATH=$RUNTIME_HOME/beautifulsoup4
export SELENIUM_PATH=$RUNTIME_HOME/selenium/py
export SIX_PATH=$RUNTIME_HOME/six
export WEBTEST_PATH=$RUNTIME_HOME/webtest
export YAML_PATH=$RUNTIME_HOME/lib/yaml/lib
