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

"""File specifying custom certificate criteria functions.

Course authors may specify custom criteria for award of a certificate.
In order to be invoked, all of the following must all apply:
  * The function name is specified as a custom_criteria field
    in the certificate_criteria group of course.yaml.
  * The function name is added to the registration_table whitelist below.
  * The function is defined in this module.
The arguments and return type of the function are described in
example_custom_criterion below.
"""

__author__ = 'Glenn De Jonghe (gdejonghe@google.com)'


from models import transforms

# List of str. Holds whitelist of function names which maybe invoked by
# the certificate_criteria > custom_criteria fields in course.yaml.
registration_table = ['example_custom_criterion', 'power_searching_criteria']


def example_custom_criterion(unused_student, unused_course):
    """Example of what a custom criterion function should look like.

    Adapt or insert new functions with the same signature for custom criteria.
    Add the name of the function to the registration_table if it's an actual
    criterion.

    This example criterion will award a certificate to every student
    in the course.

    Args:
        unused_student: models.models.Student. The student entity to test.
        unused_course: modesl.courses.Course. The course which the student is
            enrolled in. Test on this to implement course-specific criteria for
            earning a certificate.

    Returns:
        Boolean value indicating whether the student satisfies the criterion.
    """
    return True


def power_searching_criteria(student, unused_course):
    """Criteria for Power Searching with Google."""
    scores = transforms.loads(student.scores or '{}')
    final_assessment_score = scores.get('Fin', 0)
    return final_assessment_score > 66
