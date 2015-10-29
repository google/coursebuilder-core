#!/bin/bash

# Copyright 2014 Google Inc. All Rights Reserved.
#
# Wrapper script for tools/etl/etl.py that sets up the environment correctly.
#
# Run this script as follows:
#     sh ./scripts/etl.sh <arguments>
#
# ETL's arguments are involved; pass --help for details. You will need to
# provide OAuth2 credentials when using ETL on one of your running instances.
#
# Some sample command lines for your convenience. They assume you are running
# etl.sh from the root directory of your Course Builder deployment. Items in
# <brackets> are variable and depend on your deployment as follows:
#
# <archive_path>: a path on local disk to the file you are downloading to or
#     uploading from.
# <course_url_prefix>: the slug of your course. If you created a course named
#     'my_course', this will be '/my_course'.
# <datastore_types>: a comma-delimited list of datastore entity types (for
#     example, 'FileMetadataEntity,Student') that you want to operate on.
# <locales>: a comma-delimited list of locales (for example, 'en,fr,ln') that
#     you want to operate on.
# <server>: the server of the App Engine deployment you want to run your ETL
#     command against. For dev, this is 'localhost'. If you have a prod
#     deployment at foo.appspot.com, this is 'foo.appspot.com'.
#
# To download all course definition data:
#
#   sh scripts/etl.sh download course /<course_url_prefix> <server> \
#     --archive_path <archive_path>
#
# To upload all course definition data:
#
#   sh scripts/etl.sh upload course /<course_url_prefix> <server> \
#     --archive_path <archive_path>
#
# To download all datastore entities from a course:
#
#   sh scripts/etl.sh download datastore /<course_url_prefix> <server> \
#     --archive_path <archive_path>
#
# To upload all datastore entities to a course:
#
#   sh scripts/etl.sh upload datastore /<course_url_prefix> <server> \
#     --archive_path <archive_path>
#
# To download datastore entities of specific types from a course:
#
#   sh scripts/etl.sh download datastore /<course_url_prefix> <server> \
#     --archive_path <archive_path> --datastore_types <datastore_types>
#
# To upload datastore entities of specific types to a course:
#
#   sh scripts/etl.sh upload datastore /<course_url_prefix> <server> \
#     --archive_path <archive_path> --datastore_types <datastore_types>
#
# To delete translations for all locales:
#
#   sh scripts/etl.sh run modules.i18n_dashboard.jobs.DeleteTranslations \
#     /<course_url_prefix> <server>
#
# To delete translations for specific locales:
#
#   sh scripts/etl.sh run modules.i18n_dashboard.jobs.DeleteTranslations \
#     /<course_url_prefix> <server> --job_args='--locales <locales>'
#
# To download translations for all locales:
#
#   sh scripts/etl.sh run modules.i18n_dashboard.jobs.DownloadTranslations \
#     /<course_url_prefix> <server> --job_args='<archive_path>'
#
# To download translations for specific locales:
#
#   sh scripts/etl.sh run modules.i18n_dashboard.jobs.DownloadTranslations \
#     /<course_url_prefix> <server> \
#     --job_args='<archive_path> --locales <locales>'
#
# To demo translations by creating rEVERSE cASE translations in the 'ln' locale:
#
#   sh scripts/etl.sh run modules.i18n_dashboard.jobs.TranslateToReversedCase \
#     /<course_url_prefix> <server> \
#
# To upload translations from a local .zip or .po archive:
#
#   sh scripts/etl.sh run modules.i18n_dashboard.jobs.UploadTranslations \
#     /<course_url_prefix> <server> --job_args='<archive_path>'

set -e

. "$(dirname "$0")/common.sh"

# Configure the Python path so ETL can find all required libraries.
# NOTE: if you have customized Course Builder and put any code in locations not
# on this path, you will need to add your new paths here. Otherwise, ETL may
# fail at runtime (if it can't, for example, find some new models you wrote).
export PYTHONPATH=\
$FANCY_URLLIB_PATH:\
$JINJA_PATH:\
$WEBAPP_PATH:\
$WEBOB_PATH:\
$YAML_PATH:\
$PYTHONPATH

python "$TOOLS_DIR/etl/etl.py" "$@"
