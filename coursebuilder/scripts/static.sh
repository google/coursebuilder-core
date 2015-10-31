# Copyright 2015 Google Inc. All Rights Reserved.
#
# Script that generates static.yaml and prepares resources for static serving.

# Force shell to fail on any errors.
set -e

LN_TARGET="$COURSEBUILDER_RESOURCES"
LN_SOURCE="$SOURCE_DIR/lib"

# Declare resources subject to static serving
declare -A STATIC_SERV
STATIC_SERV["codemirror-4.5.0"]="codemirror"
STATIC_SERV["inputex-3.1.0"]="inputex-3.1.0"
STATIC_SERV["yui_2in3-2.9.0"]="2in3"
STATIC_SERV["yui_3.6.0"]="yui_3.6.0"
STATIC_SERV["d3-3.4.3"]="d3-3.4.3"
STATIC_SERV["dc.js-1.6.0"]="dc.js-1.6.0"
STATIC_SERV["crossfilter-1.3.7"]="crossfilter-1.3.7"
STATIC_SERV["underscore-1.4.3"]="underscore-1.4.3"
STATIC_SERV["material-design-iconic-font-1.1.1"]="material-design-icons"
STATIC_SERV["dependo-0.1.4"]="dependo-0.1.4"

# Prepare files for static serving
if [ "$ALLOW_STATIC_SERV" = true ] ; then
  echo Static serving enabled

  # Prepare target directory for static files; use symlink to
  # $COURSEBUILDER_RESOURCES to avoid polluting current view
  if [ ! -d "$LN_TARGET/_static/" ]; then
    mkdir $COURSEBUILDER_RESOURCES/_static/
  fi
  if [ ! -L "$LN_SOURCE/_static" ]; then
    ln -s $COURSEBUILDER_RESOURCES/_static/ $LN_SOURCE/
  fi

  # Unzip required files
  for K in "${!STATIC_SERV[@]}"; do
    if [ ! -f "$LN_SOURCE/_static/$K/.gcb_install_succeeded" ]; then
      echo "Unzipping $K.zip into $LN_SOURCE/_static/$K"
      unzip -o "$DISTRIBUTED_LIBS_DIR/$K.zip" \
          -d "$LN_SOURCE/_static/$K" > /dev/null
      touch "$LN_SOURCE/_static/$K/.gcb_install_succeeded"
    fi
  done
else
  echo Static serving disabled

  # Remove all static files
  if [ -d "$LN_TARGET/_static/" ]; then
    rm -rf $LN_TARGET/_static/
  fi
  if [ -L "$LN_SOURCE/_static" ]; then
    rm $LN_SOURCE/_static
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
  for K in "${!STATIC_SERV[@]}"; do
    STATIC_YAML_TEXT+=$"- url: /static/${STATIC_SERV[$K]}"$'\n'
    STATIC_YAML_TEXT+=$"  static_dir: lib/_static/$K"$'\n'
    STATIC_YAML_TEXT+=$"  expiration: 10m"$'\n'
  done
fi

# '\n' at EOF is truncated, unless followed by another character, like ' '
STATIC_YAML_TEXT+=$' '

# Write out a new static.yaml, if content differs or file does not exist;
# we do NOT want to override this file all the time as there maybe another
# test running concurrently that uses it at this very moment
STATIC_YAML=$SOURCE_DIR/static.yaml
CURRENT_STATIC_YAML_TEXT=""
if [ -f "$STATIC_YAML" ]; then
  CURRENT_STATIC_YAML_TEXT="$(< $STATIC_YAML)"
fi
if [ "$CURRENT_STATIC_YAML_TEXT" = "$STATIC_YAML_TEXT" ]; then
  echo Using current $STATIC_YAML
else
  echo Creating new $STATIC_YAML
  echo "$STATIC_YAML_TEXT" > $STATIC_YAML
fi
