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

CHROMEDRIVER_VERSION=2.10
CHROMEDRIVER_DIR=$RUNTIME_HOME/chromedriver-$CHROMEDRIVER_VERSION
if [[ $OSTYPE == linux* ]] ; then
  NODE_DOWNLOAD_FOLDER=node-v0.10.1-linux-x64
  CHROMEDRIVER_ZIP=chromedriver_linux64.zip
elif [[ $OSTYPE == darwin* ]] ; then
  NODE_DOWNLOAD_FOLDER=node-v0.10.1-darwin-x64
  CHROMEDRIVER_ZIP=chromedriver_mac32.zip
else
  echo "TARGET_OS must be one of linux or macos"
  exit -1
fi

# Ensure that ~/coursebuilder_resources is available to write
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
fi

# Configures the runtime environment.
PYTHONPATH=$SOURCE_DIR:$GOOGLE_APP_ENGINE_HOME:$RUNTIME_HOME/oauth2client
PATH=$RUNTIME_HOME/node/bin:$RUNTIME_HOME/phantomjs/bin:$CHROMEDRIVER_DIR:$PATH
export YUI_BASE=$RUNTIME_HOME/yui/build
export KARMA_LIB=$RUNTIME_HOME/karma_lib

CB_ARCHIVE_URL=https://github.com/google/coursebuilder-resources/raw/master/lib

echo Ensuring runtime folder $RUNTIME_HOME
if [ ! -d "$RUNTIME_HOME" ]; then
  mkdir -p $RUNTIME_HOME
fi

echo Using GAE from $GOOGLE_APP_ENGINE_HOME
if [ ! -d "$GOOGLE_APP_ENGINE_HOME" ]; then
  echo Installing GAE
  mkdir -p $RUNTIME_HOME
  wget https://storage.googleapis.com/appengine-sdks/deprecated/199/google_appengine_1.9.9.zip -O google_appengine_1.9.9.zip
  unzip google_appengine_1.9.9.zip -d $RUNTIME_HOME/
  mv $RUNTIME_HOME/google_appengine $GOOGLE_APP_ENGINE_HOME
  rm google_appengine_1.9.9.zip
fi

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
    | sed -e "s/.*$version_finder* //" -e 's/ .*//' )
  if [ "$version" != "$expected_version" ] ; then
    echo "Expected version '$expected_version' for $package_name, but" \
      "instead had '$version'.  Removing and reinstalling."
    rm -rf $package_dir
    return 0
  fi
  return 1
}

if need_install webtest PKG-INFO Version: 2.0.14 ; then
  wget https://pypi.python.org/packages/source/W/WebTest/WebTest-2.0.14.zip -O webtest-download.zip
  unzip webtest-download.zip -d $RUNTIME_HOME
  rm webtest-download.zip
  mv $RUNTIME_HOME/WebTest-2.0.14 $RUNTIME_HOME/webtest
fi

if need_install six PKG-INFO Version: 1.5.2 ; then
  echo Installing six '(a Python 2.x/3.x compatibility bridge)'
  wget https://pypi.python.org/packages/source/s/six/six-1.5.2.tar.gz -O six-1.5.2.tar.gz
  tar --gunzip --extract --verbose --directory $RUNTIME_HOME --file six-1.5.2.tar.gz
  rm six-1.5.2.tar.gz
  mv $RUNTIME_HOME/six-1.5.2 $RUNTIME_HOME/six
fi

if need_install beautifulsoup4 PKG-INFO Version: 4.3.2 ; then
  echo Installing Beautiful Soup HTML processing library
  wget https://pypi.python.org/packages/source/b/beautifulsoup4/beautifulsoup4-4.3.2.tar.gz -O beautifulsoup4-4.3.2.tar.gz
  tar --gunzip --extract --verbose --directory $RUNTIME_HOME --file beautifulsoup4-4.3.2.tar.gz
  rm beautifulsoup4-4.3.2.tar.gz
  mv $RUNTIME_HOME/beautifulsoup4-4.3.2 $RUNTIME_HOME/beautifulsoup4
fi

if need_install selenium PKG-INFO Version: 2.35.0 ; then
  echo Installing Selenium
  wget https://pypi.python.org/packages/source/s/selenium/selenium-2.35.0.tar.gz -O selenium-download.tgz
  tar xzf selenium-download.tgz --directory $RUNTIME_HOME
  rm selenium-download.tgz
  mv $RUNTIME_HOME/selenium-2.35.0 $RUNTIME_HOME/selenium
fi

if [ ! -x $CHROMEDRIVER_DIR/chromedriver ] ; then
  echo Installing Chromedriver
  wget http://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/$CHROMEDRIVER_ZIP -O chromedriver-download.zip
  unzip chromedriver-download.zip -d $CHROMEDRIVER_DIR
  chmod a+x $CHROMEDRIVER_DIR/chromedriver
  rm chromedriver-download.zip
fi

if need_install node ChangeLog Version 0.10.1 ; then
  echo Installing Node.js
  wget http://nodejs.org/dist/v0.10.1/$NODE_DOWNLOAD_FOLDER.tar.gz -O node-download.tgz
  tar xzf node-download.tgz --directory $RUNTIME_HOME
  mv $RUNTIME_HOME/$NODE_DOWNLOAD_FOLDER $RUNTIME_HOME/node
  rm node-download.tgz
  echo Installing Karma
  $RUNTIME_HOME/node/bin/npm install -g karma@0.8.7
fi

if need_install phantomjs ChangeLog Version 1.9.0 ; then
  echo Installing PhantomJs
  wget https://phantomjs.googlecode.com/files/phantomjs-1.9.0-linux-x86_64.tar.bz2 -O phantomjs-download.bz2
  tar xjf phantomjs-download.bz2 --directory $RUNTIME_HOME
  mv $RUNTIME_HOME/phantomjs-1.9.0-linux-x86_64 $RUNTIME_HOME/phantomjs
  rm phantomjs-download.bz2
fi

if need_install karma_lib 'jasmine-jquery*.js' Version 1.5.2 ; then
  echo Installing required karma lib files
  mkdir -p $RUNTIME_HOME/karma_lib
  wget $CB_ARCHIVE_URL/jasmine-jquery-1.5.2.js
  mv jasmine-jquery-1.5.2.js $RUNTIME_HOME/karma_lib
fi

DISTRIBUTED_LIBS="\
  babel-0.9.6.zip \
  gaepytz-2011h.zip \
  inputex-3.1.0.zip \
  yui_2in3-2.9.0.zip \
  yui_3.6.0.zip \
  google-api-python-client-1.1.zip \
  pyparsing-1.5.7.zip \
  html5lib-0.95.zip \
  httplib2-0.8.zip \
  python-gflags-2.0.zip \
  mrs-mapreduce-0.9.zip \
  mapreduce-r645.zip \
  markdown-2.5.zip \
  crossfilter-1.3.7.zip \
  d3-3.4.3.zip \
  dc.js-1.6.0.zip \
  oauth-1.0.1.zip \
  mathjax-2.3.0.zip \
  mathjax-fonts-2.3.0.zip \
  codemirror-4.5.0.zip \
"

echo Using third party Python packages from $DISTRIBUTED_LIBS_DIR
if [ ! -d "$DISTRIBUTED_LIBS_DIR" ]; then
  mkdir -p "$DISTRIBUTED_LIBS_DIR"
fi
for lib in "$DISTRIBUTED_LIBS_DIR"/*; do
  fname=$( basename "$lib" )
  if [[ "$DISTRIBUTED_LIBS" != *" $fname "* ]]; then
    echo "Warning: extraneous CB distribution runtime library file $lib"
  fi
done
for lib in $DISTRIBUTED_LIBS ; do
  if [ ! -f "$DISTRIBUTED_LIBS_DIR/$lib" ]; then
    echo "Adding CB distribution runtime library $lib to $DISTRIBUTED_LIBS_DIR"
    wget $CB_ARCHIVE_URL/$lib -P "$DISTRIBUTED_LIBS_DIR"
  fi
done

if need_install yui build/yui/yui.js YUI 3.6.0 ; then
  echo Installing YUI
  unzip "$DISTRIBUTED_LIBS_DIR/yui_3.6.0.zip" -d $RUNTIME_HOME
fi

# "Deleting existing files: *.pyc"
find "$SOURCE_DIR" -iname "*.pyc" -exec rm -f {} \;
