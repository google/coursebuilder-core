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

usage () { echo "Options: -f don't clear datastore; -h show this message"; }

CLEAR_DATASTORE='true'
while getopts fh option
do
    case $option
    in
        f)  CLEAR_DATASTORE='false';;
        h)  usage; exit 0;;
        *)  usage; exit 1;;
    esac
done

# Force shell to fail on any errors.
set -e


. "$(dirname "$0")/common.sh"

echo Starting GAE development server in a new shell
gnome-terminal -e "python $GOOGLE_APP_ENGINE_HOME/dev_appserver.py \
    --host=0.0.0.0 --port=8080 \
    --clear_datastore=$CLEAR_DATASTORE \
    --datastore_consistency_policy=consistent \
    --max_module_instances=1 \
    \"$SOURCE_DIR\""

echo Waiting for server startup
sleep 3

echo Opening browser windows pointing to an end user and an admin interface
/opt/google/chrome/chrome http://localhost:8080/ &
/opt/google/chrome/chrome http://localhost:8000/ &

echo Done!
