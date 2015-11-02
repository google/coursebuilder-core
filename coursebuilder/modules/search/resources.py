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
import datetime
import gettext
import HTMLParser
import logging
import operator
import os
import Queue
import re
import robotparser
import urllib
import urlparse
from xml.dom import minidom

import jinja2

import appengine_config
from common import jinja_utils
from models import models
from modules.announcements import announcements

from google.appengine.api import search
from google.appengine.api import urlfetch

PROTOCOL_PREFIX = 'http://'

YOUTUBE_DATA_URL = 'https://gdata.youtube.com/feeds/api/videos/'
YOUTUBE_TIMED_TEXT_URL = 'https://youtube.com/api/timedtext'

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
        raise URLNotParseableException('robots.txt disallows access to URL: %s'
                                       % url)

    parser = ResourceHTMLParser(url)
    try:
        result = urlfetch.fetch(url)
        if (result.status_code in [200, 304] and
            any(content_type in result.headers['Content-type'] for
                content_type in ['text/html', 'xml'])):
            if not isinstance(result.content, unicode):
                result.content = result.content.decode('utf-8')
            parser.feed(result.content)
        else:
            raise ValueError
    except BaseException as e:
        raise URLNotParseableException('Could not parse file at URL: %s\n%s' %
                                       (url, e))

    return parser


def get_minidom_from_xml(url, ignore_robots=False):
    """Returns a minidom representation of an XML file at url."""

    if not (ignore_robots or _url_allows_robots(url)):
        raise URLNotParseableException('robots.txt disallows access to URL: %s'
                                       % url)

    try:
        result = urlfetch.fetch(url)
    except urlfetch.Error as e:
        raise URLNotParseableException('Could not parse file at URL: %s. %s' %
                                       (url, e))
    if result.status_code not in [200, 304]:
        raise URLNotParseableException('Bad status code (%s) for URL: %s' %
                                       (result.status_code, url))

    try:
        if isinstance(result.content, unicode):
            result.content = result.content.encode('utf-8')
        xmldoc = minidom.parseString(result.content)
    except BaseException as e:
        raise URLNotParseableException(
            'Error parsing XML document at URL: %s. %s' % (url, e))

    return xmldoc


def _url_allows_robots(url):
    """Checks robots.txt for user agent * at URL."""
    url = url.encode('utf-8')
    try:
        parts = urlparse.urlparse(url)
        base = urlparse.urlunsplit((
            parts.scheme, parts.netloc, '', None, None))
        rp = robotparser.RobotFileParser(url=urlparse.urljoin(
            base, '/robots.txt'))
        rp.read()
    except BaseException as e:
        logging.info('Could not retreive robots.txt for URL: %s', url)
        raise URLNotParseableException(e)
    else:
        return rp.can_fetch('*', url)


def get_locale_filtered_announcement_list(course):
    # TODO(jorr): Restrict search in announcements by all tracking labels,
    # not just locale.
    announcement_list = (
        announcements.AnnouncementEntity.get_announcements())
    # pylint: disable=protected-access
    return models.LabelDAO._apply_locale_labels_to_locale(
        course.app_context.get_current_locale(), announcement_list)
    # pylint: enable=protected-access


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

    # Each subclass should use this constant to define how many days should
    # elapse before a resource should be re-indexed. This value should be
    # nonnegative.
    FRESHNESS_THRESHOLD_DAYS = 0

    @classmethod
    def generate_all(
        cls, course, timestamps):  # pylint: disable=unused-argument
        """A generator returning objects of type cls in the course.

        This generator should yield resources based on the last indexed time in
        timestamps.

        Args:
            course: models.courses.course. the course to index.
            timestamps: dict from doc_ids to last indexed datetimes.
        Yields:
            A sequence of Resource objects.
        """

        # For the superclass, return a generator which immediately halts. All
        # implementations in subclasses must also be generators for memory-
        # management reasons.
        return
        yield  # pylint: disable=unreachable

    @classmethod
    def _get_doc_id(cls, *unused_vargs):
        """Subclasses should implement this with identifying fields as args."""
        raise NotImplementedError

    @classmethod
    def _indexed_within_num_days(cls, timestamps, doc_id, num_days):
        """Determines whether doc_id was indexed in the last num_days days."""
        try:
            timestamp = timestamps[doc_id]
        except (KeyError, TypeError):
            return False
        else:
            delta = datetime.datetime.utcnow() - timestamp
            return delta <= datetime.timedelta(num_days)

    def get_document(self):
        """Return a search.Document to be indexed."""
        raise NotImplementedError

    def get_links(self):
        """External links to be indexed should be stored in self.links."""
        return self.links if hasattr(self, 'links') else []

    def get_unit_id(self):
        return self.unit_id if hasattr(self, 'unit_id') else None


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
    FRESHNESS_THRESHOLD_DAYS = 3

    @classmethod
    def generate_all(cls, course, timestamps):
        for lesson in course.get_lessons_for_all_units():
            unit = course.find_unit_by_id(lesson.unit_id)
            doc_id = cls._get_doc_id(lesson.unit_id, lesson.lesson_id)
            if (course.is_unit_available(unit) and
                course.is_lesson_available(unit, lesson) and
                not cls._indexed_within_num_days(timestamps, doc_id,
                                                 cls.FRESHNESS_THRESHOLD_DAYS)):
                try:
                    yield LessonResource(lesson)
                except HTMLParser.HTMLParseError as e:
                    logging.info(
                        'Error parsing objectives for Lesson %s.%s: %s',
                        lesson.unit_id, lesson.lesson_id, e)
                    continue

    @classmethod
    def _get_doc_id(cls, unit_id, lesson_id):
        return '%s_%s_%s' % (cls.TYPE_NAME, unit_id, lesson_id)

    def __init__(self, lesson):
        super(LessonResource, self).__init__()

        self.unit_id = lesson.unit_id
        self.lesson_id = lesson.lesson_id
        self.title = unicode(lesson.title)
        if lesson.notes:
            self.notes = urlparse.urljoin(
                PROTOCOL_PREFIX, unicode(lesson.notes))
        else:
            self.notes = ''
        if lesson.objectives:
            parser = ResourceHTMLParser(PROTOCOL_PREFIX)
            parser.feed(unicode(lesson.objectives))
            self.content = parser.get_content()
            self.links = parser.get_links()
        else:
            self.content = ''

    def get_document(self):
        return search.Document(
            doc_id=self._get_doc_id(self.unit_id, self.lesson_id),
            fields=[
                search.TextField(
                    name='unit_id',
                    value=str(self.unit_id) if self.unit_id else ''),
                search.TextField(name='title', value=self.title),
                search.TextField(name='content', value=self.content),
                search.TextField(name='url', value=(
                    'unit?unit=%s&lesson=%s' %
                    (self.unit_id, self.lesson_id))),
                search.TextField(name='type', value=self.TYPE_NAME),
                search.DateField(name='date',
                                 value=datetime.datetime.utcnow())])


class LessonResult(Result):
    """An object for a lesson in search results."""

    def __init__(self, search_result):
        super(LessonResult, self).__init__()
        self.url = self._get_returned_field(search_result, 'url')
        self.title = self._get_returned_field(search_result, 'title')
        self.unit_id = self._get_returned_field(search_result, 'unit_id')
        self.snippet = self._get_snippet(search_result)

    def get_html(self):
        # I18N: Displayed in search results; denotes a lesson link.
        lesson_string = gettext.gettext('Lesson')
        template_value = {
            'result_title': '%s - %s' % (self.title, lesson_string),
            'result_url': self.url,
            'result_snippet': jinja2.Markup(self.snippet)
        }
        return self._generate_html_from_template('basic.html', template_value)


class ExternalLinkResource(Resource):
    """An external link from a course."""
    TYPE_NAME = 'ExternalLink'
    RETURNED_FIELDS = ['title', 'url']
    SNIPPETED_FIELDS = ['content']
    FRESHNESS_THRESHOLD_DAYS = 15

    # TODO(emichael): Allow the user to turn off external links in the dashboard

    @classmethod
    def generate_all_from_dist_dict(cls, link_dist, link_unit_id, timestamps):
        """Generate all external links from a map from URL to distance.

        Args:
            link_dist: dict. a map from URL to distance in the link graph from
                the course.
            link_unit_id: dict.  A map from URL to the unit ID under which
                the link is found.
            timestamps: dict from doc_ids to last indexed datetimes. An empty
                dict indicates that all documents should be generated.
        Yields:
            A sequence of ExternalLinkResource.
        """

        url_queue = Queue.LifoQueue()
        for url, dist in sorted(link_dist.iteritems(),
                                key=operator.itemgetter(1)):
            url_queue.put(url)

        while not url_queue.empty():
            url = url_queue.get()
            doc_id = cls._get_doc_id(url)

            if (cls._indexed_within_num_days(timestamps, doc_id,
                                             cls.FRESHNESS_THRESHOLD_DAYS)):
                continue

            dist = link_dist[url]
            unit_id = link_unit_id.get(url)
            if dist > 1:
                break

            try:
                resource = ExternalLinkResource(url, unit_id)
            except URLNotParseableException as e:
                logging.info(e)
            else:
                if dist < 1:
                    for new_link in resource.get_links():
                        if new_link not in link_dist:
                            link_dist[new_link] = dist + 1
                            url_queue.put(new_link)
                            link_unit_id[new_link] = unit_id
                yield resource

    def __init__(self, url, unit_id):
        # distance is the distance from the course material in the link graph,
        # where a lesson notes page has a distance of 0
        super(ExternalLinkResource, self).__init__()

        self.url = url
        self.unit_id = unit_id
        parser = get_parser_for_html(url)
        self.content = parser.get_content()
        self.title = parser.get_title()
        self.links = parser.get_links()

    @classmethod
    def _get_doc_id(cls, url):
        return '%s_%s' % (cls.TYPE_NAME, url)

    def get_document(self):
        return search.Document(
            doc_id=self._get_doc_id(self.url),
            fields=[
                search.TextField(name='title', value=self.title),
                search.TextField(name='content', value=self.content),
                search.TextField(name='url', value=self.url),
                search.TextField(
                    name='unit_id',
                    value=str(self.unit_id) if self.unit_id else ''),
                search.TextField(name='type', value=self.TYPE_NAME),
                search.DateField(name='date',
                                 value=datetime.datetime.utcnow())])


class ExternalLinkResult(Result):
    """An object for an external link in the search results."""

    def __init__(self, search_result):
        super(ExternalLinkResult, self).__init__()

        self.url = self._get_returned_field(search_result, 'url')
        self.title = self._get_returned_field(search_result, 'title')
        self.unit_id = self._get_returned_field(search_result, 'unit_id')
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
    TYPE_NAME = 'YouTubeFragment'
    RETURNED_FIELDS = ['title', 'video_id', 'start', 'thumbnail_url']
    SNIPPETED_FIELDS = ['content']
    FRESHNESS_THRESHOLD_DAYS = 30

    @classmethod
    def generate_all(cls, course, timestamps):
        """Generate all YouTubeFragments for a course."""
        # TODO(emichael): Handle the existence of a single video in multiple
        # places in a course.

        youtube_ct_regex = r"""<[ ]*gcb-youtube[^>]+videoid=['"]([^'"]+)['"]"""

        for lesson in course.get_lessons_for_all_units():
            unit = course.find_unit_by_id(lesson.unit_id)
            if not (course.is_unit_available(unit) and
                    course.is_lesson_available(unit, lesson)):
                continue
            lesson_url = 'unit?unit=%s&lesson=%s' % (
                lesson.unit_id, lesson.lesson_id)

            if lesson.video and not cls._indexed_within_num_days(
                    timestamps, lesson.video, cls.FRESHNESS_THRESHOLD_DAYS):
                for fragment in cls._get_fragments_for_video(
                    lesson.unit_id, lesson.video, lesson_url):
                    yield fragment

            match = re.search(youtube_ct_regex, unicode(lesson.objectives))
            if match:
                for video_id in match.groups():
                    if not cls._indexed_within_num_days(
                            timestamps, video_id, cls.FRESHNESS_THRESHOLD_DAYS):
                        for fragment in cls._get_fragments_for_video(
                            lesson.unit_id, video_id, lesson_url):
                            yield fragment

        if announcements.custom_module.enabled:
            for entity in get_locale_filtered_announcement_list(course):
                if entity.is_draft:
                    continue
                announcement_url = 'announcements#%s' % entity.key()
                match = re.search(youtube_ct_regex, entity.html)
                if match:
                    for video_id in match.groups():
                        if not cls._indexed_within_num_days(
                                timestamps, video_id,
                                cls.FRESHNESS_THRESHOLD_DAYS):
                            for fragment in cls._get_fragments_for_video(
                                None, video_id, announcement_url):
                                yield fragment

    @classmethod
    def _indexed_within_num_days(cls, timestamps, video_id, num_days):
        for doc_id in timestamps:
            if doc_id.startswith(cls._get_doc_id(video_id, '')):
                return super(
                    YouTubeFragmentResource, cls)._indexed_within_num_days(
                        timestamps, doc_id, num_days)
        return False

    @classmethod
    def _get_fragments_for_video(cls, unit_id, video_id, url_in_course):
        """Get all of the transcript fragment docs for a specific video."""
        try:
            (transcript, title, thumbnail_url) = cls._get_video_data(video_id)
        except BaseException as e:
            logging.info('Could not parse YouTube video with id %s.\n%s',
                         video_id, e)
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
                video_id, unit_id, url_in_course, current_start,
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
        except (URLNotParseableException, IOError,
                IndexError, AttributeError) as e:
            logging.error('Could not parse video info for video id %s.\n%s',
                          video_id, e)
            title = ''
            thumbnail_url = ''

        # TODO(emichael): Handle the existence of multiple tracks
        url = urlparse.urljoin(YOUTUBE_TIMED_TEXT_URL,
                               '?v=%s&type=list' % video_id)
        tracklist = get_minidom_from_xml(url, ignore_robots=True)
        tracks = tracklist.getElementsByTagName('track')
        if not tracks:
            raise URLNotParseableException('No tracks for video %s' % video_id)
        track_name = tracks[0].attributes['name'].value
        track_lang = tracks[0].attributes['lang_code'].value
        track_id = tracks[0].attributes['id'].value

        url = urlparse.urljoin(YOUTUBE_TIMED_TEXT_URL, urllib.quote(
            '?v=%s&lang=%s&name=%s&id=%s' %
            (video_id, track_lang, track_name, track_id), '?/=&'))
        transcript = get_minidom_from_xml(url, ignore_robots=True)

        return (transcript, title, thumbnail_url)

    @classmethod
    def _get_doc_id(cls, video_id, start_time):
        return '%s_%s_%s' % (cls.TYPE_NAME, video_id, start_time)

    def __init__(self, video_id, unit_id, url, start, text, video_title,
                 thumbnail_url):
        super(YouTubeFragmentResource, self).__init__()

        self.url = url
        self.video_id = video_id
        self.unit_id = unit_id
        self.start = start
        self.text = text
        self.video_title = video_title
        self.thumbnail_url = thumbnail_url

    def get_document(self):
        return search.Document(
            doc_id=self._get_doc_id(self.video_id, self.start),
            fields=[
                search.TextField(name='title', value=self.video_title),
                search.TextField(name='video_id', value=self.video_id),
                search.TextField(
                    name='unit_id',
                    value=str(self.unit_id) if self.unit_id else ''),
                search.TextField(name='content', value=self.text),
                search.NumberField(name='start', value=self.start),
                search.TextField(name='thumbnail_url',
                                 value=self.thumbnail_url),
                search.TextField(name='url', value=self.url),
                search.TextField(name='type', value=self.TYPE_NAME),
                search.DateField(name='date',
                                 value=datetime.datetime.utcnow())])


class YouTubeFragmentResult(Result):
    """An object for a lesson in search results."""

    def __init__(self, search_result):
        super(YouTubeFragmentResult, self).__init__()
        self.doc_id = search_result.doc_id
        self.title = self._get_returned_field(search_result, 'title')
        self.video_id = self._get_returned_field(search_result, 'video_id')
        self.unit_id = self._get_returned_field(search_result, 'unit_id')
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
    FRESHNESS_THRESHOLD_DAYS = 1

    @classmethod
    def generate_all(cls, course, timestamps):
        if announcements.custom_module.enabled:
            for entity in get_locale_filtered_announcement_list(course):
                doc_id = cls._get_doc_id(entity.key())
                if not(entity.is_draft or cls._indexed_within_num_days(
                        timestamps, doc_id, cls.FRESHNESS_THRESHOLD_DAYS)):
                    try:
                        yield AnnouncementResource(entity)
                    except HTMLParser.HTMLParseError as e:
                        logging.info('Error parsing Announcement %s: %s',
                                     entity.title, e)
                        continue

    def __init__(self, announcement):
        super(AnnouncementResource, self).__init__()

        self.title = announcement.title
        self.key = announcement.key()
        parser = ResourceHTMLParser(PROTOCOL_PREFIX)
        parser.feed(announcement.html)
        self.content = parser.get_content()

    @classmethod
    def _get_doc_id(cls, key):
        return '%s_%s' % (cls.TYPE_NAME, key)

    def get_document(self):
        return search.Document(
            doc_id=self._get_doc_id(self.key),
            fields=[
                search.TextField(name='title', value=self.title),
                search.TextField(name='content', value=self.content),
                search.TextField(name='url',
                                 value='announcements#%s' % self.key),
                search.TextField(name='type', value=self.TYPE_NAME),
                search.DateField(name='date',
                                 value=datetime.datetime.utcnow())])


class AnnouncementResult(Result):
    """An object for an announcement in search results."""

    def __init__(self, search_result):
        super(AnnouncementResult, self).__init__()
        self.url = self._get_returned_field(search_result, 'url')
        self.title = self._get_returned_field(search_result, 'title')
        self.unit_id = None  # Announcements are definitionally not in units.
        self.snippet = self._get_snippet(search_result)

    def get_html(self):
        # I18N: Displayed in search results; denotes an announcement link.
        announcement_string = gettext.gettext('Announcement')
        template_value = {
            'result_title': '%s - %s' % (self.title, announcement_string),
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
    for resource_type, unused_result_type in RESOURCE_TYPES:
        returned_fields |= set(resource_type.RETURNED_FIELDS)
    return list(returned_fields)


def get_snippeted_fields():
    """Returns a list of fields that should be snippeted in a search result."""
    snippeted_fields = set()
    for resource_type, unused_result_type in RESOURCE_TYPES:
        snippeted_fields |= set(resource_type.SNIPPETED_FIELDS)
    return list(snippeted_fields)


def generate_all_documents(course, timestamps):
    """A generator for all docs for a given course.

    Args:
        course: models.courses.Course. the course to be indexed.
        timestamps: dict from doc_ids to last indexed datetimes. An empty dict
            indicates that all documents should be generated.
    Yields:
        A sequence of search.Document. If a document is within the freshness
        threshold, no document will be generated. This function does not modify
        timestamps.
    """

    link_dist = {}
    link_unit_id = {}

    for resource_type, unused_result_type in RESOURCE_TYPES:
        for resource in resource_type.generate_all(course, timestamps):
            unit_id = resource.get_unit_id()
            if isinstance(resource, LessonResource) and resource.notes:
                link_dist[resource.notes] = 0
                link_unit_id[resource.notes] = unit_id
            for link in resource.get_links():
                link_dist[link] = 1
                link_unit_id[resource.notes] = unit_id

            yield resource.get_document()

    for resource in ExternalLinkResource.generate_all_from_dist_dict(
            link_dist, link_unit_id, timestamps):
        yield resource.get_document()


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
