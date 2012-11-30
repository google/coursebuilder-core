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

"""Allows export of Lessons and Units to other JavaScript or PHP systems."""

import verify, os
from datetime import datetime

RELEASE_TAG = "1.0"


def Echo(x):
  pass


def ExportToFile(fname, text):
  file = open(fname, 'w')
  file.write("// Course Builder %s Export on %s\n" % (RELEASE_TAG, datetime.utcnow()))
  file.write("// begin\n")
  file.write(text)
  file.write("\n// end");
  file.close()


if __name__ == "__main__":
  print "Export started using %s" % os.path.realpath(__file__)

  verifier = verify.Verifier()
  erros = verifier.LoadAndVerifyModel(Echo)
  if erros and len(errors) != 0:
    raise Exception(
        "Please fix all errors reported by tools/verify.py before continuing!")

  fname = os.path.join(os.getcwd(), "coursebuilder-manifest.js")
  ExportToFile(fname, "\n".join(verifier.export))
  print "Export complete to %s" % fname

