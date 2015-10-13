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

"""Utilities for dashboard module.  Separated here to break include loops."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import os

import appengine_config

from common import safe_dom
from controllers import sites
from models import vfs

RESOURCES_PATH = '/modules/dashboard/resources'
RESOURCES_DIR = os.path.join(appengine_config.BUNDLE_ROOT,
                             RESOURCES_PATH.lstrip('/'))


def build_assets_url(action):
    return '/dashboard?action={action}'.format(action=action)


def list_files(app_context, subfolder, merge_local_files=False, all_paths=None):
    """Makes a list of files in a subfolder.

    Args:
        app_context: app_context.
        subfolder: string. Relative path of the subfolder to list.
        merge_local_files: boolean. If True, the returned list will
            contain files found on either the datastore filesystem or the
            read-only local filesystem. If a file is found on both, its
            datastore filesystem version will trump its local filesystem
            version.
        all_paths: list. A list of all file paths in the underlying file
            system.

    Returns:
        List of relative, normalized file path strings.
    """
    home = sites.abspath(app_context.get_home_folder(), '/')
    _paths = None
    if all_paths is not None:
        _paths = []
        for _path in all_paths:
            if _path.startswith(sites.abspath(
                    app_context.get_home_folder(), subfolder)):
                _paths.append(_path)
        _paths = set(_paths)
    else:
        _paths = set(app_context.fs.list(
            sites.abspath(app_context.get_home_folder(), subfolder)))

    if merge_local_files:
        local_fs = vfs.LocalReadOnlyFileSystem(logical_home_folder='/')
        _paths = _paths.union(set([
            os.path.join(appengine_config.BUNDLE_ROOT, path) for path in
            local_fs.list(subfolder[1:])]))

    result = []
    for abs_filename in _paths:
        filename = os.path.relpath(abs_filename, home)
        result.append(vfs.AbstractFileSystem.normpath(filename))
    return sorted(result)


def create_launch_button(url, active=True):
    if active:
        return safe_dom.A(
            href=url,
            className='icon row-hover material-icons',
            ).add_text('open_in_new')
    else:
        return safe_dom.Element('div', className='icon inactive')


def create_edit_button(edit_url, editable=True):
    if editable:
        return safe_dom.A(
            href=edit_url,
            className='icon md-mode-edit md row-hover',
            title='Edit',
            alt='Edit',
            )
    else:
        return safe_dom.Element('div', className='icon inactive')
