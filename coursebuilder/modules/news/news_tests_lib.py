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

"""Test news module functionality."""

__author__ = [
    'mgainer@google.com (Mike Gainer)',
]

import collections

from modules.news import news


NewsItem = collections.namedtuple('NewsItem', ['desc', 'url', 'is_new'])


def extract_news_items_from_soup(soup):
    """Find news items in a BeautifulSoup parse tree.  Used in many modules."""

    news_items = soup.select('.gcb_news_item')
    ret = []
    for item in news_items:
        is_new = None
        if 'gcb_new_news' in item.get('class'):
            is_new = True
        elif 'gcb_old_news' in item.get('class'):
            is_new = False
        else:
            raise ValueError('News item not marked as new or old!')
        link = item.find('a')
        href = link.get('href')
        text = link.text.strip()
        ret.append(NewsItem(text, href, is_new))
    return ret


def force_news_enabled(wrapped_func):
    """Decorator that forces news module to be enabled for individual tests."""

    def wrapper_func(*args, **kwargs):
        if not news.custom_module.enabled:
            news.custom_module.enable()
        save_is_enabled = news.is_enabled
        news.is_enabled = lambda: True
        ret = wrapped_func(*args, **kwargs)
        news.is_enabled = save_is_enabled
        return ret

    return wrapper_func
