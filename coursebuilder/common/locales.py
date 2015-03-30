# -*- coding: utf-8; -*-
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

"""Functions used for Course Builder locale support."""

__author__ = 'John Orr (jorr@google.com)'

import logging
import os
import re

import appengine_config


# Locale description information based on Babel Locale.display_name. However
# the names are collected here because (i) Babel does not have correct display
# names for all of the locales included, and (ii) Babel cannot access its
# localeinfo data when it is loaded as a Zip file.
LOCALES_DISPLAY_NAMES = {
    'af': u'Afrikaans (af)',
    'am': u'አማርኛ (am)',
    'ar': u'العربية (ar)',
    'bg': u'български (bg)',
    'bn': u'বাংলা (bn)',
    'ca': u'català (ca)',
    'cs': u'čeština (cs)',
    'da': u'dansk (da)',
    'de': u'Deutsch (de)',
    'el': u'Ελληνικά (el)',
    'en_GB': u'British English (en_GB)',
    'en_US': u'U.S. English (en_US)',
    'es': u'español (es)',
    'et': u'eesti (et)',
    'eu': u'euskara (eu)',
    'fa': u'فارسی (fa)',
    'fi': u'suomi (fi)',
    'fil': u'Filipino (fil)',
    'fr': u'français (fr)',
    'gl': u'galego (gl)',
    'gu': u'ગુજરાતી (gu)',
    'hi': u'हिन्दी (hi)',
    'hr': u'hrvatski (hr)',
    'hu': u'magyar (hu)',
    'id': u'Bahasa Indonesia (id)',
    'is': u'íslenska (is)',
    'it': u'italiano (it)',
    'iw': u'עברית (iw)',  # Former ISO-639 code for Hebrew; should now be he
    'ja': u'日本語 (ja)',
    'kn': u'ಕನ್ನಡ (kn)',
    'ko': u'한국어 (ko)',
    'ln': u'Fake Translation (ln)',
    'lt': u'lietuvių (lt)',
    'lv': u'latviešu (lv)',
    'ml': u'മലയാളം (ml)',
    'mr': u'मराठी (mr)',
    'ms': u'Bahasa Melayu (ms)',
    'nl': u'Nederlands (nl)',
    'no': u'Nynorsk (no)',  # Correct ISO-369-1 is nn and ISO-369-2 is nno
    'pl': u'polski (pl)',
    'pt_BR': u'português do Brasil (pt_BR)',
    'pt_PT': u'português europeu (pt_PT)',
    'ro': u'română (ro)',
    'ru': u'русский (ru)',
    'sk': u'slovenský (sk)',
    'sl': u'slovenščina (sl)',
    'sr': u'Српски (sr)',
    'sv': u'svenska (sv)',
    'sw': u'Kiswahili (sw)',
    'ta': u'தமிழ் (ta)',
    'te': u'తెలుగు (te)',
    'th': u'ไทย (th)',
    'tr': u'Türkçe (tr)',
    'uk': u'українська (uk)',
    'ur': u'اردو (ur)',
    'vi': u'Tiếng Việt (vi)',
    'zh_CN': u'中文 (简体) (zh_CN)',  # Chinese (Simplified)
    'zh_TW': u'中文 (繁體) (zh_TW)',  # Chinese (Traditional)
    'zu': u'isiZulu (zu)',
}


def get_system_supported_locales():
    translations_path = os.path.join(
        appengine_config.BUNDLE_ROOT, 'modules/i18n/resources/locale')
    return sorted(os.listdir(translations_path) + ['ln'])


def get_locale_display_name(locale):
    return LOCALES_DISPLAY_NAMES.get(locale, locale)


def parse_accept_language(accept_language_str):
    """Parse a RFC 2616 Accept-Language string.

    Accept-Language strings are of the form
        en-US,en;q=0.8,el;q=0.6
    where each language string (en-US, en, el) may be followed by a quality
    score (q). So in the example US English has default quality score (1),
    English has quality score 0.8, and Greek has quality score 0.6.

    Args:
        accept_language_str: str. A string in RFC 2616 format. If the string is
        None or empty, an empty list is return.

    Returns:
        A list of pairs. The first element of the pair is the language code
        (a str) and the second element is either a float between 0 and 1.
        The list is sorted in decreasing order by q, so that the highest
        quality language is the first element of the list.

    Refs:
        http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14
    """
    if not accept_language_str:
        return []
    assert len(accept_language_str) < 8 * 1024

    parsed = []
    try:
        for item in accept_language_str.split(','):
            lang = item.strip()
            q = 1.0
            if ';' in item:
                lang, q_str = item.split(';')
                q = float(q_str[2:]) if q_str.startswith('q=') else float(q_str)
            components = lang.split('-')
            if not all([re.match('^[a-zA-Z]+$', c) for c in components]):
                continue
            lang = '_'.join(
                [components[0].lower()] + [c.upper() for c in components[1:]])
            parsed.append((lang, q))
        return sorted(parsed, None, lambda x: -x[1])
    except Exception:  # pylint: disable=broad-except
        logging.exception('Bad Accept-Languager: %s', accept_language_str)
    return []
