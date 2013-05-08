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

"""Domain objects and constants for use by internal and external clients."""

__author__ = [
    'johncox@google.com (John Cox)',
]

# Identifier for reviews that have been computer-assigned.
ASSIGNER_KIND_AUTO = 'AUTO'
# Identifier for reviews that have been assigned by a human.
ASSIGNER_KIND_HUMAN = 'HUMAN'
ASSIGNER_KINDS = (
    ASSIGNER_KIND_AUTO,
    ASSIGNER_KIND_HUMAN,
)

# Maximum number of ReviewSteps with removed = False, in any REVIEW_STATE, that
# can exist in the backend at a given time.
MAX_UNREMOVED_REVIEW_STEPS = 100

# State of a review that is currently assigned, either by a human or by machine.
REVIEW_STATE_ASSIGNED = 'ASSIGNED'
# State of a review that is complete and may be shown to the reviewee, provided
# the reviewee is themself in a state to see their reviews.
REVIEW_STATE_COMPLETED = 'COMPLETED'
# State of a review that used to be assigned but the assignment has been
# expired. Only machine-assigned reviews can be expired.
REVIEW_STATE_EXPIRED = 'EXPIRED'
REVIEW_STATES = (
    REVIEW_STATE_ASSIGNED,
    REVIEW_STATE_COMPLETED,
    REVIEW_STATE_EXPIRED,
)


class Error(Exception):
    """Base error class."""


class ConstraintError(Error):
    """Raised when data is found indicating a constraint is violated."""


class NotAssignableError(Error):
    """Raised when review assignment is requested but cannot be satisfied."""


class RemovedError(Error):
    """Raised when an op cannot be performed on a step because it is removed."""

    def __init__(self, message, value):
        """Constructs a new RemovedError."""
        super(RemovedError, self).__init__(message)
        self.value = value

    def __str__(self):
        return '%s: removed is %s' % (self.message, self.value)


class ReviewProcessAlreadyStartedError(Error):
    """Raised when someone attempts to start a review process in progress."""


class TransitionError(Error):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, message, before, after):
        """Constructs a new TransitionError.

        Args:
            message: string. Exception message.
            before: string in peer.ReviewStates (though this is unenforced).
                State we attempted to transition from.
            after: string in peer.ReviewStates (though this is unenforced).
                State we attempted to transition to.
        """
        super(TransitionError, self).__init__(message)
        self.after = after
        self.before = before

    def __str__(self):
        return '%s: attempted to transition from %s to %s' % (
            self.message, self.before, self.after)


class Review(object):
    """Domain object for a student work submission."""

    def __init__(self, contents=None, key=None):
        self._contents = contents
        self._key = key

    @property
    def contents(self):
        return self._contents

    @property
    def key(self):
        return self._key


class ReviewStep(object):
    """Domain object for the status of a single review at a point in time."""

    def __init__(
        self, assigner_kind=None, change_date=None, create_date=None, key=None,
        removed=None, review_key=None, review_summary_key=None,
        reviewee_key=None, reviewer_key=None, state=None, submission_key=None,
        unit_id=None):
        self._assigner_kind = assigner_kind
        self._change_date = change_date
        self._create_date = create_date
        self._key = key
        self._removed = removed
        self._review_key = review_key
        self._review_summary_key = review_summary_key
        self._reviewee_key = reviewee_key
        self._reviewer_key = reviewer_key
        self._state = state
        self._submission_key = submission_key
        self._unit_id = unit_id

    @property
    def assigner_kind(self):
        return self._assigner_kind

    @property
    def change_date(self):
        return self._change_date

    @property
    def create_date(self):
        return self._create_date

    @property
    def is_assigned(self):
        """Predicate for whether the step is in REVIEW_STATE_ASSIGNED."""
        return self.state == REVIEW_STATE_ASSIGNED

    @property
    def is_completed(self):
        """Predicate for whether the step is in REVIEW_STATE_COMPLETED."""
        return self.state == REVIEW_STATE_COMPLETED

    @property
    def is_expired(self):
        """Predicate for whether the step is in REVIEW_STATE_EXPIRED."""
        return self.state == REVIEW_STATE_EXPIRED

    @property
    def key(self):
        return self._key

    @property
    def removed(self):
        return self._removed

    @property
    def review_key(self):
        return self._review_key

    @property
    def review_summary_key(self):
        return self._review_summary_key

    @property
    def reviewee_key(self):
        return self._reviewee_key

    @property
    def reviewer_key(self):
        return self._reviewer_key

    @property
    def state(self):
        return self._state

    @property
    def submission_key(self):
        return self._submission_key

    @property
    def unit_id(self):
        return self._unit_id


class ReviewSummary(object):
    """Domain object for review state aggregate entities."""

    def __init__(
        self, assigned_count=None, completed_count=None, change_date=None,
        create_date=None, key=None, reviewee_key=None, submission_key=None,
        unit_id=None):
        self._assigned_count = assigned_count
        self._completed_count = completed_count
        self._change_date = change_date
        self._create_date = create_date
        self._key = key
        self._reviewee_key = reviewee_key
        self._submission_key = submission_key
        self._unit_id = unit_id

    @property
    def assigned_count(self):
        return self._assigned_count

    @property
    def completed_count(self):
        return self._completed_count

    @property
    def change_date(self):
        return self._change_date

    @property
    def create_date(self):
        return self._create_date

    @property
    def key(self):
        return self._key

    @property
    def reviewee_key(self):
        return self._reviewee_key

    @property
    def submission_key(self):
        return self._submission_key

    @property
    def unit_id(self):
        return self._unit_id


class Submission(object):
    """Domain object for a student work submission."""

    def __init__(self, contents=None, key=None):
        self._contents = contents
        self._key = key

    @property
    def contents(self):
        return self._contents

    @property
    def key(self):
        return self._key
