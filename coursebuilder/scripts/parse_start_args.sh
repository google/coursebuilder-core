my_dir="$(dirname "$0")"

usage () { cat <<EOF


Usage: $0 [-f] [-d <data_path>] [-s] [-p <port>] [-a <admin_port>] [-h]

-f  Don't clear storage on start
-d <dir>  Set the storage path
-s  Set the storage path to $HOME/.cb_data
-p <port>  Set the port the CourseBuilder server listens on (defaults to 8081)
-a <port>  Set the port the AppEngine admin server listens on (defaults to 8000)
-h  Show this message

EOF
}

ADMIN_PORT=8000
CB_PORT=8081
CLEAR_DATASTORE=true
DATA_PATH=''

while getopts fd:sp:a:x:h option
do
    case $option
    in
        f)  CLEAR_DATASTORE=false;;
        d)  DATA_PATH="$OPTARG";;
        s)  DATA_PATH="$HOME/.cb_data";;
        p)  CB_PORT="$OPTARG" ;;
        a)  ADMIN_PORT="$OPTARG" ;;
        h)  usage; exit 0;;
        *)  usage; exit 1;;
    esac
done

. "$(dirname "$0")/common.sh"

# This constructs the command so that it can be used in both start.sh and
# start_in_shell.sh, which each require different quoting of the arguments.
#
# If you wish to change this, please ensure that these things still work:
# start.sh
# start.sh -sf
# start.sh -d ~/"foo bar"
# start_in_shell.sh
# start_in_shell.sh -sf
# start_in_shell.sh -d ~/"foo bar"
#
# Also, ensure that coursebuilder terminates after running test.sh on a selenium
# test, or that run_all_tests.sh shuts down gracefully at the end, since these
# scripts make use of start_in_shell.sh.

start_cb_server=( python "$GOOGLE_APP_ENGINE_HOME/dev_appserver.py" \
    --admin_port=$ADMIN_PORT \
    --clear_datastore=$CLEAR_DATASTORE \
    --datastore_consistency_policy=consistent \
    --host=0.0.0.0 \
    --max_module_instances=1 \
    --port=$CB_PORT \
    --skip_sdk_update_check=true )

if [ "$DATA_PATH" ] ; then
    mkdir -p "$DATA_PATH"
    start_cb_server+=("--storage_path=$DATA_PATH")
fi

start_cb_server+=("$SOURCE_DIR")
