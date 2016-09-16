# Copyright 2015 Google Inc. All Rights Reserved.
#
# Script that generates static.yaml and prepares resources for static serving.

# Force shell to fail on any errors.
set -e

LN_TARGET="$COURSEBUILDER_RESOURCES"
LN_SOURCE="$SOURCE_DIR/lib"

# Declare resources subject to static serving. OS X is still on bash 3.x, so we
# have to fake out associative arrays rather than use declare -A.
STATIC_SERV=( \
    "codemirror-4.5.0:/static/codemirror"
    "crossfilter-1.3.7:/static/crossfilter-1.3.7"
    "d3-3.4.3:/static/d3-3.4.3"
    "dagre-0.7.4:/static/dagre-0.7.4"
    "dagre-d3-0.4.17p:/static/dagre-d3-0.4.17p"
    "dc.js-1.6.0:/static/dc.js-1.6.0"
    "dependo-0.1.4:/static/dependo-0.1.4"
    "inputex-3.1.0:/static/inputex-3.1.0"
    "jquery-2.2.4:/static/jquery"
    "jqueryui-1.11.4:/static/jqueryui"
    "material-design-iconic-font-1.1.1:/static/material-design-icons"
    "underscore-1.4.3:/static/underscore-1.4.3"
    "yui_2in3-2.9.0:/static/2in3"
    "yui_3.6.0:/static/yui_3.6.0"
    "polymer-1.2.0:/static/polymer-1.2.0" \
)

# Prepare files for static serving
if [ "$ALLOW_STATIC_SERV" = true ] ; then
  echo Static serving enabled

  # Prepare target directory for static files; use symlink to
  # $COURSEBUILDER_RESOURCES to avoid polluting current view
  if [ ! -d "$LN_TARGET/_static/" ]; then
    mkdir "$COURSEBUILDER_RESOURCES/_static/"
  fi
  if [ ! -L "$LN_SOURCE/_static" -a ! -d "$LN_SOURCE/_static" ]; then
    ln -s "$COURSEBUILDER_RESOURCES/_static/" "$LN_SOURCE/"
  fi

  # Unzip required files
  for entry in "${STATIC_SERV[@]}"; do
    KEY="${entry%%:*}"
    if [ ! -f "$LN_SOURCE/_static/$KEY/.gcb_install_succeeded" ]; then
      echo "Unzipping $KEY.zip into $LN_SOURCE/_static/$KEY"
      unzip -o "$DISTRIBUTED_LIBS_DIR/$KEY.zip" \
          -d "$LN_SOURCE/_static/$KEY" > /dev/null
      touch "$LN_SOURCE/_static/$KEY/.gcb_install_succeeded"
    fi
  done
else
  echo Static serving disabled

  # Remove all static files
  if [ -d "$LN_TARGET/_static/" ]; then
    rm -rf "$LN_TARGET/_static/"
  fi
  if [ -L "$LN_SOURCE/_static" ]; then
    rm "$LN_SOURCE/_static"
  fi
fi

# Generate static serving config file; we do pay special attention to '\n'
# characters and their expansion
STATIC_YAML_TEXT=""
STATIC_YAML_TEXT="# GENERATED; DO NOT MODIFY"$'\n'
STATIC_YAML_TEXT+=$"env_variables:"$'\n'
STATIC_YAML_TEXT+=$"  GCB_STATIC_SERV_ENABLED: $ALLOW_STATIC_SERV"$'\n'
if [ "$ALLOW_STATIC_SERV" = true ] ; then
  STATIC_YAML_TEXT+=$"handlers:"$'\n'
  for entry in "${STATIC_SERV[@]}"; do
    KEY=${entry%%:*}
    VALUE=${entry#*:}
    STATIC_YAML_TEXT+=$"- url: $VALUE"$'\n'
    STATIC_YAML_TEXT+=$"  static_dir: lib/_static/$KEY"$'\n'
    STATIC_YAML_TEXT+=$"  expiration: 10m"$'\n'
  done

  # Also serve a directory for html imports
  STATIC_YAML_TEXT+=$"- url: /static/html-imports"$'\n'
  STATIC_YAML_TEXT+=$"  static_dir: lib/_static/html-imports"$'\n'
  STATIC_YAML_TEXT+=$"  expiration: 10m"$'\n'
fi

# '\n' at EOF is truncated, unless followed by another character, like ' '
STATIC_YAML_TEXT+=$' '

# Write out a new static.yaml, if content differs or file does not exist;
# we do NOT want to override this file all the time as there maybe another
# test running concurrently that uses it at this very moment
STATIC_YAML="$SOURCE_DIR/static.yaml"
CURRENT_STATIC_YAML_TEXT=""
if [ -f "$STATIC_YAML" ]; then
  CURRENT_STATIC_YAML_TEXT=$(< "$STATIC_YAML")
fi
if [ "$CURRENT_STATIC_YAML_TEXT" = "$STATIC_YAML_TEXT" ]; then
  echo Using current "$STATIC_YAML"
else
  echo Creating new "$STATIC_YAML"
  echo "$STATIC_YAML_TEXT" > "$STATIC_YAML"
fi
