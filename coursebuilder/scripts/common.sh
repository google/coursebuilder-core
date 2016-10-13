# Copyright 2016 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# @author: psimakov@google.com (Pavel Simakov)
# @author: mgainer@google.com (Mike Gainer)
# @author: nretallack@google.com (Nick Retallack)

# This script sets up all build/test dependencies including Google App Engine,
# WebTest, Selenium, Chromedriver, etc. All other scripts will include this
# script to setup these dependencies.

# Force shell to fail on any errors.
set -e

shopt -s nullglob

# Determining the path of this script depends on how it was used.
if [ "$(basename "$0")" != "common.sh" ]; then
  # Script was "sourced", e.g. `. scripts/common.sh`
  common_script="${BASH_ARGV[0]}"
  echo "Sourced as: '${common_script}'"
else
  # Script was invoked, e.g. `sh scripts/common.sh`
  common_script="$0"
  echo "Sourced as: '${common_script}'"
fi

# Set shell variables common to CB scripts.
. "$(dirname "${common_script}")/config.sh"

CHROMEDRIVER_VERSION=2.24
CHROMEDRIVER_DIR="$RUNTIME_HOME/chromedriver-$CHROMEDRIVER_VERSION"
if [[ $OSTYPE == linux* ]] ; then
  NODE_DOWNLOAD_FOLDER=node-v0.12.4-linux-x64
  CHROMEDRIVER_ZIP=chromedriver_linux64.zip
elif [[ $OSTYPE == darwin* ]] ; then
  NODE_DOWNLOAD_FOLDER=node-v0.12.4-darwin-x64
  CHROMEDRIVER_ZIP=chromedriver_mac64.zip
elif [[ $OSTYPE == "cygwin" ]] ; then
  echo "Windows install; skipping test-related downloads."
else
  echo "Target OS '$TARGET_OS' must start with 'linux' or 'darwin'."
  exit -1
fi
CHROMEDRIVER_URL=http://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/$CHROMEDRIVER_ZIP
PYPI_URL=https://pypi.python.org/packages/source

# Ensure that $COURSEBUILDER_RESOURCES is available to write
if [[ -e "$COURSEBUILDER_RESOURCES" && \
    ( ! -d "$COURSEBUILDER_RESOURCES" || \
      ! -w "$COURSEBUILDER_RESOURCES" ) ]]; then
  echo ERROR: These scripts need to be able to create or write to a folder
  echo called "'$COURSEBUILDER_RESOURCES'."
  echo Exiting...
  exit 1
fi

# Ensure that start_in_shell.sh is executable
if [ ! -x "$SOURCE_DIR/scripts/start_in_shell.sh" ]; then
  chmod u+x "$SOURCE_DIR/scripts/start_in_shell.sh"
  chmod u+x "$SOURCE_DIR/scripts/pylint.sh"
fi

# Configures the runtime environment.
export PYTHONPATH="$SOURCE_DIR\
:$GOOGLE_APP_ENGINE_HOME\
:$RUNTIME_HOME/oauth2client\
:$RUNTIME_HOME/pycrypto-2.6.1"
PATH="$RUNTIME_HOME/node/node_modules/karma/bin\
:$RUNTIME_HOME/node/bin\
:$RUNTIME_HOME/phantomjs/bin\
:$CHROMEDRIVER_DIR\
:$PATH"
export YUI_BASE="$RUNTIME_HOME/yui/build"
export KARMA_LIB="$RUNTIME_HOME/karma_lib"

CB_ARCHIVE_URL=https://github.com/google/coursebuilder-resources/raw/master
CB_ARCHIVE_CONFIG_URL=$CB_ARCHIVE_URL/config
CB_ARCHIVE_LIB_URL=$CB_ARCHIVE_URL/lib
CB_ARCHIVE_GAE_SDK_URL=$CB_ARCHIVE_CONFIG_URL/gae_sdk_download_url_cb_1_11

echo Ensuring runtime folder $RUNTIME_HOME
if [ ! -d "$RUNTIME_HOME" ]; then
  mkdir -p $RUNTIME_HOME
fi

function download_and_unpack() {
  local source_url="$1" && shift
  local dest_dir="$1" && shift || local dest_dir="$RUNTIME_HOME"

  local archive_type=$( \
    echo "$source_url" | \
    sed -e 's/.*\.zip/zip/' | \
    sed -e 's/.*\.tar\.gz/tar.gz/' | \
    sed -e 's/.*\.tar/tar/' | \
    sed -e 's/.*\.bz2/bz2/' )
  local temp_dir=$(mktemp -d)
  pushd $temp_dir > /dev/null
  curl --location --silent "$source_url" -o archive_file
  case $archive_type in
    zip) unzip -q archive_file -d "$dest_dir" ;;
    tar) tar xf archive_file --directory "$dest_dir" ;;
    tar.gz) tar xzf archive_file --directory "$dest_dir" ;;
    bz2) tar xjf archive_file --directory "$dest_dir" ;;
    *) exit -1 ;;
  esac
  rm archive_file
  popd > /dev/null
  rmdir $temp_dir
}

if [ -s "$GOOGLE_APP_ENGINE_HOME/VERSION" ]; then
  GAE_SDK_VERSION=$(cat "$GOOGLE_APP_ENGINE_HOME/VERSION" | \
    grep release | \
    sed 's/release: //g' | \
    tr -d '"')
  echo Using GAE SDK $GAE_SDK_VERSION from $GOOGLE_APP_ENGINE_HOME
else
  echo "Installing App Engine developer toolkit.  This may take a few minutes."

  if [ -d "$GOOGLE_APP_ENGINE_HOME" ]; then
    rm -r $GOOGLE_APP_ENGINE_HOME
  fi

  mkdir -p "$RUNTIME_HOME"
  curl --location --silent $CB_ARCHIVE_GAE_SDK_URL -o gae_sdk_download_url
  GAE_SDK_URL=$(cat gae_sdk_download_url)
  download_and_unpack $GAE_SDK_URL
  rm gae_sdk_download_url
  GAE_SDK_VERSION=$(cat "$GOOGLE_APP_ENGINE_HOME/VERSION" | \
    grep release | \
    sed 's/release: //g' | \
    tr -d '"')
  echo Installed GAE SDK $GAE_SDK_VERSION
fi

function handle_build_error() {
  local package_name="$1" && shift
  local package_version="$1" && shift

  echo "
Compilation error building $package_name-$package_version. Please ensure a C
compiler is installed and functional on your system. On OS X, the most likely
cause of this problem is that you don't have the XCode Command Line Tools
installed. To fix this, run

  $ xcode-select --install

and follow the instructions that appear, then re-run this command."
  exit -1
}

function need_install() {
  local package_name="$1" && shift
  local version_file="$RUNTIME_HOME/$package_name/$1" && shift
  local version_finder="$1" && shift
  local expected_version="$1" && shift
  local purpose="$1" && shift
  # The "purpose" parameter should be one of 'test' or 'product' to indicate
  # whether the item is needed only for tests or for the actual product itself.
  # For problematic platforms (Windows), we skip fetch/install of test packages.
  if [[ $OSTYPE == "cygwin" && $purpose == "test" ]] ; then
    return 1
  fi

  local package_dir="$RUNTIME_HOME/$package_name"

  if [ ! -d "$package_dir" ] ; then
    echo "Installing $package_name-$expected_version to $package_dir"
    return 0
  fi

  local version=$( grep "$version_finder" "$version_file" \
    | grep -v Meta \
    | head -1 \
    | sed -e "s/.*$version_finder* *//" -e 's/ .*//' )
  if [ "$version" != "$expected_version" ] ; then
    echo "Expected version '$expected_version' for $package_name, but" \
      "instead had '$version'.  Removing and reinstalling."
    rm -rf "$package_dir"
    return 0
  fi
  echo "Using $package_name-$expected_version from $package_dir"
  return 1
}

# Probe for file not present in the archive, but present in the folder we make
# *from* the archive.
if [ ! -f "$RUNTIME_HOME/pycrypto-2.6.1/.gcb_install_succeeded" ]; then
  if [[ $OSTYPE == "cygwin" ]] ; then
    # The Cygwin python headers claim that BSD is available, but when building
    # the PyCrypto package, it is not.  Comment out this line.  Note that we
    # are leaving it commented out: We download a copy of Cygwin specifically
    # for Course Builder so we're in 100% control of which items are and aren't
    # fetched as well as insulation from any hackery the end-user may have
    # performed.
    PYCFG=/usr/include/python2.7/pyconfig.h
    sed -e 's,^#define __BSD_VISIBLE 1,/* #define __BSD_VISIBLE 1 */,' \
        $PYCFG > $PYCFG.tmp
    mv $PYCFG.tmp $PYCFG
  fi

  # PyCrypto is included in the prod bundle, but we need to supply it in dev
  # mode. It contains native code and must be built on the user's platform.
  echo 'Installing PyCrypto (This needs to be compiled so it matches '
  echo '   your operating system)'

  # Clean up any old artifacts (for example, from failed builds).
  if [ -d "$RUNTIME_HOME/pycrypto-2.6.1" ]; then
    rm -r "$RUNTIME_HOME/pycrypto-2.6.1"
  fi

  download_and_unpack $PYPI_URL/p/pycrypto/pycrypto-2.6.1.tar.gz
  pushd . > /dev/null
  cd "$RUNTIME_HOME/pycrypto-2.6.1"
  echo Building PyCrypto
  python setup.py build > /dev/null 2>&1 || handle_build_error pycrypto 2.6.1
  echo Installing PyCrypto
  python setup.py install --home="$RUNTIME_HOME/pycrypto_build_tmp" > /dev/null
  rm -r "$RUNTIME_HOME/pycrypto-2.6.1"
  mkdir "$RUNTIME_HOME/pycrypto-2.6.1"
  touch "$RUNTIME_HOME/pycrypto-2.6.1/__init__.py"
  mv "$RUNTIME_HOME/pycrypto_build_tmp/lib/python/"* \
    "$RUNTIME_HOME/pycrypto-2.6.1"
  rm -r "$RUNTIME_HOME/pycrypto_build_tmp"
  # Now that we know we've succeeded, create the needle for later probes.
  touch "$RUNTIME_HOME/pycrypto-2.6.1/.gcb_install_succeeded"
  popd > /dev/null
fi

if need_install webtest PKG-INFO Version: 2.0.14 test ; then
  download_and_unpack $PYPI_URL/W/WebTest/WebTest-2.0.14.zip
  mv "$RUNTIME_HOME/WebTest-2.0.14" "$RUNTIME_HOME/webtest"
fi

if need_install six PKG-INFO Version: 1.5.2 product ; then
  echo Installing six '(a Python 2.x/3.x compatibility bridge)'
  download_and_unpack $PYPI_URL/s/six/six-1.5.2.tar.gz
  mv "$RUNTIME_HOME/six-1.5.2" "$RUNTIME_HOME/six"
fi

if need_install beautifulsoup4 PKG-INFO Version: 4.4.1 product ; then
  # Beautiful Soup is 'product', since it's used in flattening Polymer imports
  echo Installing Beautiful Soup HTML processing library
  download_and_unpack $PYPI_URL/b/beautifulsoup4/beautifulsoup4-4.4.1.tar.gz
  mv "$RUNTIME_HOME/beautifulsoup4-4.4.1" "$RUNTIME_HOME/beautifulsoup4"
fi

if need_install selenium PKG-INFO Version: 2.53.1 test ; then
  download_and_unpack $PYPI_URL/s/selenium/selenium-2.53.1.tar.gz
  mv "$RUNTIME_HOME/selenium-2.53.1" "$RUNTIME_HOME/selenium"
fi

if [ ! -x "$CHROMEDRIVER_DIR/chromedriver" -a $OSTYPE != "cygwin" ] ; then
  download_and_unpack $CHROMEDRIVER_URL "$CHROMEDRIVER_DIR"
  chmod a+x "$CHROMEDRIVER_DIR/chromedriver"
fi

if need_install node ChangeLog Version 0.12.4 test ; then
  download_and_unpack \
    http://nodejs.org/dist/v0.12.4/$NODE_DOWNLOAD_FOLDER.tar.gz
  mv "$RUNTIME_HOME/$NODE_DOWNLOAD_FOLDER" "$RUNTIME_HOME/node"

  echo Installing Karma
  pushd "$RUNTIME_HOME/node" > /dev/null
  if [ ! -d node_modules ]; then
    mkdir node_modules
  fi
  ./bin/npm --cache "$RUNTIME_HOME/node/cache" install \
      jasmine-core@2.3.4 phantomjs@1.9.8 karma@0.12.36 \
      karma-jasmine@0.3.5 karma-phantomjs-launcher@0.2.0 karma-jasmine-jquery \
      --save-dev > /dev/null
  popd > /dev/null
fi

# NOTE: Yes, we are looking for 2.1.0, having installed 2.1.1.  Because
# PhantomJS' ChangeLog file only mentions 2.1.0, not 2.1.1.  Grr.
if need_install phantomjs ChangeLog Version 2.1.0 test ; then
  echo Installing PhantomJs
  if [[ $OSTYPE == linux* ]] ; then
    download_and_unpack \
      $CB_ARCHIVE_LIB_URL/phantomjs-2.1.1-linux-x86_64.tar.bz2 "$RUNTIME_HOME"
    rm -rf "$RUNTIME_HOME/phantomjs"
    mv "$RUNTIME_HOME/phantomjs-2.1.1-linux-x86_64" "$RUNTIME_HOME/phantomjs"
  elif [[ $OSTYPE == darwin* ]] ; then
    download_and_unpack \
      $CB_ARCHIVE_LIB_URL/phantomjs-2.1.1-macosx.zip \
      "$RUNTIME_HOME/phantomjs"
  else
    echo "Target OS '$OSTYPE' must start with 'linux' or 'darwin'."
    exit -1
  fi
fi

if need_install logilab/pylint ChangeLog " -- " 1.4.0 test ; then
  mkdir -p "$RUNTIME_HOME/logilab"
  rm -rf "$RUNTIME_HOME/logilab/pylint"
  download_and_unpack \
    https://bitbucket.org/logilab/pylint/get/pylint-1.4.tar.gz \
    "$RUNTIME_HOME/logilab"
  mv "$RUNTIME_HOME/logilab/logilab-pylint-6224a61f7491" \
    "$RUNTIME_HOME/logilab/pylint"
fi

if need_install logilab/astroid ChangeLog " -- " 1.3.2 test ; then
  mkdir -p "$RUNTIME_HOME/logilab"
  rm -rf "$RUNTIME_HOME/logilab/asteroid"
  download_and_unpack \
    https://bitbucket.org/logilab/astroid/get/astroid-1.3.2.tar.gz \
    "$RUNTIME_HOME/logilab"
  mv "$RUNTIME_HOME/logilab/logilab-astroid-16369edfbc89" \
    "$RUNTIME_HOME/logilab/astroid"
fi

if need_install logilab/logilab/common ChangeLog " -- " 0.62.0 test ; then
  mkdir -p "$RUNTIME_HOME/logilab/logilab"
  rm -rf "$RUNTIME_HOME/logilab/logilab/common"
  download_and_unpack \
    https://bitbucket.org/logilab/logilab-common/get/logilab-common-version-0.62.0.tar.gz \
    "$RUNTIME_HOME/logilab/logilab"

  mv "$RUNTIME_HOME/logilab/logilab/logilab-logilab-common-4797b86b800e" \
    "$RUNTIME_HOME/logilab/logilab/common"
  touch "$RUNTIME_HOME/logilab/logilab/__init__.py"
fi

DISTRIBUTED_LIBS="\
  appengine-mapreduce-0.8.2.zip \
  babel-0.9.6.zip \
  codemirror-4.5.0.zip \
  crossfilter-1.3.7.zip \
  dagre-0.7.4.zip \
  dagre-d3-0.4.17p.zip \
  d3-3.4.3.zip \
  dc.js-1.6.0.zip \
  decorator-3.4.0.zip \
  dependo-0.1.4.zip \
  gaepytz-2011h.zip \
  google-api-python-client-1.4.0.zip \
  GoogleAppEngineCloudStorageClient-1.9.15.0.zip \
  GoogleAppEnginePipeline-1.9.17.0.zip \
  Graphy-1.0.0.zip \
  graphene-0.7.3.zip \
  graphql-core-0.4.12.1.zip \
  graphql-relay-0.3.3.zip \
  html5lib-0.95.zip \
  identity-toolkit-python-client-0.1.6.zip \
  inputex-3.1.0.zip \
  isodate-0.5.5.zip \
  jquery-2.2.4.zip \
  jqueryui-1.11.4.zip \
  markdown-2.5.zip \
  material-design-iconic-font-1.1.1.zip \
  mathjax-2.3.0.zip \
  mathjax-fonts-2.3.0.zip \
  mrs-mapreduce-0.9.zip \
  networkx-1.9.1.zip \
  oauth-1.0.1.zip \
  polymer-1.2.0.zip \
  pyparsing-1.5.7.zip \
  rdflib-4.2.2-dev.zip \
  reportlab-3.1.8.zip \
  simplejson-3.7.1.zip \
  six-1.10.0.zip \
  underscore-1.4.3.zip \
  yui_2in3-2.9.0.zip \
  yui_3.6.0.zip \
"

echo Using third party Python packages from $DISTRIBUTED_LIBS_DIR
if [ ! -d "$COURSEBUILDER_RESOURCES/lib" ]; then
  mkdir -p "$COURSEBUILDER_RESOURCES/lib"
fi
if [ ! -d "$DISTRIBUTED_LIBS_DIR" ]; then
  mkdir -p "$DISTRIBUTED_LIBS_DIR"
fi
for lib in "$DISTRIBUTED_LIBS_DIR"/*; do
  if [ ! "$lib" = "_static" ]; then
      continue
  fi
  fname=$( basename "$lib" )
  if [[ "$DISTRIBUTED_LIBS" != *" $fname "* ]]; then
    echo "Warning: extraneous CB distribution runtime library file $lib"
  fi
done
for lib in $DISTRIBUTED_LIBS ; do
  IS_NEW=false
  if [ ! -f "$COURSEBUILDER_RESOURCES/lib/$lib.gcb_download_succeeded" ]; then
    echo "Downloading CB runtime library $lib to $COURSEBUILDER_RESOURCES/lib/"
    rm -rf "$COURSEBUILDER_RESOURCES/lib/$lib"
    curl --location --silent $CB_ARCHIVE_LIB_URL/$lib -o \
      "$COURSEBUILDER_RESOURCES/lib/$lib"
    touch "$COURSEBUILDER_RESOURCES/lib/$lib.gcb_download_succeeded"
    IS_NEW=true
  fi
  if [ "$IS_NEW" = true ] || [ ! -f "$DISTRIBUTED_LIBS_DIR/$lib" ]; then
    rm -rf "$DISTRIBUTED_LIBS_DIR/$lib"
    ln -s "$COURSEBUILDER_RESOURCES/lib/$lib" "$DISTRIBUTED_LIBS_DIR/$lib"
  fi
done

if need_install yui build/yui/yui.js YUI 3.6.0 product ; then
  echo Installing YUI
  unzip -q "$DISTRIBUTED_LIBS_DIR/yui_3.6.0.zip" -d "$RUNTIME_HOME"
fi

# Prepare files for static serving
. "$(dirname "${common_script}")/static.sh"

# Generate flattened import files for polymer apps
. "$(dirname "${common_script}")/flatten_polymer_imports.sh"

# Delete existing files: *.pyc
find "$SOURCE_DIR" -name "*.pyc" -exec rm -f {} \;
