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


def Echo(x):
    pass


def ExportToJavaScript(fname, lines, date):
    file = open('%s.js' % fname, 'w')
    file.write('// Course Builder %s JavaScript Export on %s\n' %
               (RELEASE_TAG, date))
    file.write('// begin\n')
    code = []
    code.append('function gcb_import(){')
    for line in lines:
        if len(line) != 0:
            code.append('  %s' % line)
        else:
            code.append('')
    code.append('')
    code.append('  return units;')
    code.append('}')
    file.write('\n'.join(code))
    file.write('\n// end')
    file.close()


def ExportToPython(fname, lines, date):
    code = []
    code.append('class Array(dict):')
    code.append('  pass')
    code.append('')
    code.append('true = True')
    code.append('false = False')
    code.append('')
    code.append('def gcb_import():')
    for line in lines:
        code.append('  %s' % line)
    code.append('  return units')
    code.append('')
    code.append('if __name__ == \"__main__\":')
    code.append('  init()')

    file = open('%s.py' % fname, 'w')
    file.write('# Course Builder %s Python Export on %s\n' %
               (RELEASE_TAG, date))
    file.write('# begin\n')
    file.write('\n'.join(code))
    file.write('\n# end')
    file.close()


def ExportToPHP(fname, lines, date):
    file = open('%s.php' % fname, 'w')
    file.write('<?php\n')
    file.write('// Course Builder %s PHP Export on %s\n' % (RELEASE_TAG, date))
    file.write('// begin\n')
    code = []
    code.append('function gcb_import(){')
    for line in lines:
        if len(line) != 0:
            code.append('  $%s' % line)
        else:
            code.append('')
    code.append('')
    code.append('  return $units;')
    code.append('}')
    file.write('\n'.join(code))
    file.write('\n// end')
    file.write('?>')
    file.close()


def ExportToFile(fname, lines):
    date = datetime.utcnow()
    ExportToJavaScript(fname, lines, date)
    ExportToPython(fname, lines, date)
    ExportToPHP(fname, lines, date)


if __name__ == '__main__':
    print "Export started using %s" % os.path.realpath(__file__)

    verifier = verify.Verifier()
    errors = verifier.LoadAndVerifyModel(Echo)
    if errors and len(errors) != 0:
        raise Exception('Please fix all errors reported by tools/verify.py '
                        'before continuing!')

    fname = os.path.join(os.getcwd(), 'coursebuilder_course')
    ExportToFile(fname, verifier.export)
    print 'Export complete to %s' % fname
