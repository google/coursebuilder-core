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

CHROMIUM_TARGET_VERSION=43.0.2357.130
set +e
cb_chromium_browser=`which chromium-browser`
set -e
if [[ -z "$cb_chromium_browser" ]] ; then
  echo
  echo "==================================================================="
  echo "WARNING: No Chromium browser found, integration tests will not run."
  echo "==================================================================="
  echo
else
  export CB_CHROMIUM_BROWSER="$cb_chromium_browser"
  chromium_version=`chromium-browser --product-version`
  if [[ "$chromium_version" != "$CHROMIUM_TARGET_VERSION" ]] ; then
    echo
    echo "=============================================================="
    echo "WARNING: Running Chromium version $chromium_version for tests."
    echo "The target version is $CHROMIUM_TARGET_VERSION."
    echo "=============================================================="
    echo
  fi
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
  chmod u+x "$SOURCE_DIR/scripts/pylint.sh"
fi

# Configures the runtime environment.
export PYTHONPATH=$SOURCE_DIR:$GOOGLE_APP_ENGINE_HOME:$RUNTIME_HOME/oauth2client
PATH=$RUNTIME_HOME/node/node_modules/karma/bin\
:$RUNTIME_HOME/node/bin\
:$RUNTIME_HOME/phantomjs/bin\
:$CHROMEDRIVER_DIR\
:$PATH
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
  curl --location --silent https://storage.googleapis.com/appengine-sdks/deprecated/1921/google_appengine_1.9.21.zip -o google_appengine_1.9.21.zip
  unzip google_appengine_1.9.21.zip -d $RUNTIME_HOME/
  mv $RUNTIME_HOME/google_appengine $GOOGLE_APP_ENGINE_HOME
  rm google_appengine_1.9.21.zip
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
    | sed -e "s/.*$version_finder* *//" -e 's/ .*//' )
  if [ "$version" != "$expected_version" ] ; then
    echo "Expected version '$expected_version' for $package_name, but" \
      "instead had '$version'.  Removing and reinstalling."
    rm -rf $package_dir
    return 0
  fi
  return 1
}

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

if need_install beautifulsoup4 PKG-INFO Version: 4.3.2 ; then
  echo Installing Beautiful Soup HTML processing library
  curl --location --silent https://pypi.python.org/packages/source/b/beautifulsoup4/beautifulsoup4-4.3.2.tar.gz -o beautifulsoup4-4.3.2.tar.gz
  tar --gunzip --extract --verbose --directory $RUNTIME_HOME --file beautifulsoup4-4.3.2.tar.gz
  rm beautifulsoup4-4.3.2.tar.gz
  mv $RUNTIME_HOME/beautifulsoup4-4.3.2 $RUNTIME_HOME/beautifulsoup4
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
  ./bin/npm install jasmine-core@2.3.4 phantomjs@1.9.8 karma@0.12.36 \
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
  markdown-2.5.zip \
  material-design-iconic-font-1.1.1.zip \
  mathjax-2.3.0.zip \
  mathjax-fonts-2.3.0.zip \
  mrs-mapreduce-0.9.zip \
  networkx-1.9.1.zip \
  oauth-1.0.1.zip \
  pyparsing-1.5.7.zip \
  reportlab-3.1.8.zip \
  simplejson-3.7.1.zip \
  underscore-1.4.3.zip \
  yui_2in3-2.9.0.zip \
  yui_3.6.0.zip \
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
    curl --location --silent $CB_ARCHIVE_URL/$lib -o "$DISTRIBUTED_LIBS_DIR/$lib"
  fi
done

if need_install yui build/yui/yui.js YUI 3.6.0 ; then
  echo Installing YUI
  unzip "$DISTRIBUTED_LIBS_DIR/yui_3.6.0.zip" -d $RUNTIME_HOME
fi

# "Deleting existing files: *.pyc"
find "$SOURCE_DIR" -iname "*.pyc" -exec rm -f {} \;
