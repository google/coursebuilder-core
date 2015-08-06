#! /bin/bash

# Copyright 2014 Google Inc. All Rights Reserved.
#
# Wrapper script to launch PyLint ( http://www.pylint.org/ ) against
# CourseBuilder sources.  This script is automatically run as part of
# run_all_tests.py, and can be used on individual files; run with -h
# option to get the "help" text on options and usage.

set -e

function usage() { cat <<EOF
Usage: $0 [-p <parallelism>] [list-of-python-file-names]

-p Set the maximum number of lint jobs to run in parallel

With no file names given, all .py files in the CourseBuilder installation are
checked.  When specific files are named, only those files are processed.

EOF
}

# ------------------------------------------------------------------------------
# Parse arguments
#
parallelism=12
while getopts p: option; do
  case $option
    in
    p)  parallelism=$OPTARG ;;
    *)  usage; exit 1 ;;
  esac
done

OPTIND=$(( OPTIND - 1 ))
args=( $@ )
files=( ${args[@]:$OPTIND} )
if [[ ${#files[@]} -gt 0 ]] && [[ $parallelism -gt ${#files[@]} ]] ; then
  parallelism=${#files[@]}
fi

# ------------------------------------------------------------------------------
# Configure paths common to installation.
#
. "$(dirname "$0")/config.sh"
export PYTHONPATH=$PYTHONPATH:\
$FANCY_URLLIB_PATH:\
$JINJA_PATH:\
$WEBAPP_PATH:\
$WEBOB_PATH:\
$YAML_PATH:\
$SIX_PATH:\
$SOURCE_DIR:\
$SOURCE_DIR:\
$GOOGLE_APP_ENGINE_HOME:\
$RUNTIME_HOME/logilab:\
$RUNTIME_HOME/logilab/astroid:\
$RUNTIME_HOME/oauth2client

# ------------------------------------------------------------------------------
# Set up work variables
#
start_time=$( date +%s )
cd $COURSEBUILDER_HOME
if [[ ${#files[@]} -eq 0 ]] ; then
  files=( $( find . -name "*.py" | grep -v '\.#' ) )
fi
total=${#files[@]}
failures=0
echo "Linting: Checking ${#files[@]} files with parallelism of $parallelism..."

# ------------------------------------------------------------------------------
# Main loop: As long as we have any pending files or active lint jobs
#
while [[ ${#files[@]} -gt 0 ]] || [[ ${#jobs[@]} -gt 0 ]] ; do

  # If there are any files left and any job-slots open, start linters.
  while [[ ${#jobs[@]} -lt $parallelism ]] && [[ ${#files[@]} -gt 0 ]] ; do
    filename=${files[0]}
    files=(${files[@]:1})  # shift array to drop item at index 0
    if [[ $filename =~ (^|/)tests/ ]] ; then
      IGNORE_FOR_TESTS[0]=--disable=protected-access
      IGNORE_FOR_TESTS[1]=--disable=unbalanced-tuple-unpacking
      IGNORE_FOR_TESTS[2]=--disable=unpacking-non-sequence
    else
      IGNORE_FOR_TESTS=''
    fi
    python $RUNTIME_HOME/logilab/pylint/lint.py \
      --rcfile=$COURSEBUILDER_HOME/scripts/pylint.rc \
      ${IGNORE_FOR_TESTS[@]} \
      $filename &
    jobs[$!]=$filename  # Map PID to filename
  done

  # Don't just spin; pause to allow jobs to make some progress.
  sleep 1

  # Check which jobs have completed, and check their exit status.
  for pid in ${!jobs[@]}; do
    set +e
    kill -0 $pid >/dev/null 2>&1
    if [[ $? -ne 0 ]] ; then
      wait $pid  # Child is dead; this should be instantaneous
      job_status=$?
      if [[ $job_status -ne 0 ]] ; then
        failures=$(( failures + 1 ))
      fi
      jobs[$pid]='completed...'
      unset jobs[$pid]
    fi
    set -e
  done

  # Report on progress every so often.
  if [[ $(( $(date +%s) % 20 )) -eq 0 ]] ; then
    done=$(( $total - ${#files[@]} - ${#jobs[@]} ))
    echo "Linting: $done files done with $failures failures." \
      "${#files[@]} pending; ${#jobs[@]} active."
  fi
done

# ------------------------------------------------------------------------------
# Status report
#
end_time=$( date +%s )
echo "Linting: $total files done in $((end_time-start_time)) seconds" \
  "with $failures failures"
exit $( [[ $failures -eq 0 ]] )
