# Copyright 2013 Google Inc. All Rights Reserved.
#

#
# This script sets up all build/test dependencies including Google App Engine,
# WebTest, Selenium, Chromedriver, etc. All other scripts will include this
# script to setup these dependencies.
#


# Force shell to fail on any errors.
set -e

shopt -s nullglob

# Set shell variables common to CB scripts.
. "$(dirname "$0")/config.sh"

CHROMEDRIVER_VERSION=2.16
CHROMEDRIVER_DIR=$RUNTIME_HOME/chromedriver-$CHROMEDRIVER_VERSION
if [[ $OSTYPE == linux* ]] ; then
  NODE_DOWNLOAD_FOLDER=node-v0.12.4-linux-x64
  CHROMEDRIVER_ZIP=chromedriver_linux64.zip
elif [[ $OSTYPE == darwin* ]] ; then
  NODE_DOWNLOAD_FOLDER=node-v0.12.4-darwin-x64
  CHROMEDRIVER_ZIP=chromedriver_mac32.zip
else
  echo "Target OS '$TARGET_OS' must start with 'linux' or 'darwin'."
  exit -1
fi

# Ensure that $COURSEBUILDER_RESOURCES is available to write
if [[ -e $COURSEBUILDER_RESOURCES && \
    ( ! -d $COURSEBUILDER_RESOURCES || ! -w $COURSEBUILDER_RESOURCES ) ]]; then
  echo ERROR: These scripts need to be able to create or write to a folder
  echo called $COURSEBUILDER_RESOURCES.
  echo Exiting...
  exit 1
fi

# Ensure that start_in_shell.sh is executable
if [ ! -x "$SOURCE_DIR/scripts/start_in_shell.sh" ]; then
  chmod u+x "$SOURCE_DIR/scripts/start_in_shell.sh"
  chmod u+x "$SOURCE_DIR/scripts/pylint.sh"
fi

# Configures the runtime environment.
export PYTHONPATH=$SOURCE_DIR\
:$GOOGLE_APP_ENGINE_HOME\
:$RUNTIME_HOME/oauth2client\
:$RUNTIME_HOME/pycrypto-2.6.1
PATH=$RUNTIME_HOME/node/node_modules/karma/bin\
:$RUNTIME_HOME/node/bin\
:$RUNTIME_HOME/phantomjs/bin\
:$CHROMEDRIVER_DIR\
:$PATH
export YUI_BASE=$RUNTIME_HOME/yui/build
export KARMA_LIB=$RUNTIME_HOME/karma_lib

CB_ARCHIVE_URL=https://github.com/google/coursebuilder-resources/raw/master
CB_ARCHIVE_CONFIG_URL=$CB_ARCHIVE_URL/config
CB_ARCHIVE_LIB_URL=$CB_ARCHIVE_URL/lib
CB_ARCHIVE_GAE_SDK_URL=$CB_ARCHIVE_CONFIG_URL/gae_sdk_download_url_cb_1_10

echo Ensuring runtime folder $RUNTIME_HOME
if [ ! -d "$RUNTIME_HOME" ]; then
  mkdir -p $RUNTIME_HOME
fi

if [ -s "$GOOGLE_APP_ENGINE_HOME/VERSION" ]; then
  GAE_SDK_VERSION=$(cat $GOOGLE_APP_ENGINE_HOME/VERSION | \
    grep release | \
    sed 's/release: //g' | \
    tr -d '"')
  echo Using GAE SDK $GAE_SDK_VERSION from $GOOGLE_APP_ENGINE_HOME
else
  echo Installing GAE SDK

  if [ -d "$GOOGLE_APP_ENGINE_HOME" ]; then
    rm -r $GOOGLE_APP_ENGINE_HOME
  fi

  mkdir -p $RUNTIME_HOME
  echo Fetching GAE SDK URL from $CB_ARCHIVE_GAE_SDK_URL
  curl --location --silent $CB_ARCHIVE_GAE_SDK_URL -o gae_sdk_download_url
  GAE_SDK_URL=$(cat gae_sdk_download_url)
  curl --location --silent $GAE_SDK_URL -o google_appengine.zip
  unzip google_appengine.zip -d $RUNTIME_HOME
  rm google_appengine.zip
  rm gae_sdk_download_url
  GAE_SDK_VERSION=$(cat $GOOGLE_APP_ENGINE_HOME/VERSION | \
    grep release | \
    sed 's/release: //g' | \
    tr -d '"')
  echo Installed GAE SDK $GAE_SDK_VERSION
fi

function handle_build_error() {
  local package_name=$1 && shift
  local package_version=$1 && shift

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
  local package_name=$1 && shift
  local version_file=$RUNTIME_HOME/$package_name/$1 && shift
  local version_finder=$1 && shift
  local expected_version=$1 && shift
  local package_dir=$RUNTIME_HOME/$package_name

  echo "Using $package_name-$expected_version from $package_dir"

  if [ ! -d $package_dir ] ; then
    echo "No directory found for $package_name; installing."
    return 0
  fi

  local version=$( grep "$version_finder" $version_file \
    | grep -v Meta \
    | head -1 \
    | sed -e "s/.*$version_finder* *//" -e 's/ .*//' )
  if [ "$version" != "$expected_version" ] ; then
    echo "Expected version '$expected_version' for $package_name, but" \
      "instead had '$version'.  Removing and reinstalling."
    rm -rf $package_dir
    return 0
  fi
  return 1
}

# Probe for file not present in the archive, but present in the folder we make
# *from* the archive.
if [ ! -f $RUNTIME_HOME/pycrypto-2.6.1/.gcb_install_succeeded ]; then
  # PyCrypto is included in the prod bundle, but we need to supply it in dev
  # mode. It contains native code and must be built on the user's platform.
  echo Installing PyCrypto '(a crypto library needed in dev mode)'

  # Clean up any old artifacts (for example, from failed builds).
  if [ -d $RUNTIME_HOME/pycrypto-2.6.1 ]; then
    rm -r $RUNTIME_HOME/pycrypto-2.6.1
  fi

  curl --location --silent https://pypi.python.org/packages/source/p/pycrypto/pycrypto-2.6.1.tar.gz -o pycrypto-2.6.1.tar.gz
  tar --gunzip --extract --verbose --directory $RUNTIME_HOME --file pycrypto-2.6.1.tar.gz
  rm pycrypto-2.6.1.tar.gz
  pushd .
  cd $RUNTIME_HOME/pycrypto-2.6.1
  echo Building PyCrypto
  python setup.py build || handle_build_error pycrypto 2.6.1
  echo Installing PyCrypto
  python setup.py install --home=$RUNTIME_HOME/pycrypto_build_tmp
  rm -r $RUNTIME_HOME/pycrypto-2.6.1
  mkdir $RUNTIME_HOME/pycrypto-2.6.1
  touch $RUNTIME_HOME/pycrypto-2.6.1/__init__.py
  mv $RUNTIME_HOME/pycrypto_build_tmp/lib/python/* $RUNTIME_HOME/pycrypto-2.6.1
  rm -r $RUNTIME_HOME/pycrypto_build_tmp
  # Now that we know we've succeeded, create the needle for later probes.
  touch $RUNTIME_HOME/pycrypto-2.6.1/.gcb_install_succeeded
  popd
fi

if need_install webtest PKG-INFO Version: 2.0.14 ; then
  curl --location --silent https://pypi.python.org/packages/source/W/WebTest/WebTest-2.0.14.zip -o webtest-download.zip
  unzip webtest-download.zip -d $RUNTIME_HOME
  rm webtest-download.zip
  mv $RUNTIME_HOME/WebTest-2.0.14 $RUNTIME_HOME/webtest
fi

if need_install six PKG-INFO Version: 1.5.2 ; then
  echo Installing six '(a Python 2.x/3.x compatibility bridge)'
  curl --location --silent https://pypi.python.org/packages/source/s/six/six-1.5.2.tar.gz -o six-1.5.2.tar.gz
  tar --gunzip --extract --verbose --directory $RUNTIME_HOME --file six-1.5.2.tar.gz
  rm six-1.5.2.tar.gz
  mv $RUNTIME_HOME/six-1.5.2 $RUNTIME_HOME/six
fi

if need_install beautifulsoup4 PKG-INFO Version: 4.4.1 ; then
  echo Installing Beautiful Soup HTML processing library
  curl --location --silent https://pypi.python.org/packages/source/b/beautifulsoup4/beautifulsoup4-4.4.1.tar.gz -o beautifulsoup4-4.4.1.tar.gz
  tar --gunzip --extract --verbose --directory $RUNTIME_HOME --file beautifulsoup4-4.4.1.tar.gz
  rm beautifulsoup4-4.4.1.tar.gz
  mv $RUNTIME_HOME/beautifulsoup4-4.4.1 $RUNTIME_HOME/beautifulsoup4
fi

if need_install selenium PKG-INFO Version: 2.46.1 ; then
  echo Installing Selenium
  curl --location --silent https://pypi.python.org/packages/source/s/selenium/selenium-2.46.1.tar.gz -o selenium-download.tgz
  tar xzf selenium-download.tgz --directory $RUNTIME_HOME
  rm selenium-download.tgz
  mv $RUNTIME_HOME/selenium-2.46.1 $RUNTIME_HOME/selenium
fi

if [ ! -x $CHROMEDRIVER_DIR/chromedriver ] ; then
  echo Installing Chromedriver
  curl --location --silent http://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/$CHROMEDRIVER_ZIP -o chromedriver-download.zip
  unzip chromedriver-download.zip -d $CHROMEDRIVER_DIR
  chmod a+x $CHROMEDRIVER_DIR/chromedriver
  rm chromedriver-download.zip
fi

if need_install node ChangeLog Version 0.12.4 ; then
  echo Installing Node.js
  curl --location --silent http://nodejs.org/dist/v0.12.4/$NODE_DOWNLOAD_FOLDER.tar.gz -o node-download.tgz
  tar xzf node-download.tgz --directory $RUNTIME_HOME
  mv $RUNTIME_HOME/$NODE_DOWNLOAD_FOLDER $RUNTIME_HOME/node
  rm node-download.tgz
  echo Installing Karma
  pushd $RUNTIME_HOME/node
  ./bin/npm --cache $RUNTIME_HOME/node/cache install jasmine-core@2.3.4 phantomjs@1.9.8 karma@0.12.36 \
      karma-jasmine@0.3.5 karma-phantomjs-launcher@0.2.0 karma-jasmine-jquery \
      --save-dev
  popd
fi

if need_install phantomjs ChangeLog Version 1.9.0 ; then
  echo Installing PhantomJs
  if [[ $OSTYPE == linux* ]] ; then
    curl --location --silent https://phantomjs.googlecode.com/files/phantomjs-1.9.0-linux-x86_64.tar.bz2 -o phantomjs-download.bz2
    tar xjf phantomjs-download.bz2 --directory $RUNTIME_HOME
    mv $RUNTIME_HOME/phantomjs-1.9.0-linux-x86_64 $RUNTIME_HOME/phantomjs
    rm phantomjs-download.bz2
  elif [[ $OSTYPE == darwin* ]] ; then
    curl --location --silent https://phantomjs.googlecode.com/files/phantomjs-1.9.0-macosx.zip -o phantomjs-download.zip
    unzip phantomjs-download.zip -d $RUNTIME_HOME
    mv $RUNTIME_HOME/phantomjs-1.9.0-macosx $RUNTIME_HOME/phantomjs
    rm phantomjs-download.zip
  else
    echo "Target OS '$OSTYPE' must start with 'linux' or 'darwin'."
    exit -1
  fi
fi

if need_install logilab/pylint ChangeLog " -- " 1.4.0 ; then
  echo "Installing logilab/pylint"
  mkdir -p $RUNTIME_HOME/logilab
  rm -rf $RUNTIME_HOME/logilab/pylint
  curl --location --silent https://bitbucket.org/logilab/pylint/get/pylint-1.4.tar.gz -o pylint-1.4.tar.gz
  tempdir=$( mktemp -d /tmp/cb.XXXXXXXX )
  tar xzf pylint-1.4.tar.gz --directory $tempdir
  mv $tempdir/logilab-pylint-6224a61f7491 $RUNTIME_HOME/logilab/pylint
  rm pylint-1.4.tar.gz
  rm -rf $tempdir
fi

if need_install logilab/astroid ChangeLog " -- " 1.3.2 ; then
  echo "Installing logilab/astroid"
  mkdir -p $RUNTIME_HOME/logilab
  rm -rf $RUNTIME_HOME/logilab/astroid
  curl --location --silent https://bitbucket.org/logilab/astroid/get/astroid-1.3.2.tar.gz -o astroid-1.3.2.tar.gz
  tempdir=$( mktemp -d /tmp/cb.XXXXXXXX )
  tar xzf astroid-1.3.2.tar.gz --directory $tempdir
  mv $tempdir/logilab-astroid-16369edfbc89 $RUNTIME_HOME/logilab/astroid
  rm astroid-1.3.2.tar.gz
  rm -rf $tempdir
fi

if need_install logilab/logilab/common ChangeLog " -- " 0.62.0 ; then
  echo "Installing logilab/logilab/common"
  mkdir -p $RUNTIME_HOME/logilab/logilab
  rm -rf $RUNTIME_HOME/logilab/logilab/common
  curl --location --silent https://bitbucket.org/logilab/logilab-common/get/logilab-common-version-0.62.0.tar.gz -o logilab-common-0.62.0.tar.gz
  tempdir=$( mktemp -d /tmp/cb.XXXXXXXX )
  tar xzf logilab-common-0.62.0.tar.gz --directory $tempdir
  mv $tempdir/logilab-logilab-common-4797b86b800e $RUNTIME_HOME/logilab/logilab/common
  touch $RUNTIME_HOME/logilab/logilab/__init__.py
  rm logilab-common-0.62.0.tar.gz
  rm -rf $tempdir
fi

DISTRIBUTED_LIBS="\
  appengine-mapreduce-0.8.2.zip \
  babel-0.9.6.zip \
  codemirror-4.5.0.zip \
  crossfilter-1.3.7.zip \
  d3-3.4.3.zip \
  dc.js-1.6.0.zip \
  decorator-3.4.0.zip \
  dependo-0.1.4.zip \
  gaepytz-2011h.zip \
  google-api-python-client-1.4.0.zip \
  GoogleAppEngineCloudStorageClient-1.9.15.0.zip \
  GoogleAppEnginePipeline-1.9.17.0.zip \
  Graphy-1.0.0.zip \
  html5lib-0.95.zip \
  identity-toolkit-python-client-0.1.6.zip \
  inputex-3.1.0.zip \
  isodate-0.5.5.zip \
  markdown-2.5.zip \
  material-design-iconic-font-1.1.1.zip \
  mathjax-2.3.0.zip \
  mathjax-fonts-2.3.0.zip \
  mrs-mapreduce-0.9.zip \
  networkx-1.9.1.zip \
  oauth-1.0.1.zip \
  polymer-guide-1.2.0.zip \
  pyparsing-1.5.7.zip \
  rdflib-4.2.2-dev.zip \
  reportlab-3.1.8.zip \
  simplejson-3.7.1.zip \
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
    echo "Adding CB runtime library $lib"
    rm -rf "$DISTRIBUTED_LIBS_DIR/$lib"
    cp "$COURSEBUILDER_RESOURCES/lib/$lib" "$DISTRIBUTED_LIBS_DIR/$lib"
  fi
done

if need_install yui build/yui/yui.js YUI 3.6.0 ; then
  echo Installing YUI
  unzip "$DISTRIBUTED_LIBS_DIR/yui_3.6.0.zip" -d $RUNTIME_HOME
fi

# Prepare files for static serving
. "$(dirname "$0")/static.sh"

# Delete existing files: *.pyc
find "$SOURCE_DIR" -iname "*.pyc" -exec rm -f {} \;
