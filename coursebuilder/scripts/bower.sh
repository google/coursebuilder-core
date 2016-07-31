#! /bin/bash

#
# Copyright 2015 Google Inc. All Rights Reserved.
#

# author: psimakov@google.com (Pavel Simakov)

#
# This script builds a distributable package of Polymer framework
# dependencies used by Course Builder.
#
# This file requires bower (http://bower.io), which can be installed
# as follows:
#   npm install -g bower
#
# To build a distributable package of all necessary components run:
#    ./bower.sh
#

# Force shell to fail on any errors.
set -e

OUTPUT_NAME="polymer-1.2.0.zip"
SCRIPT_HOME="$(dirname "$0")"

pushd $SCRIPT_HOME

echo Working in $SCRIPT_HOME.
if [ -d "./bower_components/" ]; then
  echo Error: Found existing dir $SCRIPT_HOME/bower_components/. Remove and retry.
  exit 1
fi
if [ -f "./$OUTPUT_NAME" ]; then
  echo Error: Found existing dir $SCRIPT_HOME/$OUTPUT_NAME. Remove and retry.
  exit 1
fi

echo Installing all Polymer components and dependencies.
bower install --config.interactive=false

echo Removing non-essential files from all components.
# folders */demo/*, */test/* and */tests/* and all contained files
find ./bower_components/ -path "*/demo/*" -delete
find ./bower_components/ -type d -name "demo" -delete
find ./bower_components/ -path "*/test/*" -delete
find ./bower_components/ -type d -name "test" -delete
find ./bower_components/ -path "*/tests/*" -delete
find ./bower_components/ -type d -name "tests" -delete
find ./bower_components/ -path "*/.*" -delete
find ./bower_components/ -type d -name ".*" -delete
# individual files
find ./bower_components/ -type f -name "README.md" -delete
find ./bower_components/ -type f -name "CONTRIBUTING.md" -delete
find ./bower_components/ -type f -name "bower.json" -delete


echo Zip things up into $SCRIPT_HOME/$OUTPUT_NAME.
cp ./bower.json ./bower_components/
pushd ./bower_components
zip -r ../$OUTPUT_NAME *
popd

echo Cleaning up
rm -rf ./bower_components/

popd

echo Done! Find results in $SCRIPT_HOME/$OUTPUT_NAME.
