# Copyright 2016 Google Inc. All Rights Reserved.
#
# Script that generates all-imports.html files for polymer apps.
#
# Don't call this.  Let common.sh call it.

if [ "$ALLOW_STATIC_SERV" = true ] ; then
  export PYTHONPATH="$BEAUTIFULSOUP_PATH:$PYTHONPATH"
  python "$(dirname "$0")/flatten_polymer_imports.py"
fi
