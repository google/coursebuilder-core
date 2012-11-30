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
#
# @author: psimakov@google.com (Pavel Simakov)

"""Allows export of Lessons and Units to other systems."""

import verify, os
from datetime import datetime

RELEASE_TAG = "1.0"


def Echo(x):
  pass


def ExportToJavaScript(fname, text, date):
  file = open("%s.js" % fname, 'w')
  file.write("// Course Builder %s JavaScript Export on %s\n" % (RELEASE_TAG, date))
  file.write("// begin\n")
  file.write("\n".join(text))
  file.write("\n// end");
  file.close()


def ExportToPython(fname, lines, date):
  code = []
  code.append("class Array(dict):")
  code.append("  pass")
  code.append("")
  code.append("true = True")
  code.append("false = False")
  code.append("")
  code.append("def init():")
  for line in lines:
    code.append("  %s" % line)
  code.append("")
  code.append("if __name__ == \"__main__\":")
  code.append("  init()")    
    
  file = open("%s.py" % fname, 'w')
  file.write("# Course Builder %s Python Export on %s\n" % (RELEASE_TAG, date))
  file.write("# begin\n")
  file.write("\n".join(code))
  file.write("\n# end");
  file.close()


def ExportToFile(fname, text):
  date = datetime.utcnow()
  ExportToJavaScript(fname, text, date)
  ExportToPython(fname, text, date)
  

if __name__ == "__main__":
  print "Export started using %s" % os.path.realpath(__file__)

  verifier = verify.Verifier()
  errors = verifier.LoadAndVerifyModel(Echo)
  if errors and len(errors) != 0:
    raise Exception(
        "Please fix all errors reported by tools/verify.py before continuing!")

  fname = os.path.join(os.getcwd(), "coursebuilder_course")
  ExportToFile(fname, verifier.export)
  print "Export complete to %s" % fname

