# Copyright 2014 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Messages used in the data_pump module."""

__author__ = [
    'johncox@google.com (John Cox)',
]


DATASET_NAME = """
This is the name of the BigQuery dataset to which to pump the tables. If it is
not set, it will default to the name of this course.
"""

JSON_KEY = """
This is the JSON key for the instance where BigQuery is to be run.
"""

PII_ENCRYPTION_TOKEN = """
This encryption secret is used to obscure PII fields when they are pushed to
BigQuery. It will be automatically generated after all required fields are
satisfied and you click 'Save'.
"""

PROJECT_ID = """
This is the ID of the Google Cloud project to which to send data.
"""

TABLE_LIFETIME = """
This is the amount of time a table pushed to BigQuery will last. Specify with
"w" or "d" to represent weeks or days. If blank, the default of 30 days (i.e.,
30d) will be used.
"""
