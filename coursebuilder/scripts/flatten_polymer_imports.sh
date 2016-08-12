# Copyright 2016 Google Inc. All Rights Reserved.
#
# Script that generates all-imports.html files for polymer apps.

# Don't invoke flatten_polymer_imports.sh directly.
# common.sh (and others) must source it instead.
flatten_script="${BASH_ARGV[0]}"

if [ "$ALLOW_STATIC_SERV" = true ] ; then
  export PYTHONPATH="$BEAUTIFULSOUP_PATH:$PYTHONPATH"
  python "$(dirname "${flatten_script}")/flatten_polymer_imports.py"
fi
