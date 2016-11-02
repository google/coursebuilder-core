#!/usr/bin/env bash

# Copyright 2016 Google Inc. All Rights Reserved.
#
# author: tlarsen@google.com (Todd Larsen)

# Sequentially re-run failed tests (and also known b/28723700 test flakes).
#
# scripts/rerun_flakes.sh --help for usage and examples.

# This script is not expecting to be sourced from other scripts. (Otherwise,
# logic like that near the top of scripts/common.sh is necessary.)
rerun_failures_script="$0"

cb_dir() {
  # Locates the coursebuilder/ parent directory of the "$1" script path.
  local script="$1"
  local reldir="$( dirname "$script" )"
  local absdir="$( cd "$reldir" && pwd )"
  local dir="$(basename "$absdir")"

  while [ "$dir" != "coursebuilder" ]; do
    local parent="$(dirname "$absdir")"
    absdir="$(cd "$parent" && pwd)"
    dir="$(basename "$absdir")"
  done
  echo "$absdir"
}

# Set shell variables common to CB scripts.
. $(cb_dir "${rerun_failures_script}")/core/scripts/config.sh

# Log file (e.g. /tmp/project_py_160815_163642.log) in which to find 'ERROR:'
# and 'FAIL:' lines and re-run the corresponding failed tests.
DEFAULT_ERRORS_LOG_FILENAME="b28723700_flakes.log"
DEFAULT_ERRORS_LOG_PATH="${INTERNAL_SCRIPTS_DIR}/${DEFAULT_ERRORS_LOG_FILENAME}"
opt_error_log="${DEFAULT_ERRORS_LOG_PATH}"

# Directory (typically '/tmp') where the --server_log_file for each re-run test
# will be created, as specified by the -s or --server_log_dir. If unspecified,
# --server_log_file is not supplied to scripts/project.py.
opt_server_log_dir=""

# If non-zero, the 'ERROR:' and 'FAIL:' lines in the opt_error_log file
# will be extracted (matched) and printed, but no actual tests will be re-run.
opt_list_errors_only=0

displayUsage() {
  local exit_code="$1"
  local error_msg="$2"
  if [ -n "${error_msg}" ]; then
    echo "ERROR: ${error_msg}" 1>&2
  fi
  echo
  echo "USAGE:"
  echo "${rerun_failures_script} \\"
  echo "  [-e <errors_log_path>] | [--errors_in[=]<errors_log_path>] \\"
  echo "  [-s <server_log_dir>] | [--server_log_dir[=]<server_log_dir>] \\"
  echo "  [-l | --list_errors_only] \\"
  echo "  -- --<any_following_flags> --<or_options> --<passed_to_project_py>"
  echo
  echo "Not specifying --errors_log_path results in a default file being used:"
  echo "  coursebuilder/internal/scripts/${DEFAULT_ERRORS_LOG_FILENAME}"
  echo
  echo "By default, --server_log_dir is unspecified, and so --server_log_file"
  echo "is *NOT* supplied to scripts/project.py for each --test run."
  echo
  if [ -n "${exit_code}" ]; then
    exit ${exit_code}
  fi
}

HORIZONTAL_RULING_LINE="----------------------------------------\
---------------------------------------"

displayHelp() {
  local exit_code="$1"

  # No exit_code to displayUsage, or it exits this script before the examples
  # below can be displayed.
  displayUsage

  echo "${HORIZONTAL_RULING_LINE}"
  echo "EXAMPLES:"
  echo
  echo "Run this script from the coursebuilder source directory."
  echo "  cd google3/experimental/coursebuilder"
  echo "  scripts/rerun_failures.sh"
  echo
  echo "To re-run tests from `project.py --also_log_to_file` output:"
  echo "  scripts/rerun_failures.sh -e /tmp/project_py_YYMMDD_HHMMSS.log"
  echo "  scripts/rerun_failures.sh --errors_log_path=./tests.log"
  echo
  echo "To keep the --server_log_file from each test, specify a log directory:"
  echo "  scripts/rerun_failures.sh -s /tmp"
  echo "  scripts/rerun_failures.sh --server_log_dir=/tmp"
  echo
  echo "Running from google3/ also works:"
  echo "  experimental/coursebuilder/scripts/rerun_failures.sh -s /tmp"
  echo
  echo "To pass additional flags to scripts/project.py:"
  echo "  scripts/rerun_failures.sh -- --skip_integration_setup --verbose"
  echo "  scripts/rerun_failures.sh -s /tmp -- --skip_integration_setup"
  echo
  echo "Prefix with a DISPLAY variable to have test Chrome instances run in"
  echo "an xvfb headless display:"
  echo "  DISPLAY=:99 scripts/rerun_failures.sh"
  echo "or a Chrome Remote Desktop:"
  echo "  DISPLAY=:20 scripts/rerun_failures.sh"
  echo
  exit ${exit_code}
}

optspec=":ehls-:"

while getopts "$optspec" optchar; do
  case "${optchar}" in
    -)
      case "${OPTARG}" in
        errors_in|e)
          opt_error_log="${!OPTIND}"; OPTIND=$(( $OPTIND + 1 ))
          ;;
        errors_in=*)
          opt_error_log=${OPTARG#*=}
          ;;
        list_errors_only|l)
          opt_list_errors_only=1
          ;;
        server_log_dir|s)
          opt_server_log_dir="${!OPTIND}"; OPTIND=$(( $OPTIND + 1 ))
          ;;
        server_log_dir=*)
          opt_server_log_dir=${OPTARG#*=}
          ;;
        help|h)
          displayHelp 0
          ;;
        *)
          displayUsage 1 "Unknown option: --${OPTARG}"
          ;;
      esac
      ;;
    e)
      opt_error_log="${!OPTIND}"; OPTIND=$(( $OPTIND + 1 ))
      ;;
    l)
      opt_list_errors_only=1
      ;;
    s)
      opt_server_log_dir="${!OPTIND}"; OPTIND=$(( $OPTIND + 1 ))
      ;;
    h)
      displayHelp 0
      ;;
    *)
      displayUsage 1 "Unknown option: -${OPTARG}"
      ;;
  esac
done

# All arguments after those consumed by getopts are expected to be flags or
# options that are passed unchanged to scripts/project.py.
shift $((OPTIND-1))
opt_args_after_double_dash=( "$@" )

cmd() {
  # Constructs a project.py command line with flags, both for display and eval.
  local method="$1" ; local class="$2" ; local log="$3"
  local -a flags=( "${@:4}" )

  echo "python \"${SCRIPTS_DIR}/project.py\" \\"
  echo "  --test=\\" ; echo "${class}.\\" ; echo -n "$method"

  if [ -n "${log}" ]; then
    echo " \\" ; echo "  --server_log_file=\\" ; echo -n "$log"
  fi

  for flag in "${flags[@]}" ; do
    echo " \\" ;  echo -n "  $flag"
  done

  echo " \\" ; echo "  2>&1"
}

appserver() {
  # Detects the broken state resulting from dev_appserver already running.
  local -a lines=( "$@" ) ; local -i ok=1
  local msg="$(echo "${lines[*]}" | grep -i "failed to bind to port")" ; ok=$?
  if [ $ok -eq 0 ]; then
    echo -n "$(sed -e 's/[[:space:]]*$//' <<<$msg)  "
    echo "dev_appserver running?"
    return 1
  fi
  return 0
}

completed() {
  # Finds the "result" progress message in the lines of project.py output.
  local -a lines=( "$@" ) ; local -i missing=1 ; local ifs=$IFS ; IFS=$'\n'
  local -a found=( $(echo "${lines[@]}" | grep "1 completed") )
  missing=$? ; IFS=$ifs
  if [ $missing -ne 0 ]; then
    return 1
  fi
  # Only keep the first occurrence of the "1 completed" progress message.
  echo "${found[0]}" | cut -d ' ' -f 5-12
  return 0
}

# Accumulates list of tests that have been run.
runs=( )

# Accumulates list of tests that failed.
failures=( )

# Accumulates list of tests that succeeded.
sucesses=( )

runTest() {
  # Runs one test method of the supplied test class.
  local method="$1" ; local class="$2" ; local dir="$3"
  local -a flags=( "${@:4}" ) ; local log="" ; local -i ok=1
  local now="$(date +%y%m%d_%H%M%S)"
  local test="${class}.${method}"
  runs+=( "$test" )

  if [ -n "$dir" ]; then
    log="${dir}/${method}_${now}.log"
  fi

  local run="$(cmd "$method" "$class" "$log" "${flags[@]}")"
  local -a lines=$(eval "$run")

  local -i missing=1 ; local final=""
  local result=$(completed "${lines[*]}") ; missing=$?
  if [ $missing -eq 0 ]; then
    final="$result"
  fi

  if [ -z "$final" ]; then
    local running=$(appserver "${lines[*]}") ; missing=$? ; passed=0
    if [ $missing -eq 0 ]; then
      failure="$running"  # dev_appserver appears to be running.
    else
      failure="TEST FAILED TO COMPLETE?"  # No "1 completed" found at all.
    fi
  else
    # "1 completed" line found, now check to see if that test failed.
    failure=$(echo "$final" | grep "1 failed") ; passed=$?
  fi
  if [ $passed -eq 0 ]; then
    failures+=( "$test" )
    echo "FAILURE: $failure" ; echo ; echo "${lines[@]}" ; echo
    # If --server_log_dir was present, reconstruct the displayed command
    # line with a new --server_log_file flag having a later timestamp for
    # the log file name.
    if [ -n "$log" ]; then
      now="$(date +%y%m%d_%H%M%S)"
      log="${dir}/${method}_${now}.log"
      run="$(cmd "$method" "$class" "$log" "${flags[@]}")"
    fi
    echo "TO RE-RUN ONLY THIS FAILED TEST:" ; echo ; echo "$run"
  else
    echo "SUCCESS: $final"
    successes+=( "$test" )
  fi
}

testMethod() {
  echo "$1" | cut -d ' ' -f 2
}

testClass() {
  echo "$1" | cut -d '(' -f 2 | cut -d ')' -f 1
}

errorType() {
  echo "$1" | cut -d ':' -f 1
}

# A list of all 'ERROR:' or 'FAIL:' lines found in opt_error_log.
error_lines=( )

readAllErrorLines() {
  local log_path="$1"
  while read line; do
    local not_error=1
    echo "$line" | grep -q '^\(ERROR\|FAIL\): '
    not_error=$?
    if [ ${not_error} -eq 0 ]; then
      error_lines+=( "$line" )
    fi
  done <"${log_path}"
}

rerunTests() {
  local server_log_dir="$1"
  local -a flags=( "${@:2}")

  # Runs any tests that indicated 'ERROR:' in the supplied log file.
  for line in "${error_lines[@]}"; do
    local error="$(errorType "$line")"
    local method="$(testMethod "$line")"
    local class="$(testClass "$line")"
    echo "${HORIZONTAL_RULING_LINE}"
    echo "${error}: ${method}" ; echo "FROM: ${class}"
    runTest "$method" "$class" "${server_log_dir}" "${flags[@]}" ; echo
  done
}

main() {
  local -a test_args=( "$@" )
  local -i num_args="${#test_args[@]}"

  readAllErrorLines "${opt_error_log}"
  local -i num_errors="${#error_lines[@]}"

  if [ ${num_errors} -eq 0 ]; then
    echo
    echo "WARNING: No 'ERROR:' or 'FAIL:' tests found in:"
    echo "${opt_error_log}"
    displayUsage 1
  fi

  echo
  echo "${HORIZONTAL_RULING_LINE}"
  echo -n "Found     *** ${num_errors} ***     "
  echo "'ERROR:' or 'FAIL:' test failure(s) in:"
  echo "  ${opt_error_log}"
  echo

  if [ ${opt_list_errors_only} -eq 0 ]; then

    if [ -n "${opt_server_log_dir}" ]; then
      echo -n "${num_errors} --test runs"
      echo " will save a unique --server_log_file in this --server_log_dir:"
      echo "  ${opt_server_log_dir}"
      echo
    fi

    if [ ${num_args} -ne 0 ]; then
      echo -n "${num_errors} --test runs"
      echo " will be supplied these additional arguments:"
      for arg in "${test_args[@]}"; do
        echo "  ${arg}"
      done
      echo
    fi

    echo -n "${num_errors} --test failures"
    echo " ('ERROR:' or 'FAIL:') being re-run serially now:"

    rerunTests "${opt_server_log_dir}" "${test_args[@]}"
    echo "${HORIZONTAL_RULING_LINE}"
    echo "TESTS RUN:   ${#runs[@]}"
    echo
    echo "PASSED:      ${#successes[@]}"
    echo

    for success in "${successes[@]}" ; do
      echo "$success"
    done
    echo

    echo "FAILED:      ${#failures[@]}"
    echo
    for failure in "${failures[@]}" ; do
      echo "$failure"
    done
  else
    echo "${num_errors} --test runs disabled by --list_errors_only (-l):"
    echo
    for line in "${error_lines[@]}" ; do
      local error="$(errorType "$line")"
      local method="$(testMethod "$line")"
      local class="$(testClass "$line")"
      echo "${error}: ${class}.${method}"
    done
  fi

  echo "${HORIZONTAL_RULING_LINE}"
  echo
}

main "${opt_args_after_double_dash[@]}"
