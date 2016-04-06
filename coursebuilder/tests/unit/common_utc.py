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

"""Unit tests for common.utc."""

__author__ = 'Todd Larsen (tlarsen@google.com)'

import calendar
import datetime
import time
import unittest

from common import schema_transforms
from common import utc


class UtcUnitTests(unittest.TestCase):

    # Would use schema_transforms.ISO_8601_DATETIME_FORMAT here, but, since
    # time.strftime() expects whole seconds (no fractional part), the ".%f"
    # present in that format string is not desired. time.strftime() is used
    # to generate "expected text" values, since, with this specific format
    # string, those results should match the whole-seconds values transformed
    # by datetime.strftime(ISO_8601_DATETIME_FORMAT).
    ISO_8601_STRUCT_TIME_FORMAT = '%Y-%m-%dT%H:%M:%S.000000Z'

    def setUp(self):
        self.now_seconds = utc.now_as_timestamp()
        self.now_st = time.gmtime(self.now_seconds)
        self.now_text = time.strftime(
            self.ISO_8601_STRUCT_TIME_FORMAT, self.now_st)
        self.now_dt = datetime.datetime.utcfromtimestamp(self.now_seconds)

        self.day_dt = datetime.datetime(
            self.now_dt.year, self.now_dt.month, self.now_dt.day)
        self.day_st = (
            self.now_st.tm_year, self.now_st.tm_mon, self.now_st.tm_mday,
            0, 0, 0, # Force to 00:00:00, leaving all else unchanged.
            self.now_st.tm_wday, self.now_st.tm_yday, self.now_st.tm_isdst)

        self.month_dt = datetime.datetime(
            self.now_dt.year, self.now_dt.month, 1)
        self.month_st = self.month_dt.utctimetuple()
        self.month_text = time.strftime(
            self.ISO_8601_STRUCT_TIME_FORMAT, self.month_st)

        self.year_dt = datetime.datetime(self.now_dt.year, 1, 1)
        self.year_st = self.year_dt.utctimetuple()
        self.year_text = time.strftime(
            self.ISO_8601_STRUCT_TIME_FORMAT, self.year_st)

    def test_to_timestamp(self):
        """Confirm precedence of seconds, dt, st, or text in to_timestamp()."""
        # Select now_seconds value, because seconds= was supplied.
        self.assertEquals(
            utc.to_timestamp(
                seconds=self.now_seconds, dt=self.day_dt, st=self.month_st,
                text=self.year_text),
            self.now_seconds)

        # Select day start value, because seconds= was not supplied, and
        # dt was supplied.
        self.assertEquals(
            utc.to_timestamp(
                dt=self.day_dt, st=self.month_st, text=self.year_text),
            utc.day_start(self.now_seconds))

        # Select month value, because seconds= and dt= were not supplied, and
        # st was supplied.
        self.assertEquals(
            utc.to_timestamp(st=self.month_st, text=self.year_text),
            calendar.timegm(self.month_dt.utctimetuple()))

        # Select year value, because seconds=, dt=, and st= were not supplied,
        # and text was supplied.
        self.assertEquals(utc.to_timestamp(text=self.year_text),
            calendar.timegm(self.year_dt.utctimetuple()))

        # Select new "now" value, because seconds=, dt=, st=, and text= were
        # all missing.
        self.assertTrue(utc.to_timestamp() >= self.now_seconds)

    def test_day_start_end(self):
        """Tests day_start() and day_end() with time and datetime methods."""
        # The "start-of-day" of any UTC time should be that date, but after
        # forcing the hour:minute:second time to the first second of the day.
        start_dt_epoch = calendar.timegm(self.day_dt.utctimetuple())
        start_st_epoch = calendar.timegm(self.day_st)
        self.assertEquals(start_dt_epoch, start_st_epoch)

        # Make the last second of a UTC day, 23:59:59, by forcing hour, minutes,
        # and seconds to the above limits. THe call to day_start should still
        # results in 00:00:00.
        end_dt = self.now_dt.replace(hour=23, minute=59, second=59)
        end_dt_epoch = calendar.timegm(end_dt.utctimetuple())
        end_st = (
            self.now_st.tm_year, self.now_st.tm_mon, self.now_st.tm_mday,
            23, 59, 59, # Force to 23:59:59, leaving all else unchanged.
            self.now_st.tm_wday, self.now_st.tm_yday, self.now_st.tm_isdst)
        end_st_epoch = calendar.timegm(end_st)
        self.assertEquals(end_dt_epoch, end_st_epoch)

        self.assertEquals(utc.day_start(start_dt_epoch), start_dt_epoch)
        self.assertEquals(utc.day_start(self.now_seconds), start_dt_epoch)
        self.assertEquals(utc.day_start(end_dt_epoch), start_dt_epoch)

        self.assertEquals(utc.day_end(start_dt_epoch), end_dt_epoch)
        self.assertEquals(utc.day_end(self.now_seconds), end_dt_epoch)
        self.assertEquals(utc.day_end(end_dt_epoch), end_dt_epoch)

    def test_to_text(self):
        """Confirm precedence of seconds, dt, and st in to_text()."""
        # Select now_seconds value, because seconds= was supplied.
        self.assertEquals(
            utc.to_text(
                seconds=self.now_seconds, dt=self.day_dt, st=self.month_st),
            time.strftime(self.ISO_8601_STRUCT_TIME_FORMAT, self.now_st))

        # Select day_st value, because seconds= was not supplied, and
        # dt was supplied.
        self.assertEquals(
            utc.to_text(dt=self.day_dt, st=self.month_st),
            time.strftime(self.ISO_8601_STRUCT_TIME_FORMAT, self.day_st))

        # Select month value, because seconds= and dt= were not supplied, and
        # st was supplied.
        self.assertEquals(utc.to_text(st=self.month_st),
            time.strftime(self.ISO_8601_STRUCT_TIME_FORMAT, self.month_st))

    def test_leap_second(self):
        """Points out that Python does not know when the leap seconds are.

        This matters because, for example, StudentLifecycleObserver handlers
        are supplied a datetime.datetime, which includes explicit seconds,
        like what is obtained from the ISO_8601_DATETIME_FORMAT string
        ('%Y-%m-%dT%H:%M:%S.%fZ').

        The (harmless?) outcome is that events occurring during the leap
        second (23:59:60) will be added to the next day tallies.
        """
        # 30 Jun 2015 23:59:60 is the most recent leap second, as of this
        # test. time.strptime() is used here, instead of
        # datetime.datetime.strptime(), because the latter function does
        # not understand leap seconds at all, instead complaining with:
        #   ValueError: second must be in 0..59
        leap_st = time.strptime("2015-06-30T23:59:60.0Z",
                                schema_transforms.ISO_8601_DATETIME_FORMAT)
        self.assertEquals(leap_st.tm_year, 2015)
        self.assertEquals(leap_st.tm_mon, 6)
        self.assertEquals(leap_st.tm_mday, 30)
        self.assertEquals(leap_st.tm_hour, 23)
        self.assertEquals(leap_st.tm_min, 59)
        self.assertEquals(leap_st.tm_sec, 60) # Not 59, but leap second as 60.
        leap_epoch = long(calendar.timegm(leap_st))

        # 30 Jun 2015 23:59:59 is the last "normal" second in 2015-06-30,
        # just prior to the leap second.
        last_dt = datetime.datetime.strptime(
            "2015-06-30T23:59:59.0Z",
            schema_transforms.ISO_8601_DATETIME_FORMAT)
        last_st = last_dt.utctimetuple()
        self.assertEquals(last_st.tm_year, 2015)
        self.assertEquals(last_st.tm_mon, 6)
        self.assertEquals(last_st.tm_mday, 30)
        self.assertEquals(last_st.tm_hour, 23)
        self.assertEquals(last_st.tm_min, 59)
        self.assertEquals(last_st.tm_sec, 59)
        last_epoch = long(calendar.timegm(last_st))

        # According to Posix, "Unix time" (seconds since the 1970-01-01 epoch
        # also known as a "Posix timestamp") should repeat itself for one
        # second during a leap second, but the following confirms this not to
        # be the case. It should not be necessary to add the `+ 1`.
        self.assertEquals(leap_epoch, last_epoch + 1)

        # The tangible effect of this is that events occurring during the
        # actual leap second end up in the tallies for the next day.
        day_sec = 24 * 60 * 60
        self.assertEquals(utc.day_start(leap_epoch),
                          utc.day_start(last_epoch) + day_sec)
