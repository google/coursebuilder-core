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
import re
import robotparser
import urllib
import urlparse
from xml.dom import minidom
from xml.parsers.expat import ExpatError

import appengine_config
from common import jinja_utils
import jinja2
from modules.announcements import announcements

from google.appengine.api import search
from google.appengine.api import urlfetch

PROTOCOL_PREFIX = 'http://'

YOUTUBE_DATA_URL = 'http://gdata.youtube.com/feeds/api/videos/'
YOUTUBE_TIMED_TEXT_URL = 'http://youtube.com/api/timedtext'

# The limit (in seconds) for the time that elapses before a new transcript
# fragment should be started. A lower value results in more fine-grain indexing
# and more docs in the index.
YOUTUBE_CAPTION_SIZE_SECS = 30


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


def get_parser_for_html(url, ignore_robots=False):
    """Returns a ResourceHTMLParser with the parsed data."""

    if not (ignore_robots or _url_allows_robots(url)):
        raise URLNotParseableException

    parser = ResourceHTMLParser(url)
    try:
        result = urlfetch.fetch(url)
        if (result.status_code in [200, 304] and
            any(content_type in result.headers['Content-type'] for
                content_type in ['text/html', 'xml'])):
            # TODO(emichael): Stop dropping non-ascii characters and fix the
            # failing tests
            parser.feed(
                result.content.decode('utf-8').encode('ascii', 'ignore'))
        else:
            raise ValueError
    except ValueError:
        raise URLNotParseableException('Could not parse file at URL: %s' % url)

    return parser


def get_minidom_from_xml(url, ignore_robots=False):
    """Returns a minidom representation of an XML file at url."""

    if not (ignore_robots or _url_allows_robots(url)):
        raise URLNotParseableException

    result = urlfetch.fetch(url)
    if result.status_code not in [200, 304]:
        raise URLNotParseableException('Could not parse file at URL: %s' % url)

    try:
        # TODO(emichael): Stop dropping non-ascii characters and fix the
        # failing tests
        xmldoc = minidom.parseString(result.content.decode('utf-8').encode(
            'ascii', 'ignore'))
    except ExpatError as e:
        logging.error('Error parsing XML document: %s', e)
        raise URLNotParseableException('Could not parse file at URL: %s' % url)

    return xmldoc


def _url_allows_robots(url):
    """Checks robots.txt for user agent * at URL."""
    parts = urlparse.urlparse(url)
    base = urlparse.urlunsplit((
        parts.scheme, parts.netloc, '', None, None))
    rp = robotparser.RobotFileParser(url=urlparse.urljoin(
        base, '/robots.txt'))
    rp.read()
    return rp.can_fetch('*', url)


class Resource(object):
    """Abstract superclass for a resource."""

    # Each subclass should define this constant
    TYPE_NAME = 'Resource'

    # Each subclass should use this constant to define the fields it needs
    # returned with a search result.
    RETURNED_FIELDS = []

    # Each subclass should use this constant to define the fields it needs
    # returned as snippets in the search result. In most cases, this should be
    # one field.
    SNIPPETED_FIELDS = []

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

    @classmethod
    def _get_returned_field(cls, result, field):
        """Returns the value of a field in result, '' if none exists."""
        try:
            return result[field][0].value
        except (KeyError, IndexError, AttributeError):
            return ''

    @classmethod
    def _get_snippet(cls, result):
        """Returns the value of the snippet in result, '' if none exists."""
        try:
            return result.expressions[0].value
        except (AttributeError, IndexError):
            return ''


class LessonResource(Resource):
    """A lesson in a course."""
    TYPE_NAME = 'Lesson'
    RETURNED_FIELDS = ['title', 'unit_id', 'lesson_id', 'url']
    SNIPPETED_FIELDS = ['content']

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
        if lesson.notes:
            try:
                parser = get_parser_for_html(urlparse.urljoin(PROTOCOL_PREFIX,
                                                              lesson.notes))
                self.content = parser.get_content()
            except (URLNotParseableException, IOError):
                self.content = ''
        else:
            self.content = ''
        # TODO(emichael): set self.links and crawl external links
        self.links = []

    def get_document(self):
        return search.Document(
            doc_id=('%s_%s_%s' % (self.TYPE_NAME,
                                  self.unit_id, self.lesson_id)),
            fields=[
                search.TextField(name='title', value=self.title),
                search.TextField(name='content', value=self.content),
                search.HtmlField(name='objectives', value=self.objectives),
                search.TextField(name='unit_id', value=unicode(self.unit_id)),
                search.TextField(name='lesson_id',
                                 value=unicode(self.lesson_id)),
                search.TextField(name='url', value=(
                    'unit?unit_id=%s&lesson=%s' %
                    (self.unit_id, self.lesson_id))),
                search.TextField(name='type', value=self.TYPE_NAME),
                search.DateField(name='date', value=datetime.now().date())])


class LessonResult(Result):
    """An object for a lesson in search results."""

    def __init__(self, search_result):
        super(LessonResult, self).__init__()
        self.url = self._get_returned_field(search_result, 'url')
        self.title = self._get_returned_field(search_result, 'title')
        self.unit_id = self._get_returned_field(search_result, 'unit_id')
        self.lesson_id = self._get_returned_field(search_result, 'lesson_id')
        self.snippet = self._get_snippet(search_result)

    def get_html(self):
        template_value = {
            'result_title': '%s - Lesson %s.%s' % (self.title, self.unit_id,
                                                   self.lesson_id),
            'result_url': self.url,
            'result_snippet': jinja2.Markup(self.snippet)
        }
        return self._generate_html_from_template('basic.html', template_value)


class ExternalLinkResource(Resource):
    """An external link from a course."""
    TYPE_NAME = 'External Link'
    RETURNED_FIELDS = ['title', 'url']
    SNIPPETED_FIELDS = ['content']

    def __init__(self, url):
        super(ExternalLinkResource, self).__init__()

        self.url = url

        parser = get_parser_for_html(url)
        self.content = parser.get_content()
        self.title = parser.get_title()
        # Do NOT record the links, otherwise we crawl the web

    def get_document(self):
        return search.Document(
            doc_id=('%s_%s' % (self.TYPE_NAME, self.url)),
            fields=[
                search.TextField(name='title', value=self.title),
                search.TextField(name='content', value=self.content),
                search.TextField(name='url', value=self.url),
                search.TextField(name='type', value=self.TYPE_NAME),
                search.DateField(name='date', value=datetime.now().date())])


class ExternalLinkResult(Result):
    """An object for an external link in the search results."""

    def __init__(self, search_result):
        super(ExternalLinkResult, self).__init__()

        self.url = self._get_returned_field(search_result, 'url')
        self.title = self._get_returned_field(search_result, 'title')
        self.snippet = self._get_snippet(search_result)

    def get_html(self):
        template_value = {
            'result_title': self.title,
            'result_url': self.url,
            'result_snippet': jinja2.Markup(self.snippet)
        }
        return self._generate_html_from_template('basic.html', template_value)


class YouTubeFragmentResource(Resource):
    """An object for a YouTube transcript fragment in search results."""
    TYPE_NAME = 'YouTube'
    RETURNED_FIELDS = ['title', 'video_id', 'start', 'thumbnail_url']
    SNIPPETED_FIELDS = ['content']

    @classmethod
    def get_all(cls, course):
        """Get all of the transcript fragment docs for a course."""
        # TODO(emichael): When announcements are implemented, grab the videos
        # in custom tags there.
        fragments = []
        for lesson in course.get_lessons_for_all_units():
            if lesson.video:
                fragments += cls._get_fragments_for_video(
                    lesson.video, lesson.lesson_id, lesson.unit_id)
            match = re.search(
                r"""<[ ]*gcb-youtube[^>]+videoid=['"]([^'"]+)['"]""",
                lesson.objectives)
            if match:
                for video_id in match.groups():
                    fragments += cls._get_fragments_for_video(
                        video_id, lesson.lesson_id, lesson.unit_id)
        return fragments

    @classmethod
    def _get_fragments_for_video(cls, video_id, lesson_id, unit_id):
        """Get all of the transcript fragment docs for a specific video."""
        try:
            (transcript, title, thumbnail_url) = cls._get_video_data(video_id)
        except URLNotParseableException:
            return []

        # Aggregate the fragments into YOUTUBE_CAPTION_SIZE_SECS time chunks
        fragments = transcript.getElementsByTagName('text')
        aggregated_fragments = []
        # This parser is only used for unescaping HTML entities
        parser = HTMLParser.HTMLParser()
        while fragments:
            current_start = float(fragments[0].attributes['start'].value)
            current_text = []

            while (fragments and
                   float(fragments[0].attributes['start'].value) -
                   current_start < YOUTUBE_CAPTION_SIZE_SECS):
                current_text.append(parser.unescape(
                    fragments.pop(0).firstChild.nodeValue))

            aggregated_fragment = YouTubeFragmentResource(
                video_id, lesson_id, unit_id, current_start,
                '\n'.join(current_text), title, thumbnail_url)
            aggregated_fragments.append(aggregated_fragment)

        return aggregated_fragments

    @classmethod
    def _get_video_data(cls, video_id):
        """Returns (track_minidom, title, thumbnail_url) for a video."""

        try:
            vid_info = get_minidom_from_xml(
                urlparse.urljoin(YOUTUBE_DATA_URL, video_id),
                ignore_robots=True)
            title = vid_info.getElementsByTagName(
                'title')[0].firstChild.nodeValue
            thumbnail_url = vid_info.getElementsByTagName(
                'media:thumbnail')[0].attributes['url'].value
        except (URLNotParseableException, IOError, IndexError, AttributeError):
            title = ''
            thumbnail_url = ''

        # TODO(emichael): Handle the existence of multiple tracks
        url = urlparse.urljoin(YOUTUBE_TIMED_TEXT_URL,
                               '?v=%s&type=list' % video_id)
        tracklist = get_minidom_from_xml(url, ignore_robots=True)
        tracks = tracklist.getElementsByTagName('track')
        if not tracks:
            raise URLNotParseableException
        track_name = tracks[0].attributes['name'].value
        track_lang = tracks[0].attributes['lang_code'].value
        track_id = tracks[0].attributes['id'].value

        url = urlparse.urljoin(YOUTUBE_TIMED_TEXT_URL, urllib.quote(
            '?v=%s&lang=%s&name=%s&id=%s' %
            (video_id, track_lang, track_name, track_id), '?/=&'))
        transcript = get_minidom_from_xml(url, ignore_robots=True)

        return (transcript, title, thumbnail_url)

    def __init__(self, video_id, lesson_id, unit_id, start, text, video_title,
                 thumbnail_url):
        super(YouTubeFragmentResource, self).__init__()

        self.unit_id = unit_id
        self.lesson_id = lesson_id
        self.video_id = video_id
        self.start = start
        self.text = text
        self.video_title = video_title
        self.thumbnail_url = thumbnail_url

    def get_document(self):
        return search.Document(
            doc_id=('%s_%s_%s_%s_%s' % (self.TYPE_NAME,
                                        self.unit_id, self.lesson_id,
                                        self.video_id, self.start)),
            fields=[
                search.TextField(name='title', value=self.video_title),
                search.TextField(name='video_id', value=self.video_id),
                search.TextField(name='content', value=self.text),
                search.NumberField(name='start', value=self.start),
                search.TextField(name='thumbnail_url',
                                 value=self.thumbnail_url),
                search.TextField(name='url', value=(
                    'unit?unit_id=%s&lesson=%s' %
                    (self.unit_id, self.lesson_id))),
                search.TextField(name='type', value=self.TYPE_NAME),
                search.DateField(name='date', value=datetime.now().date())])


class YouTubeFragmentResult(Result):
    """An object for a lesson in search results."""

    def __init__(self, search_result):
        super(YouTubeFragmentResult, self).__init__()
        self.doc_id = search_result.doc_id
        self.title = self._get_returned_field(search_result, 'title')
        self.video_id = self._get_returned_field(search_result, 'video_id')
        self.start = self._get_returned_field(search_result, 'start')
        self.thumbnail_url = self._get_returned_field(search_result,
                                                      'thumbnail_url')
        self.url = self._get_returned_field(search_result, 'url')
        self.snippet = self._get_snippet(search_result)

    def get_html(self):
        template_value = {
            'result_title': self.title,
            'result_url': self.url,
            'video_id': self.video_id,
            'start_time': self.start,
            'thumbnail_url': self.thumbnail_url,
            'result_snippet': jinja2.Markup(self.snippet)
        }
        return self._generate_html_from_template('youtube.html', template_value)


class AnnouncementResource(Resource):
    """An announcement in a course."""
    TYPE_NAME = 'Announcement'
    RETURNED_FIELDS = ['title', 'url']
    SNIPPETED_FIELDS = ['content']

    @classmethod
    def get_all(cls, course):
        resources = []
        if announcements.custom_module.enabled:
            for entity in announcements.AnnouncementEntity.get_announcements():
                if not entity.is_draft:
                    resources.append(AnnouncementResource(entity))
        return resources

    def __init__(self, announcement):
        super(AnnouncementResource, self).__init__()

        self.title = announcement.title
        self.key = announcement.key()
        parser = ResourceHTMLParser(PROTOCOL_PREFIX)
        parser.feed(announcement.html)
        self.content = parser.get_content()

    def get_document(self):
        return search.Document(
            doc_id=('%s_%s' % (self.TYPE_NAME, self.key)),
            fields=[
                search.TextField(name='title',
                                 value='%s - Announcement' % self.title),
                search.TextField(name='content', value=self.content),
                search.TextField(name='url',
                                 value='announcements#%s' % self.key),
                search.TextField(name='type', value=self.TYPE_NAME),
                search.DateField(name='date', value=datetime.now().date())])


class AnnouncementResult(Result):
    """An object for an announcement in search results."""

    def __init__(self, search_result):
        super(AnnouncementResult, self).__init__()
        self.url = self._get_returned_field(search_result, 'url')
        self.title = self._get_returned_field(search_result, 'title')
        self.snippet = self._get_snippet(search_result)

    def get_html(self):
        template_value = {
            'result_title': self.title,
            'result_url': self.url,
            'result_snippet': jinja2.Markup(self.snippet)
        }
        return self._generate_html_from_template('basic.html', template_value)


# Register new resource types here
RESOURCE_TYPES = [
    (LessonResource, LessonResult),
    (ExternalLinkResource, ExternalLinkResult),
    (YouTubeFragmentResource, YouTubeFragmentResult),
    (AnnouncementResource, AnnouncementResult)
]


def get_returned_fields():
    """Returns a list of fields that should be returned in a search result."""
    returned_fields = set(['type'])
    for (resource_type, unused_result_type) in RESOURCE_TYPES:
        returned_fields |= set(resource_type.RETURNED_FIELDS)
    return list(returned_fields)


def get_snippeted_fields():
    """Returns a list of fields that should be snippeted in a search result."""
    snippeted_fields = set()
    for (resource_type, unused_result_type) in RESOURCE_TYPES:
        snippeted_fields |= set(resource_type.SNIPPETED_FIELDS)
    return list(snippeted_fields)


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
