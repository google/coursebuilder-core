# Copyright 2012 Google Inc. All Rights Reserved.
#
# author: psimakov@google.com (Pavel Simakov)

#
# This script starts local developer Google AppEngine server and initializes it
# with the default data set.
#
# Run this script from the coursebuilder/ folder:
#     sh ./scripts/start.sh
#

# Force shell to fail on any errors.
set -e

. "$(dirname "$0")/parse_start_args.sh"

# Maintain this list of arguments in parallel with those in start_in_shell.sh
start_cb_server="python $GOOGLE_APP_ENGINE_HOME/dev_appserver.py \
    --host=0.0.0.0 --port=$CB_PORT --admin_port=$ADMIN_PORT \
    --clear_datastore=$CLEAR_DATASTORE \
    --datastore_consistency_policy=consistent \
    --max_module_instances=1 \
    --skip_sdk_update_check=true \
    $STORAGE_PATH_ARGUMENT \
    \"$SOURCE_DIR\""

echo "Starting GAE development server in a new shell"

if [[ $OSTYPE == linux* ]] ; then
  /usr/bin/xterm -e "$start_cb_server" &
elif [[ $OSTYPE == darwin* ]] ; then
  run_script=$( mktemp /tmp/XXXXXXXX )
  echo "$start_cb_server" > $run_script
  chmod 755 $run_script
  open -a Terminal.app $run_script
else
  echo "TODO: Support non-linux launch of CourseBuilder from new terminal"
  exit 1
fi

echo Waiting for server startup
sleep 10

echo "Opening browser windows pointing to an end user and an admin interface"
if [[ $OSTYPE == linux* ]] ; then
  /opt/google/chrome/chrome http://localhost:$ADMIN_PORT/ &
  /opt/google/chrome/chrome http://localhost:$CB_PORT/ &
elif [[ $OSTYPE == darwin* ]] ; then
  open -a "Google Chrome".app http://localhost:$ADMIN_PORT/
  open -a "Google Chrome".app http://localhost:$CB_PORT/
else
  echo "TODO: Support non-linux launch of CourseBuilder from new terminal"
  exit 1
fi

echo Done!
