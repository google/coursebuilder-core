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

"""Utility functions common to analytics module."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import os
import sys

import appengine_config


def _generators_for_analytics(analytics):
    ret = set()
    for analytic in analytics:
        ret.update(analytic.generator_classes)
    return ret


def _get_required_generators(source_class):
    """Allow client code to return list or single instance.  Convert to list."""

    ret = []
    required = source_class.required_generators()
    if required:
        try:
            ret.extend(required)
        except TypeError:
            ret.append(required)
    return ret


def _get_template_dir_names(analytic=None):
    """Find directories in which the template for this analytic can be found.

    Always includes the CourseBuilder base install directory and the
    directory for the analytics module.

    Args:
        analytic: If the analytic is non-blank, we will also include the
            directories of all of the data sources and generators specified
            for that analytic.  This behavior permits simple naming of
            templates as just their base names, as long as they are in
            the same directory as the code that provides their content.
    Returns:
        Array of directories in which to seek a template.  Note that the
        CourseBuilder root directory is always listed first so that fully
        qualified paths (e.g. "modules/my_new_module/my_template.html")
        will always work.)
    """

    # Always add root of CB install first, to permit disambiguation of
    # same-named files by specifying full path.  Note that here, we're
    # using CODE_ROOT, not BUNDLE_ROOT - the latter refers to course
    # content, and the former to the supporting code.
    ret = [
        appengine_config.CODE_ROOT,
        os.path.join(appengine_config.CODE_ROOT, 'modules', 'analytics')]

    if analytic:
        # Add back path to source/generator classes, minus the .py file
        # in which the handler class exists.
        for source_class in analytic.data_source_classes:
            ret.append(os.path.join(appengine_config.CODE_ROOT, os.path.dirname(
                sys.modules[source_class.__module__].__file__)))
        for generator_class in analytic.generator_classes:
            ret.append(os.path.join(appengine_config.CODE_ROOT, os.path.dirname(
                sys.modules[generator_class.__module__].__file__)))
    return ret
