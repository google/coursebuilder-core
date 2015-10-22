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

"""Encryption and digest functionality."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import base64
import hashlib
import hmac
import os
import random
import time

import appengine_config
from common import messages
from common import users
from common import utils
from models import config


try:
    from Crypto.Cipher import AES
except ImportError:
    if appengine_config.PRODUCTION_MODE:
        raise

    class AES(object):
        """No-op crypto class to permit running on MacOS in dev mode."""

        MODE_CBC = 2

        @staticmethod
        def new(unused_1, unused_2, unused_3):
            return AES()

        def __init__(self):
            pass

        def _reverse(self, message):
            # "Encrypt" by reversing.  Just want to ensure that the encrypted
            # version differs from the plaintext so that nothing accidentally
            # relies on being able to read the nominally-encrypted value.
            m_list = list(message)
            m_list.reverse()
            return ''.join(m_list)

        def encrypt(self, message):
            return self._reverse(message)

        def decrypt(self, message):
            return self._reverse(message)


XSRF_SECRET_LENGTH = 20

XSRF_SECRET = config.ConfigProperty(
    'gcb_xsrf_secret', str, messages.SITE_SETTINGS_XSRF_SECRET,
    default_value='Course Builder XSRF Secret', label='XSRF secret')

ENCRYPTION_SECRET_LENGTH = 48

ENCRYPTION_SECRET = config.ConfigProperty(
    'gcb_encryption_secret', str, messages.SITE_SETTINGS_ENCRYPTION_SECRET,
    default_value='default value of CourseBuilder encryption secret',
    label='Encryption Secret',
    validator=config.ValidateLength(ENCRYPTION_SECRET_LENGTH).validator)


class EncryptionManager(object):

    @classmethod
    def init_secret_if_none(cls, cfg, length):

        # Any non-default value is fine.
        if cfg.value and cfg.value != cfg.default_value:
            return

        # All property manipulations must run in the default namespace.
        with utils.Namespace(appengine_config.DEFAULT_NAMESPACE_NAME):

            # Look in the datastore directly.
            entity = config.ConfigPropertyEntity.get_by_key_name(cfg.name)
            if not entity:
                entity = config.ConfigPropertyEntity(key_name=cfg.name)

            # Any non-default non-None value is fine.
            if (entity.value and not entity.is_draft and
                (str(entity.value) != str(cfg.default_value))):
                return

            # Initialize to random value.
            entity.value = base64.urlsafe_b64encode(
                os.urandom(int(length * 0.75)))
            entity.is_draft = False
            entity.put()

    @classmethod
    def _get_hmac_secret(cls):
        """Verifies that non-default XSRF secret exists; creates one if not."""
        cls.init_secret_if_none(XSRF_SECRET, XSRF_SECRET_LENGTH)
        return XSRF_SECRET.value

    @classmethod
    def _get_encryption_secret(cls):
        """Verifies non-default encryption secret exists; creates one if not."""
        cls.init_secret_if_none(ENCRYPTION_SECRET, ENCRYPTION_SECRET_LENGTH)
        return ENCRYPTION_SECRET.value

    @classmethod
    def hmac(cls, components):
        """Generate an XSRF over the array of components strings."""
        secret = cls._get_hmac_secret()
        digester = hmac.new(str(secret))
        for component in components:
            digester.update(component)
        return digester.digest()

    @classmethod
    def _build_crypto(cls, secret):
        if len(secret) != 48:
            raise ValueError('Encryption secret must be exactly 48 characters')
        return AES.new(secret[:32], AES.MODE_CBC, secret[32:])

    @classmethod
    def encrypt(cls, message, secret=None):
        """Encrypt a message.  Message value returned is not URL-safe."""
        message = message or ''
        message = '%d.%s' % (len(message), message)
        message += '^' * (16 - len(message) % 16)
        secret = secret or cls._get_encryption_secret()
        return cls._build_crypto(secret).encrypt(message)

    @classmethod
    def encrypt_to_urlsafe_ciphertext(cls, message, secret=None):
        """Convenience wrapper to get URL-safe version of encrytped data."""
        return base64.urlsafe_b64encode(cls.encrypt(message, secret))

    @classmethod
    def decrypt(cls, message, secret=None):
        """Decrypt a message, returning the original plaintext."""
        secret = secret or cls._get_encryption_secret()
        crypto = cls._build_crypto(secret)
        message = crypto.decrypt(message)
        delim_index = message.find('.')
        original_length = int(message[:delim_index])
        return message[delim_index + 1:delim_index + 1 + original_length]

    @classmethod
    def decrypt_from_urlsafe_ciphertext(cls, message, secret=None):
        return cls.decrypt(base64.urlsafe_b64decode(message), secret)


class XsrfTokenManager(object):
    """Provides XSRF protection by managing action/user tokens in memcache."""

    # Max age of the token (4 hours).
    XSRF_TOKEN_AGE_SECS = 60 * 60 * 4

    # Token delimiters.
    DELIMITER_PRIVATE = ':'
    DELIMITER_PUBLIC = '/'

    # Default nickname to use if a user does not have a nickname,
    USER_ID_DEFAULT = 'default'

    @classmethod
    def _create_token(cls, action_id, issued_on):
        """Creates a string representation (digest) of a token."""

        # We have decided to use transient tokens stored in memcache to reduce
        # datastore costs. The token has 4 parts: hash of the actor user id,
        # hash of the action, hash of the time issued and the plain text of time
        # issued.

        # Lookup user id.
        user = users.get_current_user()
        if user:
            user_id = user.user_id()
        else:
            user_id = cls.USER_ID_DEFAULT

        # Round time to seconds.
        issued_on = long(issued_on)

        digest = EncryptionManager.hmac(
            cls.DELIMITER_PRIVATE.join([
                str(user_id), str(action_id), str(issued_on)]))
        token = '%s%s%s' % (
            issued_on, cls.DELIMITER_PUBLIC, base64.urlsafe_b64encode(digest))

        return token

    @classmethod
    def create_xsrf_token(cls, action):
        return cls._create_token(action, time.time())

    @classmethod
    def is_xsrf_token_valid(cls, token, action):
        """Validate a given XSRF token by retrieving it from memcache."""
        try:
            parts = token.split(cls.DELIMITER_PUBLIC)
            if len(parts) != 2:
                return False

            issued_on = long(parts[0])
            age = time.time() - issued_on
            if age > cls.XSRF_TOKEN_AGE_SECS:
                return False

            authentic_token = cls._create_token(action, issued_on)
            if authentic_token == token:
                return True

            return False
        except Exception:  # pylint: disable=broad-except
            return False


def get_external_user_id(app_id, namespace, email):
    """Gets an id for a user that can be transmitted to external systems.

    The returned key is scoped to a particular user within a particular course
    on a particular Course Builder deployment, and is guaranteed to be
    statistically unique within that scope.

    Args:
      app_id: string. Application ID of the CB App Engine deployment.
      namespace: string. Namespace of a single course. May be the empty string.
      email: string. Unvalidated email address for a user.

    Returns:
      String.
    """
    return hmac.new(
        '%s%s%s' % (app_id, namespace, email), digestmod=hashlib.sha256
    ).hexdigest()


def hmac_sha_2_256_transform(privacy_secret, value):
    """HMAC-SHA-2-256 for use as a privacy transformation function."""
    return hmac.new(
        str(privacy_secret), msg=str(value), digestmod=hashlib.sha256
    ).hexdigest()


def hmac_sha_2_256_transform_b64(privacy_secret, value):
    """HMAC-SHA-2-256 for use as a privacy transformation function.

    Operates exactly as hmac_sha_2_256_transform above, but encodes the result
    under base64, rather than as hexadecimal digits.  This provides a
    meaningful space savings, in particular when these values are used as
    entity keys.

    Args:
      privacy_secret: Hash salt value to use when encoding
      value: The string to perform a one-way hash upon.
    Returns:
      A base64'd version of the SHA2-256 one way hash corresponding to 'value'.

    """

    raw_digest = hmac.new(
        str(privacy_secret), msg=str(value), digestmod=hashlib.sha256).digest()
    # Modify standard base64 to use $ and * as the two characters other than
    # A-Z, a-z, 0-9 for the encoding.  These characters are selected because
    # 1) These are URL-safe (do not require encoding in case the returned
    #    value is ever used as a URL GET value)
    # 2) These do not conflict with characters such as '-', '_', ',', '.'
    #    which are often used as separators when combining/splitting values into
    #    packed strings.
    return base64.b64encode(raw_digest, '$*')


def generate_transform_secret_from_xsrf_token(xsrf_token, action):
    """Deterministically generate a secret from an XSRF 'nonce'.

    When multiple data sources are being via the REST API, consumers
    may need to correlate data across the different sources.  To take
    a particular example, the analytics page on the dashboard is one
    such consumer.  This function provides a convenient way to turn an
    opaque, non-forgeable XSRF token internally into an HMAC secret.

    The main point here is that the secret string used for HMAC'ing
    the PII in the data source outputs is
    - Not derived from anything the user may generate, so the user
      cannot manipulate the seed value to experiment to find weaknesses.
    - Not predictable given the information the user has.  (The user does
      not have the encryption key.)  The encryption key is used in preference
      to using the HMAC key twice.

    Args:
        xsrf_token: An XSRF token encoded as usual for use as an
            HTML parameter.
        action: Action expected to be present in the token.
    Returns:
        None if the XSRF token is invalid, or an encryption key if it is.
    """

    if not XsrfTokenManager.is_xsrf_token_valid(xsrf_token, action):
        return None

    # Encrypt the publicly-visible xsrf parameter with our private
    # encryption secret so that we now have a string which is
    # - Entirely deterministic
    # - Not generatable by anyone not in posession of the encryption secret.
    seed_string = EncryptionManager.encrypt(xsrf_token)
    seed = 0
    for c in seed_string:
        seed *= 256
        seed += ord(c)
    r = random.Random(seed)

    # Use the random seed to deterministically generate a secret which
    # will be consistent for identical values of the HMAC token.
    return base64.urlsafe_b64encode(
        ''.join(chr(r.getrandbits(8)) for unused in range(
            int(ENCRYPTION_SECRET_LENGTH * 0.75))))
