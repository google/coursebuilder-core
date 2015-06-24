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

CLEAR_DATASTORE=true
STORAGE_PATH_ARGUMENT=''
ADMIN_PORT=8000
CB_PORT=8081
while getopts fd:sp:a:h option
do
    case $option
    in
        f)  CLEAR_DATASTORE=false;;
        d)  data_path="$OPTARG";;
        s)  data_path="$HOME/.cb_data";;
        p)  CB_PORT="$OPTARG" ;;
        a)  ADMIN_PORT="$OPTARG" ;;
        h)  usage; exit 0;;
        *)  usage; exit 1;;
    esac
done

if [ "$data_path" ] ; then
    mkdir -p "$data_path"
    STORAGE_PATH_ARGUMENT=--storage_path="\"$data_path\""
fi

. "$(dirname "$0")/common.sh"

start_cb_server="python $GOOGLE_APP_ENGINE_HOME/dev_appserver.py \
    --host=0.0.0.0 --port=$CB_PORT --admin_port=$ADMIN_PORT \
    --clear_datastore=$CLEAR_DATASTORE \
    --datastore_consistency_policy=consistent \
    --max_module_instances=1 \
    --skip_sdk_update_check=true \
    $STORAGE_PATH_ARGUMENT \
    \"$SOURCE_DIR\""
