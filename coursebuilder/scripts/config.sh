# Copyright 2014 Google Inc. All Rights Reserved.
#
# Set common config variables for developer runtime environment scripts.

# NOTE: This file is also evaluated by Python scripts to get configurations
# from environment variables.  Do not add any non-idempotent side-effects
# to this script.

# Don't invoke config.sh directly.
# common.sh (and others) must source it instead.
config_script="${BASH_ARGV[0]}"

# Paths for project source and Google App Engine SDK
export SOURCE_DIR="$( cd "$( dirname "${config_script}" )" && cd .. && pwd )"
export PRODUCT_VERSION=`cat "$SOURCE_DIR/app.yaml" | \
    grep GCB_PRODUCT_VERSION | \
    awk -F ':' '{print $2}' | \
    tr -d "'"`
export _VERSION_SUFFIX=`echo $PRODUCT_VERSION | sed 's/\./_/g'`
export COURSEBUILDER_HOME="$SOURCE_DIR"
export TOOLS_DIR="$SOURCE_DIR/tools"
export SCRIPTS_DIR="$SOURCE_DIR/scripts"
export INTERNAL_SCRIPTS_DIR="$SOURCE_DIR/internal/scripts"
export DISTRIBUTED_LIBS_DIR="$SOURCE_DIR/lib"
export COURSEBUILDER_RESOURCES="$HOME/coursebuilder_resources_$_VERSION_SUFFIX"
export MODULES_HOME="$COURSEBUILDER_RESOURCES/modules"
export RUNTIME_HOME="$COURSEBUILDER_RESOURCES/runtime"
export RELEASE_HOME="$COURSEBUILDER_RESOURCES/releases"
export GOOGLE_APP_ENGINE_HOME="$RUNTIME_HOME/google_appengine"
export GOLDEN_INSTALL_LIST="$INTERNAL_SCRIPTS_DIR/golden_install_list"

# Paths for resources used by the Python runtime.
export BEAUTIFULSOUP_PATH="$RUNTIME_HOME/beautifulsoup4"
export FANCY_URLLIB_PATH="$GOOGLE_APP_ENGINE_HOME/lib/fancy_urllib"
export JINJA_PATH="$GOOGLE_APP_ENGINE_HOME/lib/jinja2-2.6"
export PYCRYPTO_PATH="$RUNTIME_HOME/pycrypto-2.6.1"
export SELENIUM_PATH="$RUNTIME_HOME/selenium/py"
export SIX_PATH="$GOOGLE_APP_ENGINE_HOME/lib/six"
export WEBAPP_PATH="$GOOGLE_APP_ENGINE_HOME/lib/webapp2-2.5.2"
export WEBOB_PATH="$GOOGLE_APP_ENGINE_HOME/lib/webob-1.2.3"
export WEBTEST_PATH="$RUNTIME_HOME/webtest"
export YAML_PATH="$GOOGLE_APP_ENGINE_HOME/lib/yaml/lib"

# Common settings and options
export SERVER=appengine.google.com

# Disable static serving completely by setting the default value of
# ALLOW_STATIC_SERV to 'false' below; if your local environment has a value of
# GCB_ALLOW_STATIC_SERV set, it will be used as a default instead
export ALLOW_STATIC_SERV=${GCB_ALLOW_STATIC_SERV:-true}

# Configure dev_appserver. Allow OAuth2 authentication of remote_api endpoints.
export OAUTH_IS_ADMIN=1
