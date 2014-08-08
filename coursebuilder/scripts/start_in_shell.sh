#! /bin/sh

# Copyright 2012 Google Inc. All Rights Reserved.
#
# author: psimakov@google.com (Pavel Simakov)

#
# This script starts local developer Google AppEngine server for integration
# tests and initializes it with a default data set.
#
# Run this script from the coursebuilder/ folder:
#     sh ./scripts/start_in_shell.sh
#

usage () { cat <<EOF


Usage: $0 [-f] [-s] [-p <port>] [-a <admin_port>] [-h]

-f  Don't clear datastore on start
-s  Use $HOME/.cb_data as storage path.  This is useful for
    saving bench-test data across runs of release.py.
-p <port>  Set the port the CourseBuilder server listens on (defaults to 8081)
-a <port>  Set the port the AppEngine admin server listens on (defaults to 8000)
-h  Show this message

EOF
}

CLEAR_DATASTORE='true'
STORAGE_PATH_ARGUMENT=''
ADMIN_PORT=8000
CB_PORT=8081
while getopts fsp:a:h option
do
    case $option
    in
        f)  CLEAR_DATASTORE='false';;
        s)  data_path="$HOME/.cb_data"
            mkdir -p "$data_path"
            STORAGE_PATH_ARGUMENT=--storage_path="$data_path"
            ;;
        p)  CB_PORT="$OPTARG" ;;
        a)  ADMIN_PORT="$OPTARG" ;;
        h)  usage; exit 1;;
        *)  usage; exit 1;;
    esac
done

# Force shell to fail on any errors.
set -e


. "$(dirname "$0")/common.sh"

echo Starting GAE development server
exec python $GOOGLE_APP_ENGINE_HOME/dev_appserver.py \
    --host=0.0.0.0 --port=$CB_PORT --admin_port=$ADMIN_PORT \
    --clear_datastore=$CLEAR_DATASTORE \
    $STORAGE_PATH_ARGUMENT \
    --datastore_consistency_policy=consistent \
    --max_module_instances=1 \
    "$SOURCE_DIR"
