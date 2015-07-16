#!/usr/bin/python

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

"""Manage fetching and installation of extension modules to CourseBuilder.

To run, use the wrapper script in this directory since it configures paths for
you:

  sh scripts/modules.sh --targets=<targets>

<targets> is a list of third-party modules that should be configured.
To remove a module, simply re-run this command, omitting the modules
you don't want incorporated.  (Every time this script is run, it enables
all of and only the targets mentioned.).

Targets consist of a name followed by an '@' character, and then a source URL.
If a target is available on the local machine (e.g., source code in a
different directory, possibly a different source-code control system),
you can specify it using a relative path (starting with "../", or an
absolute path by using the "file://" style of URI.  This will use symlinks
to incorporate the project, so you can continue editing the extension in
place while it is under development.

  sh scripts/modules.sh --targets=file:///home/my_user/src/my_project

This script also knows how to download projects from github, so you can
use the download URL for the project, as in:

  sh scripts/modules.sh \
    --targets=lti@https://github.com/google/coursebuilder-lti-module

Lastly, a few items have well-known GitHub addresses, so you can omit
the address for them.  See the WELL_KNOWN_MODULES variable below.

  sh scripts/modules.sh --targets=lti,xblock

"""

__author__ = 'Mike Gainer (mgainer@google.com)'

"""=============================================================================
For module authors:

To make a module that is installable by this script, you should provide the
following configuration/setup files:

--------------------------------------------------------------------------------
                               module.yaml

This file contains various configuration items describing your extension:
- module_name: The name of the Python module containing the
  register_module() function.  This should be the full module path from
  the base of the CourseBuilder installation, as set by your scripts/setup.sh
  script (see below) when it is run.  For example, if your module installs
  itself in a directory named 'foo', and the registration function is in
  'foo/setup.py', you would set this value to 'modules.foo.setup'.
- container_version: The oldest version of Course Builder with which this module
  is compatible, in major/minor/bugfix form.  E.g., 1, or 1.8 or 1.8.0
- third_party_libraries: A list of dicts, naming any third party libraries
  required by your module.  These are libraries that appear in the
  lib/ directory in the base coursebuilder install.  This field is not required
  if there are no such dependencies.
- appengine_libraries: A list of dicts, giving the name and version of any
  libraries provided by App Engine that your module needs.  See example for
  syntax.  This section is optional.
- tests: A list of name/value pairs giving the module/class and count of
  tests for your module.  See example for syntax.  This may be redundant
  with modules specified by Course Builder or other extension modules, but
  everyone must agree on the required version number.

Example contents of module.yaml
----------------------------------
module_name: modules.bar.bar_module
container_version: 1.6.0
tests:
  tests.ext.bar.bar_tests.BarTest: 1
appengine_libraries:
- name: endpoints
  version: "1.0"
third_party_libraries:
- name: foo_stuff-1.9.1.zip

--------------------------------------------------------------------------------
                               scripts/setup.sh

This file must exist, and be executable.  This script is your module's
opportunity to do any required setup operations.  The script is run in a shell
whose working directory is that of your module's install directory.  I.e., the
directory containing the "scripts" subdirectory.  Currently, it is presented
with two arguments: "-d" and the directory of the main Course Builder install.

The only mandatory thing your script must do is to softlink or copy its code
(softlink preferred) into the Course Builder modules/ directory, and tests
into the Course Builder tests/ext directory.  It is strongly suggested that
these be named modules/<your_module_name> and texts/ext/<your_module_name>
to prevent naming conflicts.

This script may also do patching of base files, if required.  Normally, this
will only affect course.yaml and other non-Python files.  If your module needs
to override behavior in Python files, you will be *much* more future-proof if
you restrict yourself to monkey-patching Python modules or functions when your
modules is registered rather than applying patches to the text of .py files.

Note that some convenience functions (check_directory, link_module, link_tests)
are provided for you by Course Builder's common.sh file.  See the example below
for usage.

Example minimal contents of setup.sh:
-------------------------------------
#!/bin/bash -x
if [[ "$1" == '-d' && -n "$2"  ]] ; then
  export MODULE_DIR=$( pwd )
  export CB_DIR="$2"
  ln -s $MODULE_DIR/modules/my_module $CB_DIR/modules/my_module
  ln -s $MODULE_DIR/tests/my_module $CB_DIR/tests/ext/my_module
else
  echo "Unexpected command line for setup.sh: $@"
  exit 1
fi

--------------------------------------------------------------------------------
                              tests/ext/<yourmodule>/...

Your module should come with unit and functional tests.  These should be
referenced from your module.yaml file (see above).  See the existing tests
in coursebuilder/tests/{unit,functional} for example code to crib from .


============================================================================="""

import argparse
import collections
import logging
import os
import re
import subprocess
import sys
import time

from common import yaml_files

# Standard name of manifest file within a module.
_MANIFEST_NAME = 'module.yaml'

# Number of attempts to kill wayward subprocesses before giving up entirely.
_KILL_ATTEMPTS = 5
# Time budget for setup.sh invocations.
_SETUP_SH_EXECUTION_MAX_SECONDS = 60 * 5

# Command line flags supported
PARSER = argparse.ArgumentParser()
PARSER.add_argument(
    '--targets', default=[], type=lambda s: s.split(','),
    help=(
        'List of modules to use.  Multiple modules may be listed separated by '
        'commas.  If a module has already been downloaded, or is on the '
        'list of well-known modules (see scripts/module_config.py source), '
        'then the module source need not be provided.  If the module needs '
        'to be downloaded, then the name of the module should be followed by '
        'an "@" character, and then the URL at which the module is '
        'available.  E.g.,  '
        '--targets=example@https://github.com/my-company/my_example_module'
        'The file:// style of URI may also be used; in this case a symlink '
        'is made.  This is useful while you are developing a module.  E.g., '
        '--modules=example@file:///home/my_user_name/src/example'
        ))

# Logging.
_LOG = logging.getLogger('coursebuilder.models.module_config')
logging.basicConfig()
_LOG.setLevel(logging.INFO)

# Convenience types with just data, no behavior.
WellKnownModule = collections.namedtuple(
    'WellKnownModule', ['name', 'method', 'location'])

# List of modules for which we already know the source location.
_WELL_KNOWN_MODULES = {
    'lti': WellKnownModule(
        'lti', 'git',
        'https://github.com/google/coursebuilder-lti-module'),
    'xblock': WellKnownModule(
        'xblock', 'git',
        'https://github.com/google/coursebuilder_xblock_module'),
}


def _die(message):
    _LOG.critical(message)
    raise Exception(message)


def _assert_path_exists(path, message):
    if not os.path.exists(path):
        _die(message)


def _run_process(args, patience_seconds=10):
    proc = subprocess.Popen(args)
    cmdline = ' '.join(args)
    start = time.time()
    max_expected = start + patience_seconds
    absolute_max = start + patience_seconds + _KILL_ATTEMPTS
    while time.time() < absolute_max:
        if time.time() > max_expected:
            proc.kill()
        proc.poll()
        if proc.returncode is not None:
            if proc.returncode == 0:
                return
            else:
                _die('The command "%s" completed with exit code %d.  Please '
                     'run that command manually, ascertain and remedy the '
                     'problem, and try again.' % (cmdline, proc.returncode))
                sys.exit(1)
    _die('The command "%s" failed to complete after %d seconds, and '
         '%d attempts to kill it.  You should manually kill the process.  '
         'Please run that command manually and ascertain and remedy the '
         'problem.' % (cmdline, int(time.time() - start), _KILL_ATTEMPTS))


def _download_if_needed(name, location, module_install_dir):
    manifest_path = os.path.join(module_install_dir, _MANIFEST_NAME)
    if os.path.exists(manifest_path):
        return
    _LOG.info('Downloading module %s', name)

    all_modules_dir = os.path.dirname(module_install_dir)
    if not os.path.exists(all_modules_dir):
        os.makedirs(all_modules_dir)

    if name in _WELL_KNOWN_MODULES:
        method = _WELL_KNOWN_MODULES[name].method
        if not location:
            location = _WELL_KNOWN_MODULES[name].location
    else:
        if not location:
            _die('Module "%s" needs to be downloaded, but its location was '
                 'not provided on the command line.' % name)
        method = _infer_method_from_location(location)

    if method == 'git':
        _run_process(['git', 'clone', location, module_install_dir])
    elif method == 'cp-r':
        _run_process(['cp', '-r', location, module_install_dir])
    elif method == 'softlink':
        location = re.sub(r'^file:/*(localhost)?/*', '', location)
        # Relative paths must always start with ../ so as not to refer to
        # something within the CB distribution itself.  If they do not so
        # start, assume they are absolute, and prepend a '/'.
        if not location.startswith('../'):
            location = '/' + location
        # Location may be relative, and if so, is relative to CB dir from
        # which we are running modules.sh.  Make absolute so it will also
        # work when softlinked at $HOME/$COURSEBUILDER_RESOURCES/modules
        location = os.path.abspath(location)
        _run_process(['ln', '--symbolic', location, module_install_dir])
    else:
        _die('We would like to download module "%s" ' % name +
             'from location "%s", ' % location +
             'but no implementation for downloading via %s ' % method +
             'has been implemented as yet.')

    _assert_path_exists(
        manifest_path,
        'Modules are expected to contain ' +
        'a manifest file named "%s" ' % _MANIFEST_NAME +
        'in their root directory when installed.  ' +
        'Module %s at path %s does not. ' % (name, manifest_path))


def _infer_method_from_location(location):
    # Not terribly sophisticated.  When modules start showing up at places
    # other than github, we can make this a little smarter.
    if location.startswith('https://github.com/'):
        return 'git'

    # For testing, and/or pulling in not-really-third party stuff from
    # elsewhere in a local work environment.
    if location.startswith('/tmp/') or location.startswith('/var/folders/'):
        return 'cp-r'

    # A file on the local host.  Softlink rather than copy, so original
    # can be edited in place and versioned using whatever config managment
    # software is appropriate.
    if location.startswith('../') or location.startswith('file://'):
        return 'softlink'

    return 'unknown'


def _install_if_needed(app_yaml, name, module_install_dir, coursebuilder_home):
    # Verify version compatibility before attempting installation.
    coursebuilder_version = app_yaml.get_env('GCB_PRODUCT_VERSION')
    module = yaml_files.ModuleManifest(
        os.path.join(module_install_dir, _MANIFEST_NAME))
    module.assert_version_compatibility(coursebuilder_version)

    # This is the best we can do as far as verifying that a module has been
    # installed.  Modules have quite a bit of free rein as far as what-all
    # they may or may not do -- setting up $CB/modules/<modulename> is the
    # only hard requirement.  Note that this may even be a softlink, so
    # we just test for existence, not is-a-directory.
    if os.path.exists(os.path.join(coursebuilder_home, 'modules', name)):
        return module
    _LOG.info('Installing module %s', name)

    # Verify setup script exists and give a nice error message if not (rather
    # than letting _run_process emit an obscure error).
    install_script_path = os.path.join(
        module_install_dir, 'scripts', 'setup.sh')
    _assert_path_exists(
        install_script_path,
        'Modules are expected to provide a script to perform installation of '
        'the module at <module-root>/scripts/setup.sh  No such file was found '
        'in module %s' % name)

    # Have $PWD set to the install directory for the module when calling
    # setup.sh, just in case the setup script needs to discover its own
    # location in order to set up softlinks.
    cwd = os.getcwd()
    try:
        os.chdir(module_install_dir)
        _run_process(
            ['bash', install_script_path, '-d', coursebuilder_home],
            patience_seconds=_SETUP_SH_EXECUTION_MAX_SECONDS)
    finally:
        os.chdir(cwd)

    # Verify setup script exists and give a nice error message if not (rather
    # than letting _run_process emit an obscure error).
    install_script_path = os.path.join(
        module_install_dir, 'scripts', 'setup.sh')
    init_file_path = os.path.join(
        coursebuilder_home, 'modules', name, '__init__.py')
    _assert_path_exists(
        init_file_path,
        'After installing module %s, there should have been an __init__.py '
        'file present at the path %s, but there was not.' % (
            name, init_file_path))

    return module


def _update_appengine_libraries(app_yaml, modules):
    for module in modules:
        for lib in module.appengine_libraries:
            app_yaml.require_library(lib['name'], lib['version'])


def _construct_third_party_libraries(modules):
    libs_str_parts = []
    libs = {}
    for module in modules:
        for lib in module.third_party_libraries:
            name = lib['name']
            internal_path = lib.get('internal_path')
            if lib['name'] in libs:
                if internal_path != libs[name]:
                    raise ValueError(
                        'Module %s ' % module.module_name +
                        'specifies third party library "%s" ' % name +
                        'with internal path "%s" ' % internal_path +
                        'but this is incompatible with the '
                        'already-specified internal path "%s"' % libs[name])
            else:
                if internal_path:
                    libs_str_parts.append(' %s:%s' % (name, internal_path))
                else:
                    libs_str_parts.append(' %s' % name)
    return ''.join(libs_str_parts)


def _update_third_party_libraries(app_yaml, modules):
    libs_str = _construct_third_party_libraries(modules)
    app_yaml.set_env('GCB_THIRD_PARTY_LIBRARIES', libs_str)


def _update_enabled_modules(app_yaml, modules):
    new_val = ' '.join([module.main_module for module in modules])
    app_yaml.set_env('GCB_THIRD_PARTY_MODULES', new_val)


def _update_tests(coursebuilder_home, modules):
    tests = {}
    for module in modules:
        tests.update(module.tests)

    yaml_path = os.path.join(coursebuilder_home, 'scripts',
                             'third_party_tests.yaml')
    if tests:
        _LOG.info('Updating scripts/third_party_tests.yaml')
        with open(yaml_path, 'w') as fp:
            fp.write('tests:\n')
            for test in sorted(tests):
                fp.write('  %s: %d\n' % (test, tests[test]))
    else:
        if os.path.exists(yaml_path):
            os.unlink(yaml_path)


def main(args, coursebuilder_home, modules_home):
    modules = []
    app_yaml = yaml_files.AppYamlFile(
        os.path.join(coursebuilder_home, 'app.yaml'))

    for module_name in args.targets:
        parts = module_name.split('@')
        name = parts[0]
        location = parts[1] if len(parts) > 1 else None
        install_dir = os.path.join(modules_home, name)
        _download_if_needed(name, location, install_dir)
        module = _install_if_needed(app_yaml, name, install_dir,
                                    coursebuilder_home)
        modules.append(module)

    _update_tests(coursebuilder_home, modules)
    _LOG.info('Updating app.yaml')
    _update_appengine_libraries(app_yaml, modules)
    _update_third_party_libraries(app_yaml, modules)
    _update_enabled_modules(app_yaml, modules)
    app_yaml.write()

    if app_yaml.application == 'mycourse':
        _LOG.warning('The application name in app.yaml is "mycourse".  You '
                     'should change this from its default value before '
                     'uploading to AppEngine.')


if __name__ == '__main__':
    main(PARSER.parse_args(),
         os.environ['COURSEBUILDER_HOME'],
         os.environ['MODULES_HOME'])
