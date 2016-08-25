# Force shell to fail on any errors.
set -e

if [[ -z $1 ]]; then
  usage
  exit 1
fi

# Reinstall AE runtime environment and CB-distributed libs if necessary.
. "$(dirname "$0")/common.sh" > /dev/null

. "$(dirname "$0")/test_config.sh"

python "$SOURCE_DIR/tests/suite.py" \
  --test_class_name "$1" "${@:2}"
