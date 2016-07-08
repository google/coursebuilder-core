# Copyright 2016 Google Inc. All Rights Reserved.
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

"""Generate flattened import files for Polymer projects."""

__author__ = 'Nick Retallack (nretallack@google.com)'

import os
import urlparse

import bs4

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
STATIC_IMPORT_ROOT = os.path.join(ROOT, 'lib/_static/html-imports')

# URL => path
URL_ROOTS = {
    '/static/': os.path.join(ROOT, 'lib/_static/'),
    '/modules/explorer/_static/': (
        os.path.join(ROOT, 'modules/explorer/_static/')),
    '/modules/guide/_static/': (
        os.path.join(ROOT, 'modules/guide/_static/')),
}

# Entry point URL => Resulting file path
JOBS = {
    '/modules/explorer/_static/components/course-explorer/course-explorer.html':
        os.path.join(STATIC_IMPORT_ROOT, 'explorer-imports.html'),
    '/modules/guide/_static/guide/guide-app/guide-app.html':
        os.path.join(STATIC_IMPORT_ROOT, 'guide-imports.html'),
}


def get_imports_from_html(html):
    return set(link.get('href') for link in
        bs4.BeautifulSoup(html, 'html.parser').find_all('link', rel='import'))


def make_link_tag(url):
    return """<link rel="import" href="{url}">""".format(url=url)


def get_imports_from_file(path):
    with open(path) as the_file:
        return get_imports_from_html(the_file.read())


def map_url_to_file(url):
    for url_root, path in URL_ROOTS.iteritems():
        if url.startswith(url_root):
            return url.replace(url_root, path)


def get_imports_from_url(url):
    return set(urlparse.urljoin(url, new_url)
        for new_url in get_imports_from_file(map_url_to_file(url)))


def recursive_get_imports_from_url(url):
    queue = set([url])
    processed = set()
    while queue:
        url = queue.pop()
        if url not in processed:
            queue |= get_imports_from_url(url)
        processed.add(url)
    return processed


def flatten_imports(url):
    return '\n'.join(sorted(
        make_link_tag(import_url) for import_url in
        recursive_get_imports_from_url(url)))


def write_flattened_imports(url, path):
    dirname = os.path.dirname(path)
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    with open(path, 'w') as write_file:
        write_file.write(flatten_imports(url))


def do_all_jobs():
    for url, path in JOBS.iteritems():
        write_flattened_imports(url, path)


if __name__ == '__main__':
    do_all_jobs()
