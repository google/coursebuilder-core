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

"""UTC date/time utility functions common to all of CourseBuilder."""

__author__ = 'Todd Larsen (tlarsen@google.com)'

import calendar
import datetime
import time

from common import schema_transforms


# Alias existing ISO 8601 formats from schema_transforms.py for convenience.
ISO_8601_DATE_FMT = schema_transforms.ISO_8601_DATE_FORMAT
ISO_8601_DATETIME_FMT = schema_transforms.ISO_8601_DATETIME_FORMAT

# Human-readable ISO 8601 date format (compared to ISO_8601_DATETIME_FMT).
ISO_8601_UTC_HUMAN_FMT = '%Y-%m-%d %H:%M:%S UTC'


def datetime_to_timestamp(utc_dt):
    """Returns UTC datetime as a POSIX timestamp (seconds since epoch).

    Args:
        utc_dt: a datetime.datetime object storing a UTC date and time.
    Returns:
        The UTC date and time as whole seconds since epoch. Leap seconds
        (utc_dt.second > 59) are "collapsed" to the last non-leap second (59),
        since POSIX timestamps (AKA "Unix time") collapse leap seconds in this
        way by definition, see also:
            http://en.wikipedia.org/wiki/Unix_time#Leap_seconds
    """
    no_leap_second = min(59, utc_dt.second)
    no_leap_dt = utc_dt.replace(second=no_leap_second)
    return calendar.timegm(utc_dt.utctimetuple())


def timestamp_to_datetime(utc_timestamp):
    """Returns UTC datetime corresponding to POSIX timestamp (secs since epoch).

    Args:
        utc_timestamp: Seconds since Jan 1, 1970 UTC.
    Returns:
        A datetime instance with tzinfo set to None.
    """
    return datetime.datetime.utcfromtimestamp(utc_timestamp)


def struct_time_to_timestamp(utc_st):
    """Returns UTC struct_time as a POSIX timestamp (seconds since epoch)."""
    no_leap_second = min(59, utc_st.tm_sec)
    return calendar.timegm(
        (utc_st.tm_year, utc_st.tm_mon, utc_st.tm_mday,
         utc_st.tm_hour, utc_st.tm_min, no_leap_second,
         utc_st.tm_wday, utc_st.tm_yday, utc_st.tm_isdst))


def text_to_timestamp(text, fmt=ISO_8601_DATETIME_FMT):
    """Returns UTC time string as a POSIX timestamp (seconds since epoch).

    Args:
        text: string containing UTC date and time in the specified format.
        fmt: a datetime strftime format string; defaults to
            ISO_8601_DATETIME_FMT.
    """
    utc_dt = datetime.datetime.strptime(text, fmt)
    return datetime_to_timestamp(utc_dt)


def text_to_datetime(text, fmt=ISO_8601_DATETIME_FMT):
    """Returns UTC datetime for stringified date in given format."""
    return timestamp_to_datetime(text_to_timestamp(text, fmt=fmt))


def now_as_timestamp(_test_fixed_seconds=None):
    """Returns the current UTC time, as whole seconds since epoch."""
    # datetime alternative:
    #   if _test_fixed_seconds is None:
    #     now_dt = datetime.datetime.utcnow()
    #   else:
    #     now_dt = datetime.datetime.utcfromtimestamp(_test_fixed_seconds)
    #   return calendar.timegm(now_dt.utctimetuple())

    # calendar.timegm() always produces whole seconds (int or long) results.
    return struct_time_to_timestamp(time.gmtime(_test_fixed_seconds))


def now_as_datetime():
    """Get UTC datetime for current time."""
    return timestamp_to_datetime(now_as_timestamp())


def to_timestamp(seconds=None, dt=None, st=None, text=None,
                 fmt=ISO_8601_DATETIME_FMT):
    """Returns POSIX timestamp (seconds since epoch), from optional parameters.

    In order of precedence, the first of these values is used to return a UTC
    time in whole seconds since epoch:
        seconds, dt, st, text
    If none of these is supplied, now_as_timestamp() is called to obtain the
    current time.

    Args:
        seconds: UTC time, as seconds since epoch, -OR-
        dt: UTC time, as datetime.datetime, -OR-
        st: UTC time, as a time.struct_time, -OR-
        text: string containing UTC date and time in the specified format.
        fmt: a datetime strftime format string; defaults to
            ISO_8601_DATETIME_FMT.
    Returns:
        seconds, unchanged, if not None, else:
        dt, converted to UTC seconds since epoch, if not None, else:
        st, converted to UTC seconds since epoch, if not None, else:
        text, converted to UTC seconds since epoch, if not None, else:
        now_as_timestamp().
    """
    if seconds is not None:
        return seconds

    if dt is not None:
        return datetime_to_timestamp(dt)

    if st is not None:
        return struct_time_to_timestamp(st)

    if text is not None:
        return text_to_timestamp(text, fmt=fmt)

    return now_as_timestamp()


_SECONDS_PER_DAY = 24 * 60 * 60


def day_start(seconds):
    """Truncates a POSIX timestamp to the start of that day (00:00:00).

    Args:
        seconds: an arbitrary UTC time, as seconds since epoch (stored
            in whatever time.gmtime will accept, i.e. int, long, or float).
    Returns:
        The supplied UTC time truncated to 00:00:00 of that same day, as whole
        seconds since epoch.
    """
    # datetime alternative:
    #
    #   if seconds is None:
    #     utc_dt = datetime.datetime.utcnow()
    #   else:
    #     utc_dt = datetime.datetime.utcfromtimestamp(seconds)
    #   day_dt = utc_dt.replace(hour=0, minute=0, second=0)
    #   return long(calendar.timegm(day_dt.utctimetuple()))
    #
    # struct_time alternative:
    #
    #   gmt_st = time.gmtime(seconds) # Convert UTC seconds to struct_time.
    #   day_st = (gmt_st.tm_year, gmt_st.tm_mon, gmt_st.tm_mday,
    #             0, 0, 0, # Force time to 00:00:00, leaving all else unchanged.
    #             gmt_st.tm_wday, gmt_st.tm_yday, gmt_st.tm_isdst)
    #   return long(calendar.timegm(day_st)) # Back to seconds since epoch.
    return (seconds // _SECONDS_PER_DAY) * _SECONDS_PER_DAY


_LAST_SECOND_OF_DAY = _SECONDS_PER_DAY - 1


def day_end(seconds):
    """Forces a POSIX timestamp to the end of that day (23:59:59).

    Args:
        seconds: an arbitrary UTC time, as seconds since epoch (stored
            in whatever time.gmtime will accept, i.e. int, long, or float).
    Returns:
        The supplied UTC time forced to 23:59:59 of that same day, as whole
        seconds since epoch. This function ignores the possibility of leap
        seconds, returning strict POSIX timestamps.
    """
    # datetime alternative:
    #
    #   if seconds is None:
    #     utc_dt = datetime.datetime.utcnow()
    #   else:
    #     utc_dt = datetime.datetime.utcfromtimestamp(seconds)
    #   day_dt = utc_dt.replace(hour=23, minute=59, second=59)
    #   return long(calendar.timegm(day_dt.utctimetuple()))
    #
    # struct_time alternative:
    #
    #   gmt_st = time.gmtime(seconds) # Convert UTC seconds to struct_time.
    #   day_st = (gmt_st.tm_year, gmt_st.tm_mon, gmt_st.tm_mday,
    #             23, 59, 59, # Force to 23:59:59, leaving all else unchanged.
    #             gmt_st.tm_wday, gmt_st.tm_yday, gmt_st.tm_isdst)
    #   return long(calendar.timegm(day_st)) # Back to seconds since epoch.
    return day_start(seconds) + _LAST_SECOND_OF_DAY


_SECONDS_PER_HOUR = 60 * 60


def hour_start(seconds):
    """Truncates a POSIX timestamp to the start of that hour (HH:00:00).

    Args:
        seconds: an arbitrary UTC time, as seconds since epoch (stored
            in whatever time.gmtime will accept, i.e. int, long, or float).
    Returns:
        The supplied UTC time truncated to HH:00:00 of that same hour, as whole
        seconds since epoch.
    """
    # datetime alternative:
    #
    #   if seconds is None:
    #     utc_dt = datetime.datetime.utcnow()
    #   else:
    #     utc_dt = datetime.datetime.utcfromtimestamp(seconds)
    #   day_dt = utc_dt.replace(minute=0, second=0)
    #   return long(calendar.timegm(day_dt.utctimetuple()))
    #
    # struct_time alternative:
    #
    #   gmt_st = time.gmtime(seconds) # Convert UTC seconds to struct_time.
    #   day_st = (gmt_st.tm_year, gmt_st.tm_mon, gmt_st.tm_mday,
    #             gmt_st.tm_hour, 0, 0, # Force to HH:00:00.
    #             gmt_st.tm_wday, gmt_st.tm_yday, gmt_st.tm_isdst)
    #   return long(calendar.timegm(day_st)) # Back to seconds since epoch.
    return (seconds // _SECONDS_PER_HOUR) * _SECONDS_PER_HOUR


_LAST_SECOND_OF_HOUR = _SECONDS_PER_HOUR - 1


def hour_end(seconds):
    """Forces a POSIX timestamp to the end of that hour (HH:59:59).

    Args:
        seconds: an arbitrary UTC time, as seconds since epoch (stored
            in whatever time.gmtime will accept, i.e. int, long, or float).
    Returns:
        The supplied UTC time forced to HH:59:59 of that same hour, as whole
        seconds since epoch. This function ignores the possibility of leap
        seconds, returning strict POSIX timestamps.
    """
    # datetime alternative:
    #
    #   if seconds is None:
    #     utc_dt = datetime.datetime.utcnow()
    #   else:
    #     utc_dt = datetime.datetime.utcfromtimestamp(seconds)
    #   day_dt = utc_dt.replace(minute=59, second=59)
    #   return long(calendar.timegm(day_dt.utctimetuple()))
    #
    # struct_time alternative:
    #
    #   gmt_st = time.gmtime(seconds) # Convert UTC seconds to struct_time.
    #   day_st = (gmt_st.tm_year, gmt_st.tm_mon, gmt_st.tm_mday,
    #             gmt_st.tm_hour, 59, 59, # Force to HH:59:59.
    #             gmt_st.tm_wday, gmt_st.tm_yday, gmt_st.tm_isdst)
    #   return long(calendar.timegm(day_st)) # Back to seconds since epoch.
    return hour_start(seconds) + _LAST_SECOND_OF_HOUR


def to_text(seconds=None, dt=None, st=None,
            fmt=ISO_8601_DATETIME_FMT):
    """Converts a UTC date and time into a string via datetime.strftime.

    In order of precedence, the first of these values is used to return a UTC
    time as a strftime-formatted string:  seconds, dt, st

    Args:
        seconds: UTC time, as seconds since epoch, -OR-
        dt: UTC time, as datetime.datetime, -OR-
        st: UTC time, as a time.struct_time.
        fmt: a time/datetime strftime format string; defaults to
            ISO_8601_DATETIME_FMT.
    """
    if seconds is not None:
        dt = datetime.datetime.utcfromtimestamp(seconds)

    if dt is None:
        dt = datetime.datetime.utcfromtimestamp(calendar.timegm(st))

    return dt.strftime(fmt)
