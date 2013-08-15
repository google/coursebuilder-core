# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Resources to be indexed and searched over by the search module."""

__author__ = 'Ellis Michael (emichael@google.com)'

import collections
from datetime import datetime
import HTMLParser
import logging
import os
import Queue
import robotparser
import urlparse

import appengine_config
from common import jinja_utils
import jinja2

from google.appengine.api import search
from google.appengine.api import urlfetch

PROTOCOL_PREFIX = 'http://'


class URLNotParseableException(Exception):
    """Exception thrown when the resource at a URL cannot be parsed."""
    pass


class ResourceHTMLParser(HTMLParser.HTMLParser):
    """Custom parser for processing HTML files."""

    IGNORED_TAGS = ['script', 'style']

    def __init__(self, url):
        HTMLParser.HTMLParser.__init__(self)
        self.content_list = []
        self._links = []
        self._title = ''
        self.tag_tracker = collections.Counter()
        self.url = url

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'a' and 'href' in attrs_dict:
            self._links.append(urlparse.urljoin(self.url, attrs_dict['href']))

        self.tag_tracker[tag] += 1

    def handle_endtag(self, tag):
        if self.tag_tracker[tag] > 0:
            self.tag_tracker[tag] -= 1

    def handle_data(self, data):
        """Invoked every time the parser encounters the page's inner content."""
        if self.tag_tracker['title']:
            if self._title:
                self._title += '\n%s' % data
            else:
                self._title = data
        stripped_data = data.strip()
        if (not any([self.tag_tracker[tag] for tag in self.IGNORED_TAGS]) and
            stripped_data):
            self.content_list.append(stripped_data)

    def get_content(self):
        return '\n'.join(self.content_list)

    def get_links(self):
        return self._links

    def get_title(self):
        return self._title


def get_parser_for_html(url):
    """Returns a ResourceHTMLParser with the parsed data."""

    parts = urlparse.urlparse(url)
    base = urlparse.urlunsplit((
        parts.scheme, parts.netloc, '', None, None))
    rp = robotparser.RobotFileParser(url=urlparse.urljoin(base, '/robots.txt'))
    rp.read()
    if not rp.can_fetch('*', url):
        raise URLNotParseableException

    parser = ResourceHTMLParser(url)
    try:
        result = urlfetch.fetch(url)
        if (result.status_code in [200, 304] and
            'text/html' in result.headers['Content-type']):
            parser.feed(unicode(result.content))
        else:
            raise ValueError
    except ValueError:
        raise URLNotParseableException('Could not parse file at URL: %s' % url)

    return parser


class Resource(object):
    """Abstract superclass for a resource."""

    @classmethod
    def get_all(cls, course):  # pylint: disable-msg=unused-argument
        """Return a list of objects of type cls in the course."""
        return []

    def get_document(self):
        """Return a search.Document to be indexed."""
        raise NotImplementedError

    def get_links(self):
        """External links to be indexed should be stored in self.links."""
        return self.links if hasattr(self, 'links') else []


class Result(object):
    """The abstract superclass for a result returned by the search module."""

    def get_html(self):
        """Return an HTML fragment to be used in the results page."""
        raise NotImplementedError

    @classmethod
    def _generate_html_from_template(cls, template_name, template_value):
        """Generates marked-up HTML from template."""
        template = jinja_utils.get_template(
            template_name,
            [os.path.join(appengine_config.BUNDLE_ROOT,
                          'modules', 'search', 'results_templates')])
        return jinja2.Markup(template.render(template_value))


class LessonResource(Resource):
    """A lesson in a course."""
    TYPE_NAME = 'Lesson'

    @classmethod
    def get_all(cls, course):
        return [LessonResource(lesson) for lesson in
                course.get_lessons_for_all_units()]

    def __init__(self, lesson):
        super(LessonResource, self).__init__()

        self.unit_id = lesson.unit_id
        self.lesson_id = lesson.lesson_id
        self.title = lesson.title
        self.objectives = lesson.objectives
        try:
            parser = get_parser_for_html(urlparse.urljoin(PROTOCOL_PREFIX,
                                                          lesson.notes))
            self.content = parser.get_content()
        except (URLNotParseableException, IOError):
            self.content = ''
        # TODO(emichael): set self.links and crawl external links
        self.links = []

    def get_document(self):
        return search.Document(
            doc_id=('unit?unit=%s&lesson=%s' % (self.unit_id, self.lesson_id)),
            fields=[
                search.TextField(name='title', value=self.title),
                search.TextField(name='content', value=self.content),
                search.HtmlField(name='objectives', value=self.objectives),
                search.TextField(name='type', value=self.TYPE_NAME),
                search.DateField(name='date', value=datetime.now().date())])


class LessonResult(Result):
    """An object for a lesson in search results."""

    def __init__(self, search_result):
        super(LessonResult, self).__init__()
        self.link = search_result.doc_id
        try:
            self.title = search_result['title'][0].value
        except (AttributeError, IndexError, KeyError):
            self.title = ''
        try:
            self.snippet = search_result.expressions[0].value
        except (AttributeError, IndexError):
            self.snippet = ''

    def get_html(self):
        template_value = {
            'result_title': self.title,
            'result_link': self.link,
            'result_snippet': jinja2.Markup(self.snippet)
        }
        return self._generate_html_from_template('basic.html', template_value)


class ExternalLinkResource(Resource):
    """An external link from a course."""
    TYPE_NAME = 'Link'

    def __init__(self, url):
        super(ExternalLinkResource, self).__init__()

        self.url = url

        parser = get_parser_for_html(url)
        self.content = parser.get_content()
        self.title = parser.get_title()
        # Do NOT record the links, otherwise we crawl the web

    def get_document(self):
        return search.Document(
            doc_id=self.url,
            fields=[
                search.TextField(name='title', value=self.title),
                search.TextField(name='content', value=self.content),
                search.TextField(name='type', value=self.TYPE_NAME),
                search.DateField(name='date', value=datetime.now().date())])


class ExternalLinkResult(Result):
    """An object for an external link in the search results."""

    def __init__(self, search_result):
        super(ExternalLinkResult, self).__init__()

        self.link = search_result.doc_id
        try:
            self.title = search_result['title'][0].value
        except (AttributeError, IndexError, KeyError):
            self.title = ''
        try:
            self.snippet = search_result.expressions[0].value
        except (AttributeError, IndexError):
            self.snippet = ''

    def get_html(self):
        template_value = {
            'result_title': self.title,
            'result_link': self.link,
            'result_snippet': jinja2.Markup(self.snippet)
        }
        return self._generate_html_from_template('basic.html', template_value)


# Register new resource types here
RESOURCE_TYPES = [
    (LessonResource, LessonResult),
    (ExternalLinkResource, ExternalLinkResult)
]


def get_all_documents(course):
    """Return a list of docs for a given course."""
    resource_queue = Queue.LifoQueue()

    for (resource_type, unused_result_type) in RESOURCE_TYPES:
        for resource in resource_type.get_all(course):
            resource_queue.put(resource)

    # Build docs and get linked pages
    docs = []
    while not resource_queue.empty():
        item = resource_queue.get()
        docs.append(item.get_document())

        for link in item.get_links():
            try:
                # TODO(emichael): Ensure the same link isn't crawled twice
                resource_queue.put(ExternalLinkResource(link))
            except URLNotParseableException:
                pass

    return docs


def process_results(results):
    """Generate result objects for the results of a query."""
    result_types = {resource_type.TYPE_NAME: result_type
                    for (resource_type, result_type) in RESOURCE_TYPES}

    processed_results = []
    for result in results:
        try:
            result_type = result_types[result['type'][0].value]
            processed_results.append(result_type(result))
        except (AttributeError, IndexError, KeyError) as e:
            # If there is no type information, we cannot process the result
            logging.error("%s. Couldn't process result", e)

    return processed_results
