# Copyright 2012 Google Inc. All Rights Reserved.
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

"""Allows export of Lessons and Units to other systems."""

__author__ = 'psimakov@google.com (Pavel Simakov)'

from datetime import datetime
import os

import verify

RELEASE_TAG = '1.0'


def echo(unused_x):
    pass


JS_GCB_REGEX = """
function gcb_regex(base, modifiers) {
    // NB: base should already have backslashes escaped
    return new RegExp(base, modifiers);
}

"""


def export_to_javascript(filename, lines, date):
    """Creates JavaScript export function from given lines and writes a file."""
    code = []
    code.append(JS_GCB_REGEX)
    code.append('function gcb_import(){')
    for line in lines:
        if line:
            code.append('  %s' % line)
        else:
            code.append('')
    code.append('')
    code.append('  course = Array();')
    code.append('  course["units"] = units;')
    code.append('  course["assessments"] = assessments;')
    code.append('  return course;')
    code.append('}')

    afile = open('%s.js' % filename, 'w')
    afile.write('// Course Builder %s JavaScript Export on %s\n' % (
        RELEASE_TAG, date))
    afile.write('// begin\n')
    afile.write('\n'.join(code))
    afile.write('\n// end')
    afile.close()


PYTHON_GCB_REGEX = """
import re
def gcb_regex(base, modifiers):
    flags = 0
    if 'i' in modifiers:
        flags |= re.IGNORECASE
    if 'm' in modifiers:
        flags |= re.MULTILINE
    return re.compile(base, flags)

"""


def export_to_python(filename, lines, date):
    """Creates Python export function from given lines and writes a file."""
    code = []
    code.append('class Array(dict):')
    code.append('  pass')
    code.append('')
    code.append('true = True')
    code.append('false = False')
    code.append(PYTHON_GCB_REGEX)
    code.append('def gcb_import():')
    for line in lines:
        code.append('  %s' % line)
    code.append('')
    code.append('  course = Array();')
    code.append('  course["units"] = units;')
    code.append('  course["assessments"] = assessments;')
    code.append('  return course;')

    afile = open('%s.py' % filename, 'w')
    afile.write('# Course Builder %s Python Export on %s\n' % (
        RELEASE_TAG, date))
    afile.write('# begin\n')
    afile.write('\n'.join(code))
    afile.write('\n# end')
    afile.close()


# TODO(psimakov): implement PHP_GCB_REGEX, but it's unclear how to return a new
# regexp object in PHP. maybe see http://www.regular-expressions.info/php.html


def export_to_php(filename, lines, date):
    """Creates PHP export function from given lines and writes a file."""
    code = []
    code.append('function gcb_import(){')
    for line in lines:
        if line:
            code.append('  $%s' % line)
        else:
            code.append('')
    code.append('')
    code.append('  $course = Array();')
    code.append('  $course["units"] = $units;')
    code.append('  $course["assessments"] = $assessments;')
    code.append('  return $course;')
    code.append('}')

    afile = open('%s.php' % filename, 'w')
    afile.write('<?php\n')
    afile.write('// Course Builder %s PHP Export on %s\n' %
                (RELEASE_TAG, date))
    afile.write('// begin\n')
    afile.write('\n'.join(code))
    afile.write('\n// end')
    afile.write('?>')
    afile.close()


def export_to_file(filename, lines):
    date = datetime.utcnow()
    export_to_javascript(filename, lines, date)
    export_to_python(filename, lines, date)
    export_to_php(filename, lines, date)


if __name__ == '__main__':
    print 'Export started using %s' % os.path.realpath(__file__)

    verifier = verify.Verifier()
    errors = verifier.load_and_verify_model(echo)
    if errors:
        raise Exception('Please fix all errors reported by tools/verify.py '
                        'before continuing!')

    fname = os.path.join(os.getcwd(), 'coursebuilder_course')
    export_to_file(fname, verifier.export)
    print 'Export complete to %s' % fname
