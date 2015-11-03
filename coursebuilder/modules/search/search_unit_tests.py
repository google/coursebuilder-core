# -*- coding: utf-8 -*-

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

"""Unit tests for the Search module."""

__author__ = 'Ellis Michael (emichael@google.com)'

import re
import robotparser
import urlparse

from modules.search import resources
from tests.functional import actions

from google.appengine.api import urlfetch


VALID_PAGE_URL = 'http://valid.null/'
VALID_PAGE = """<html>
                  <head>
                    <title>Test Page</title>
                    <script>
                        alert('test');
                    </script>
                    <style>
                        body {
                          font-size: 12px;
                        }
                    </style>
                  </head>
                  <body>
                    Lorem ipsum <strong> dolor </strong> sit.
                    <a href="index.php?query=bibi%20quid">Ago gratias tibi</a>.
                    <a>Cogito ergo sum.</a>
                    <a href="//partial.null/"> Partial link </a>
                    <a href="ftp://absolute.null/"> Absolute link </a>
                    <a href="http://pdf.null/"> PDF </a>
                    <a href="http://link.null/"> Link </a>
                  </body>
                </html>"""
VALID_PAGE_ROBOTS = ('User-agent: *', 'Allow: /')

LINKED_PAGE_URL = 'http://link.null/'
LINKED_PAGE = """<a href="http://distance2link.null/">
                   What hath God wrought?
                 </a>"""

SECOND_LINK_PAGE_URL = 'http://distance2link.null/'
SECOND_LINK_PAGE = """Something went terribly wrong. ABORT"""

UNICODE_PAGE_URL = 'http://unicode.null/'
UNICODE_PAGE = """<html>
                     <head>
                       <title>‘Quoted string’</title>
                     </head>
                     <body>
                       Russell's Paradox: <br/>
                       ∃ y∀ x(x∈ y ⇔ P(x)) <br/>
                       Let P(x)=~(x∈ x), x=y. <br/>
                       y∈ y ⇔ ~(y∈ y)
                     </body>
                   </html>"""

PDF_URL = 'http://pdf.null/'

XML_DOC_URL = 'http://xml.null/'
XML_DOC = """<document attribute="foo">
               <childNode>
                 Text content.
               </childNode>
             </document>"""

YOUTUBE_TRANSCRIPT_URL = (resources.YOUTUBE_TIMED_TEXT_URL +
                          '?.*name=Name%20of%20track.*$')
YOUTUBE_TRANSCRIPT = """<transcript>
                          <text start="3.14" dur="6.28">
                            Apple, lemon, cherry...
                          </text>
                          <text start="20.0" dur="20.0">
                            It&#39;s a test.
                          </text>
                        </transcript>"""

GDATA_DOC_URL = resources.YOUTUBE_DATA_URL
GDATA_DOC = """<?xml version='1.0' encoding='UTF-8'?>
               <entry xmlns='http://www.w3.org/2005/Atom'
                   xmlns:media='http://search.yahoo.com/mrss/'>
                 <title type="text">
                   Medicus Quis
                 </title>
                 <media:thumbnail url="http://thumbnail.null"/>
               </entry>"""

YOUTUBE_TRANSCRIPT_LIST_URL = (resources.YOUTUBE_TIMED_TEXT_URL +
                               '?.*type=list.*$')
YOUTUBE_TRANSCRIPT_LIST = """<transcript_list docid="123456789">
                               <track id="0" name="Name of track"
                                   lang_code="en" lang_original="English"
                                   lang_translated="English"
                                   lang_default="true" />
                             </transcript_list>"""

BANNED_PAGE_URL = 'http://banned.null/'
BANNED_PAGE = 'Should not be accessed'
BANNED_PAGE_ROBOTS = ('User-agent: *', 'Disallow: /')


class SearchTestBase(actions.TestBase):
    """Unit tests for all search functionality."""

    pages = {VALID_PAGE_URL + '$':  # Using $ to prevent erroneous matches
             (VALID_PAGE, 'text/html'),

             urlparse.urljoin(VALID_PAGE_URL, '/robots.txt'):
             (VALID_PAGE_ROBOTS, 'text/html'),

             LINKED_PAGE_URL + '$':
             (LINKED_PAGE, 'text/html'),

             urlparse.urljoin(LINKED_PAGE_URL, '/robots.txt'):
             (VALID_PAGE_ROBOTS, 'text/html'),

             SECOND_LINK_PAGE_URL + '$':
             (SECOND_LINK_PAGE, 'text/html'),

             urlparse.urljoin(SECOND_LINK_PAGE_URL, '/robots.txt'):
             (VALID_PAGE_ROBOTS, 'text/html'),

             PDF_URL:
             (VALID_PAGE, 'application/pdf'),

             UNICODE_PAGE_URL + '$':
             (UNICODE_PAGE, 'text/html charset=utf-8'),

             urlparse.urljoin(UNICODE_PAGE_URL, '/robots.txt'):
             (VALID_PAGE_ROBOTS, 'text/html'),

             XML_DOC_URL + '$':
             (XML_DOC, 'text/xml'),

             urlparse.urljoin(XML_DOC_URL, '/robots.txt'):
             (VALID_PAGE_ROBOTS, 'text/html'),

             YOUTUBE_TRANSCRIPT_URL:
             (YOUTUBE_TRANSCRIPT, 'text/xml'),

             GDATA_DOC_URL:
             (GDATA_DOC, 'text/xml'),

             YOUTUBE_TRANSCRIPT_LIST_URL:
             (YOUTUBE_TRANSCRIPT_LIST, 'text/xml'),

             # The default Power Searching course has notes in this domain
             'http://www.google.com/robots.txt':
             (VALID_PAGE_ROBOTS, 'text/html'),

             BANNED_PAGE_URL + '$':
             (BANNED_PAGE, 'text/html'),

             urlparse.urljoin(BANNED_PAGE_URL, '/robots.txt'):
             (BANNED_PAGE_ROBOTS, 'text/html'),
            }

    def setUp(self):
        """Do all of the necessary monkey patching to test search."""
        super(SearchTestBase, self).setUp()

        def return_doc(url):
            """Monkey patch for URL fetching."""

            class Response(object):

                def __init__(self, code, content_type, content):
                    self.status_code = code
                    self.headers = {}
                    self.headers['Content-type'] = content_type
                    self.content = content

            for pattern in self.pages:
                if re.match(pattern, url):
                    page_data = self.pages[pattern]
                    body = page_data[0]
                    content_type = page_data[1]
                    break
            else:
                body = VALID_PAGE
                content_type = 'text/html'

            result = Response(200, content_type, body)
            return result

        self.swap(urlfetch, 'fetch', return_doc)

        class FakeRobotParser(robotparser.RobotFileParser):
            """Monkey patch for robot parser."""

            def read(self):
                parts = urlparse.urlsplit(self.url)
                if not (parts.netloc and parts.scheme):
                    raise IOError
                response = urlfetch.fetch(self.url)
                self.parse(response.content)

        self.swap(robotparser, 'RobotFileParser', FakeRobotParser)


class ParserTests(SearchTestBase):
    """Unit tests for the search HTML Parser."""

    def setUp(self):
        super(ParserTests, self).setUp()

        self.parser = resources.ResourceHTMLParser(VALID_PAGE_URL)
        self.parser.feed(VALID_PAGE)

    def test_found_tokens(self):
        content = self.parser.get_content()
        for text in ['Lorem', 'ipsum', 'dolor']:
            self.assertIn(text, content)

    def test_no_false_matches(self):
        content = self.parser.get_content()
        for text in ['Loremipsum', 'ipsumdolor', 'tibiCogito', 'sit.Ago']:
            self.assertNotIn(text, content)

    def test_ignored_fields(self):
        content = self.parser.get_content()
        for text in ['alert', 'font-size', 'body', 'script', 'style']:
            self.assertNotIn(text, content)

    def test_links(self):
        links = self.parser.get_links()
        self.assertIn('http://valid.null/index.php?query=bibi%20quid', links)
        self.assertIn('http://partial.null/', links)
        self.assertIn('ftp://absolute.null/', links)
        self.assertEqual(len(links), 5)

    def test_unopened_tag(self):
        self.parser = resources.ResourceHTMLParser('')
        self.parser.feed('Lorem ipsum </script> dolor sit.')
        content = self.parser.get_content()
        for text in ['Lorem', 'ipsum', 'dolor', 'sit']:
            self.assertIn(text, content)

    def test_title(self):
        self.assertEqual('Test Page', self.parser.get_title())

    def test_get_parser_allowed(self):
        self.parser = resources.get_parser_for_html(VALID_PAGE_URL)
        content = self.parser.get_content()
        self.assertIn('Cogito ergo sum', content)

        with self.assertRaises(resources.URLNotParseableException):
            self.parser = resources.get_parser_for_html(BANNED_PAGE_URL)
            content = self.parser.get_content()
            self.assertNotIn('accessed', content)

    def test_bad_urls(self):
        for url in ['http://', 'invalid.null', '//invalid.null', '//',
                    'invalid', '?test=1', 'invalid?test=1']:
            with self.assertRaises(resources.URLNotParseableException):
                self.parser = resources.get_parser_for_html(url)
                content = self.parser.get_content()
                self.assertNotIn('impsum', content)

    def test_unicode_page(self):
        self.parser = resources.get_parser_for_html(UNICODE_PAGE_URL)
        content = self.parser.get_content()
        self.assertIn('Paradox', content)

        title = self.parser.get_title()
        self.assertIn('Quoted string', title)

    def test_xml_parser(self):
        dom = resources.get_minidom_from_xml(XML_DOC_URL)
        self.assertEqual('foo', dom.getElementsByTagName(
            'document')[0].attributes['attribute'].value)
        self.assertIn('Text content.', dom.getElementsByTagName(
            'childNode')[0].firstChild.nodeValue)
