# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Classes and functions defining allowed asset upload paths."""

__author__ = 'Todd Larsen (tlarsen@google.com)'


class AllowedBases(object):
    """Manages the set of asset path bases for which uploading is allowed."""

    # Set of string. The relative, normalized path bases we allow uploading of
    # binary data into.
    _BINARY_BASES = frozenset([
        '/assets/img/',
    ])

    # Set of string. The relative, normalized path bases we allow uploading of
    # text data into.
    _TEXT_BASES = frozenset([
        '/assets/css/',
        '/assets/html/',
        '/assets/lib/',
        '/views/'
    ])

    # Set of string. The relative, normalized path bases we allow uploads into.
    _ALLOWED_BASES = frozenset(_BINARY_BASES.union(_TEXT_BASES))

    @classmethod
    def all_bases(cls, bases=None):
        """Returns caller-supplied non-empty bases, or all allowed bases."""
        return cls._ALLOWED_BASES if not bases else bases

    @classmethod
    def binary_bases(cls):
        """Returns all allowed binary bases (e.g. asset bases for images)."""
        return cls._BINARY_BASES

    @classmethod
    def text_bases(cls):
        """Returns all allowed text bases (e.g. asset bases for templates)."""
        return cls._TEXT_BASES

    @classmethod
    def is_path_allowed(cls, path, bases=None):
        matched_base = cls.match_allowed_bases(path, bases=bases)
        return True if matched_base else False

    @classmethod
    def match_allowed_bases(cls, path, bases=None):
        # Just use _ALLOWED_BASES if the caller (or, more likely, a caller of
        # is_path_allowed()) did not specify a custom set of bases. Otherwise,
        # use the caller-supplied custom subset (typically acquired via either
        # text_bases() or binary_bases()).
        bases = cls.all_bases(bases=bases)
        for base in bases:
            if does_path_match_base(path, base):
                return base
        return None

    @classmethod
    def add_text_base(cls, base):
        cls.add_text_bases([base])

    @classmethod
    def add_text_bases(cls, bases):
        # Insure that caller-supplied bases are in "base" asset path form.
        cls._TEXT_BASES = cls._TEXT_BASES.union(as_bases(bases))
        cls._update_allowed_bases()

    @classmethod
    def del_text_base(cls, base):
        cls.del_text_bases([base])

    @classmethod
    def del_text_bases(cls, bases):
        # Insure that caller-supplied bases are in "base" asset path form.
        cls._TEXT_BASES = cls._TEXT_BASES.difference(as_bases(bases))
        cls._update_allowed_bases()

    @classmethod
    def add_binary_base(cls, base):
        cls.add_binary_bases([base])

    @classmethod
    def add_binary_bases(cls, bases):
        # Insure that caller-supplied bases are in "base" asset path form.
        cls._BINARY_BASES = cls._BINARY_BASES.union(as_bases(bases))
        cls._update_allowed_bases()

    @classmethod
    def del_binary_base(cls, base):
        cls.del_binary_bases([base])

    @classmethod
    def del_binary_bases(cls, bases):
        # Insure that caller-supplied bases are in "base" asset path form.
        cls._BINARY_BASES = cls._BINARY_BASES.difference(as_bases(bases))
        cls._update_allowed_bases()

    @classmethod
    def _update_allowed_bases(cls):
        cls._ALLOWED_BASES = frozenset(cls._BINARY_BASES.union(cls._TEXT_BASES))


def as_key(key):
    """Strips any / prefix and/or suffix from a supplied key (path) string.

    Most uses of the asset path as a key (other than validation by
    is_path_allowed) expect any leading and trailing / URL path
    separators have been removed.
    """
    return key.lstrip('/').rstrip('/')


def as_base(path):
    """Prefixes and suffixes the provided path string with / if not present.

    "Base" paths, with their leading and trailing / URL path separators, are
    used when deciding if an asset path (also known as an asset 'key') is
    allowed for uploading, to prevent partial matches like 'views_of_space'
    matching because it has a prefix of 'views'. The base '/views/' path is
    protected from matching a corresponding base '/views_of_space/' path.
    """
    path = path if path.startswith('/') else '/' + path
    return  path if path.endswith('/') else path + '/'


def as_bases(bases):
    return (as_base(base) for base in bases)


def relative_base(base):
    """Removes / URL path separator prefix but ensures suffix is present."""
    return as_base(base).lstrip('/')


def does_path_match_base(path, base):
    """Returns True if path is validly prefixed with the supplied base."""
    # Do not trust caller to have supplied a / URL path separator prefixed
    # and suffixed "base" asset path. as_base() will simply be a no-op for a
    # base that is already properly delimited.
    canonical = as_base(base)

    if path == canonical:
        # Exact match of allowed "base" asset path, including leading and
        # trailing / URL path separators.
        return True

    if (len(path) > len(canonical)) and path.startswith(canonical):
        # Asset path is prefixed by an allowed "base" asset path, including
        # the leading and trailing / URL path separators (with the trailing
        # base separator at the correct position in the asset path).
        return True

    if path == as_key(base):
        # Exact match (with no extra path length) of allowed asset base key
        # (an allowed asset base path with the leading and trailing / URL path
        # separators strippped).
        return True

    relative = relative_base(base)

    if path == relative:
        # Exact match of relative "base" asset path, with trailing, but not
        # leading, / URL path separator.
        return True

    if (len(path) > len(relative)) and path.startswith(relative):
        # Asset path must at least be longer than the relative base as
        # a path prefix (e.g. assets/img/), and must start with exactly
        # that prefix (including the trailing / URL path separator in the
        # correct position in the path).
        return True

    return False
