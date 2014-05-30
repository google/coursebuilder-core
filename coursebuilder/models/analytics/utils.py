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


def _generators_for_visualizations(visualizations):
    ret = set()
    for visualization in visualizations:
        ret.update(visualization.generator_classes)
    return ret


def _rest_data_source_classes(visualizations):
    ret = set()
    for visualization in visualizations:
        ret.update(visualization.rest_data_source_classes)
    return ret


def _get_template_dir_names(visualization=None):
    """Find directories where the template for this visualization can be found.

    Always includes the CourseBuilder base install directory and the
    directory for the analytics module.

    Args:
        visualization: If the visualization is non-blank, we will also include
            the directories of all of the data sources and generators
            specified for that visualization.  This behavior permits simple
            naming of templates as just their base names, as long as they are
            in the same directory as the code that provides their content.

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
        os.path.join(appengine_config.CODE_ROOT, 'modules', 'visualizations')]

    if visualization:
        # Add back path to source/generator classes, minus the .py file
        # in which the handler class exists.
        for source_class in visualization.data_source_classes:
            ret.append(os.path.join(appengine_config.CODE_ROOT, os.path.dirname(
                sys.modules[source_class.__module__].__file__)))
        for generator_class in visualization.generator_classes:
            ret.append(os.path.join(appengine_config.CODE_ROOT, os.path.dirname(
                sys.modules[generator_class.__module__].__file__)))
    return ret
