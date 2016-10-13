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
cached=0
updated_on=$(date +%s)

function log_time {
    echo $(date +"%Y/%m/%d %H:%M:%S")
}

echo $(log_time)"     Linting started:" \
  "${#files[@]} files with parallelism of $parallelism."

# ------------------------------------------------------------------------------
# Make a directory for caching of lint results; prepare pylint.rc file metadata
#
LINT_CACHE_DIR=$RUNTIME_HOME/coursebuilder/pylint_cache/
if [ ! -d "$LINT_CACHE_DIR" ]; then
  echo $(log_time)"     Creating new cache" \
    "directory $LINT_CACHE_DIR"
  mkdir -p $LINT_CACHE_DIR
fi

pylint_rc="$COURSEBUILDER_HOME/scripts/pylint.rc"
meta_content_rc="pylint_rc_size: "$(stat -c %s "$pylint_rc")
meta_content_rc=$meta_content_rc", pylint_rc_age: "$(stat -c %Y "$pylint_rc")

# ------------------------------------------------------------------------------
# Main loop: As long as we have any pending files or active lint jobs
#
while [[ ${#files[@]} -gt 0 ]] || [[ ${#jobs[@]} -gt 0 ]] ; do

  # If there are any files left and any job-slots open, start linters.
  while [[ ${#jobs[@]} -lt $parallelism ]] && [[ ${#files[@]} -gt 0 ]] ; do
    filename=${files[0]}
    files=(${files[@]:1})  # shift array to drop item at index 0
    if [[ $filename =~ (^|/)tests/ || $filename =~ modules/.*_tests.py ]] ; then
      IGNORE_FOR_TESTS[0]=--disable=protected-access
      IGNORE_FOR_TESTS[1]=--disable=unbalanced-tuple-unpacking
      IGNORE_FOR_TESTS[2]=--disable=unpacking-non-sequence
      IGNORE_FOR_TESTS[3]=--disable=too-many-statements
    else
      IGNORE_FOR_TESTS=''
    fi

    # if file has not changed in size and timestamp, we can skip linting; we
    # keep the file's size and timestamp in a new file with a name derived
    # from the filename; we also add the size and the age of pylint.rc file,
    # to catch changes in linting rules
    meta_filename="$LINT_CACHE_DIR"$(echo "$filename.meta" | tr / _)
    meta_content="file_size: "$(stat -c %s "$filename")
    meta_content=$meta_content", file_age: "$(stat -c %Y "$filename")
    meta_content=$meta_content"; "$meta_content_rc
    if [ -f "$meta_filename" ]; then
        old_meta_content="$(< $meta_filename)"
        if [ "$meta_content" = "$old_meta_content" ]; then
          cached=$(( cached + 1 ))
          echo "NOOP" > /dev/null &
          jobs[$!]=$filename  # Map PID to filename
          continue
        else:
          rm $meta_filename
        fi
    fi

    # do the linting
    python $RUNTIME_HOME/logilab/pylint/lint.py \
      --rcfile=$COURSEBUILDER_HOME/scripts/pylint.rc \
      ${IGNORE_FOR_TESTS[@]} \
      $filename && echo $meta_content > $meta_filename &
    jobs[$!]=$filename  # Map PID to filename
  done

  # Don't just spin; pause to allow jobs to make some progress.
  sleep 0.1

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
  if [[ $(( $(date +%s) - $updated_on )) -gt 10 ]] ; then
    updated_on=$(date +%s)
    done=$(( $total - ${#files[@]} - ${#jobs[@]} ))
    echo $(log_time)"     Linting progress: $done done;" \
      "$failures failed; $cached cached/skipped; ${#files[@]} pending;" \
      "${#jobs[@]} active."
  fi
done

# ------------------------------------------------------------------------------
# Status report
#
end_time=$( date +%s )
echo $(log_time)"     Linting done in $((end_time-start_time)) seconds:" \
  "$total done; $failures failed; $cached cached/skipped."

exit $( [[ $failures -eq 0 ]] )
