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

"""Automation of removal of data upon unregistration of a user."""

__author__ = 'Mike gainer (mgainer@google.com)'

import logging

from common import utils as common_utils
from common import safe_dom
from common import schema_fields
from controllers import sites
from controllers import utils
from mapreduce import context
from models import courses
from models import custom_modules
from models import data_removal as models_data_removal
from models import jobs
from models import models
from modules.admin import admin
from modules.courses import settings
from modules.dashboard import tabs
from modules.data_removal import removal_models

from google.appengine.api import namespace_manager
from google.appengine.ext import db

MODULE_NAME = 'data_removal'

# Names for course-level settings options.
DATA_REMOVAL_SETTINGS_SECTION = 'data_removal'
REMOVAL_POLICY = 'removal_policy'


class DataRemovalPendingException(Exception):
    """Raised when user re-registration is attempted during deletion."""


class DataRemovalPolicyRegistry(object):
    """Registry for various data removal policies.

    Any other modules wishing to implement richer policies than the
    all-or-none options provided by this module may simply register here.
    Registered policies will be selectable on the course settings UI.
    """

    _policies = {}

    @classmethod
    def register(cls, policy):
        if policy.get_name() in cls._policies:
            raise ValueError('Data removal policy %s is already registered' %
                             policy.get_name())
        if not issubclass(policy, AbstractDataRemovalPolicy):
            raise ValueError(
                'Registered type must extend AbstractDataRemovalPolicy')
        cls._policies[policy.get_name()] = policy

    @classmethod
    def get_by_name(cls, name):
        return cls._policies[name]

    @classmethod
    def get_all(cls):
        return cls._policies.itervalues()


class AbstractDataRemovalPolicy(object):
    """Implements policy for removal of data on student unregistration."""

    @classmethod
    def get_name(cls):
        """Short name for storing as settings value.  Not displayed."""
        raise NotImplementedError()

    @classmethod
    def get_description(cls):
        """Brief description of policy; keep under 80 characters."""
        raise NotImplementedError()

    @classmethod
    def prevent_registration(cls, app_context, user_id):
        """Allows policies to prevent re-registration of users during deletion.

        If a data removal policy wishes to prevent re-registration of a user
        to avoid race conditions while deletion is still in progress, this
        function should return a list of SafeDom entities.  These will be
        shown on the user registration page in place of the usual form.

        If registration is permitted, this function should return an empty
        list.

        Args:
          app_context: Standard CB application context object
          user_id: The obfuscated of the user.  This is obtainable via
              common.users.get_current_user().user_id()
        Returns:
          An empty list if registration is to be permitted.  Otherwise, a list
          of content to be shown in lieu of the registration form.
        """
        raise NotImplementedError()

    @classmethod
    def on_user_add(cls, user_id):
        """Notify policy of new user."""
        raise NotImplementedError()

    @classmethod
    def on_user_removal_intent(cls, user_id):
        """Notify policy user unenroll form says user wishes deletion."""
        raise NotImplementedError()

    @classmethod
    def on_user_unenroll(cls, user_id):
        """User is now unenrolled, and deletion can begin.

        This is called back repeatedly from the user lifecycle queue.
        As such, this function must be idempotent.
        """

    @classmethod
    def on_all_data_removed(cls, user_id):
        """Notify policy all data for user has been removed.

        This call is mostly here as a convenience.  Very likely, your removal
        policy will involve some asynchronous processing that is initiated via
        on_user_unenroll().  Having this function as a method on the policy
        allows only policy-related code to add/modify/delete on policy-related
        database entities.  For an example of this, see
        DataRemovalJob.complete(), below.

        Note that this function will very likely be called within a DB
        transaction coordinating the removal of entities related to async
        deletion with entity removal/modification related to retention policy
        lifecycle completion.  You should limit the number of distinct objects
        this function modifies/removes accordingly.

        Args:
          user_id: The obfuscated of the user.  This is obtainable via
              common.users.get_current_user().user_id()

        """
        raise NotImplementedError()


class IndefiniteRetentionPolicy(AbstractDataRemovalPolicy):

    @classmethod
    def get_name(cls):
        return 'indefinite_retention'

    @classmethod
    def get_description(cls):
        return 'No data is removed upon un-registration of user'

    @classmethod
    def prevent_registration(cls, app_context, user_id):
        return []  # Empty list means we permit registration of user.

    @classmethod
    def on_user_add(cls, user_id):
        pass

    @classmethod
    def on_user_removal_intent(cls, user_id):
        pass

    @classmethod
    def on_user_unenroll(cls, user_id):
        pass

    @classmethod
    def on_all_data_removed(cls, user_id):
        pass


class ImmediateRemovalPolicy(AbstractDataRemovalPolicy):

    @classmethod
    def get_name(cls):
        return 'immediate_removal'

    @classmethod
    def get_description(cls):
        return 'Immediate removal of most data; batch removal of event data'

    @classmethod
    def prevent_registration(cls, app_context, user_id):
        if removal_models.ImmediateRemovalState.is_deletion_pending(user_id):
            return [
                safe_dom.Element('p')
                .add_text(
                    # I18N: Shown when a student is attempting to re-enroll in a
                    # course soon after un-enrolling.  It takes up to several
                    # hours to remove their data, and they are prevented from
                    # re-enrolling during that time to prevent problems.
                    app_context.gettext(
                        'You cannot re-register for this course at the '
                        'current time, because deletion of your previous '
                        'data is still in progress.  Please try again in '
                        'in a few hours.'
                    )
                )
            ]
        return []

    @classmethod
    def on_user_add(cls, user_id):
        # NOTE: A sufficiently motivated Student attacker could re-register
        # himself by just POST-ing directly to the student-creation form
        # handler while deletion was still pending.  However, to do that, he
        # would have had to manually construct the registration form - when
        # the form is painted, it calls prevent_registration(), above, and
        # that should suppress the form for well-intentioned Students.
        #
        # If the POST is done maliciously, there is a very real possibility of
        # a race: the batch cleanup of Event data would run up to several
        # hours later, possibly after the re-registered student had completed
        # some assessments.  Having EventEntity items removed would probably
        # have a negligible effect on course-wide statistics, but would
        # definitely show up as missing items on the Gradebook analytics page.
        # Further, the student's scores would have been recorded separately in
        # the new Student record, so that and the event record would be
        # inconsistent.  This situation is hard to achieve for well-behaved
        # users, and only of minor consequence to system correctness, so we
        # accept it.
        removal_models.ImmediateRemovalState.create(user_id)

    @classmethod
    def on_user_removal_intent(cls, user_id):
        # It doesn't look like this is enough to get the work done, and it's
        # not.  Here, we are just recording the user's intention to have
        # their stuff removed.  In theory, we will be called back Very Soon
        # from the user lifecycle notification queue, at which point we will
        # check their deletion-desire status, and start clobbering.
        # That callback is delivered at on_user_unenroll().
        removal_models.ImmediateRemovalState.set_deletion_pending(user_id)

    @classmethod
    def on_user_unenroll(cls, user_id):
        if removal_models.ImmediateRemovalState.is_deletion_pending(user_id):
            # Allow exceptions to propagate out, which will cause the lifecycle
            # queue to do retries.
            cls._remove_indexed_items(user_id)
            cls._initiate_unindexed_deletion(user_id)

    @classmethod
    def _remove_indexed_items(cls, user_id):
        # We expect that there are comparatively few items indexed by user_id
        # or email address.  Further, since we're running from a task queue,
        # we have 10 minutes to get this done.  We could do these deletions in
        # parallel via async callback/follow-up, but the benefit isn't worth
        # the additional complexity.

        # Try to look up student to do removals by email address.  This may
        # not work, in that the Student may already be gone.  If that's the
        # case, though, we would have started the removers that delete by
        # user_id, and have finished with the by-email deletions, so we can
        # trust that if we can't load the Student, we will have already done
        # the by-email deletions on some earlier attempt.
        student = None
        try:
            student = models.Student.get_student_by_user_id(user_id)
        except Exception, ex:  # pylint: disable=broad-except
            logging.error('Failed looking up student by user ID %s', user_id)
            common_utils.log_exception_origin()
            # But don't return -- we still need to do removals based on
            # user_id even though we cannot remove by email address.

        if student and student.email:
            for remover in models_data_removal.Registry.get_email_removers():
                try:
                    remover(student.email)
                except Exception, ex:
                    logging.critical('Failed to wipe out user data via %s',
                                     str(remover))
                    common_utils.log_exception_origin()
                    raise  # Propagate exception so POST returns 500 status.

        # Do removals which depend only on user_id.  Do these last, so that
        # we're not removing stuff that earlier steps might depend on.
        for remover in models_data_removal.Registry.get_user_id_removers():
            try:
                remover(user_id)
            except Exception, ex:
                logging.critical('Failed to wipe out user data via %s',
                                 str(remover))
                common_utils.log_exception_origin()
                raise  # Propagate exception so POST returns 500 status code.

    @classmethod
    def _initiate_unindexed_deletion(cls, user_id):
        # Make a DB entry that will tell the cron job that there is work to do
        # to clean up un-indexed entities for this user.
        class_names = models_data_removal.Registry.get_unindexed_class_names()
        removal_models.BatchRemovalState.create(user_id, class_names)

    @classmethod
    def on_all_data_removed(cls, user_id):
        """Called back from DataRemovalJob started by cron handler when done."""
        removal_models.ImmediateRemovalState.delete_by_user_id(user_id)


class DataRemovalCronHandler(utils.AbstractAllCoursesCronHandler):
    """Batch job (a few times a day) to finish cleanup of un-indexed items."""

    URL = '/cron/data_removal/batch_delete'  # Must match cron.yaml

    @classmethod
    def is_globally_enabled(cls):
        return True

    @classmethod
    def is_enabled_for_course(cls, app_context):
        return True

    def cron_action(self, app_context, global_state):
        pending_work = removal_models.BatchRemovalState.get_all_work()
        entity_classes = models_data_removal.Registry.get_unindexed_classes()
        for name, user_ids in pending_work.iteritems():
            if name not in entity_classes:
                logging.critical(
                    'Resource name "%s" no longer has a registered function '
                    'to permit deletion of user data!', name)
                continue
            job = DataRemovalJob(app_context, entity_classes[name], user_ids)
            if job.is_active():
                job.cancel()
            job.submit()


class DataRemovalJob(jobs.AbstractCountingMapReduceJob):
    """Map/reduce job against a single un-indexed table to delete user data."""

    def __init__(self, app_context, entity_class, user_ids):
        super(DataRemovalJob, self).__init__(app_context)
        self._entity_class = entity_class
        self._entity_class_name = entity_class.__name__
        self._user_ids = user_ids
        self._job_name = 'job-dataremoval-%s-%s' % (
            entity_class.__name__, self._namespace)

    @staticmethod
    def get_description():
        return 'remove items by user_id'

    def entity_class(self):
        return self._entity_class

    def build_additional_mapper_params(self, app_context):
        return {
            'user_ids': self._user_ids,
            'entity_class_name': self._entity_class_name,
        }

    @staticmethod
    def map(item):
        mapper_params = context.get().mapreduce_spec.mapper.params
        user_ids_to_remove = set(mapper_params['user_ids'])
        item_user_ids = set(item.get_user_ids())
        matching = item_user_ids.intersection(user_ids_to_remove)
        if matching:
            item.delete()
            for user_id in matching:
                yield user_id, 1

    @staticmethod
    def complete(kwargs, results):
        """Finalize removal map/reduce batch job.

        This is an interesting situation: simply by getting here, we can
        reasonably assume that we can just treat all provided user_ids as
        having been completed.  This is because a user with no records in the
        entity table being deleted is just as done as a user where we did find
        items to remove.

        Further, since we delete all indexed items prior to starting any bulk
        deletion, we can trust that we shouldn't have any race problems of the
        following form: User unregisters, and then the user hits 'back' and
        does some UI action which would ordinarily add an un-indexed item.
        The handler that adds the unindexed item will need to load the Student
        or similar records, and that record will already be gone.

        Finally, since we prevent users from re-registering while any deletion
        is in progress, we are also certain that we're not removing any new
        items added after the user re-registered.
        """

        entity_class_name = kwargs['mapper_params']['entity_class_name']
        user_ids = kwargs['mapper_params']['user_ids']
        removal_policy = _get_removal_policy()

        # For each completed user, remove the name of the completed entity
        # type from their list of things to do.  If that list is then empty,
        # we are done with the user; call the deletion policy and tell it so.
        items = removal_models.BatchRemovalState.get_by_user_ids(user_ids)
        for item, user_id in zip(items, user_ids):

            if not item:
                # Possibly this is a re-try of a map/reduce batch job that was
                # racing with a previously timed-out item that still had some
                # life left in it.  Either way, the stuff is gone.
                #
                # DO NOT call to the policy to inform it of completion of
                # deletion; that will have been done in the other batch's
                # complete() invocation, and the user may have re-registered
                # since then.
                logging.warning(
                    'Expected to find data-removal item for user %s '
                    'and class %s, but did not...  Odd.', user_id,
                    entity_class_name)
                continue

            if not entity_class_name in item.resource_types:
                # Again, possibly a race with a previously started M/R job...
                logging.warning(
                    'Data-removal item for user %s exists, but class %s '
                    'has already been removed from the to-do list.', user_id,
                    entity_class_name)
                continue

            item.resource_types.remove(entity_class_name)
            if item.resource_types:
                # Other types still have work pending; just save.
                item.put()
            else:
                # That's all, folks!  Tell the policy we're done.
                @db.transactional(xg=True)
                def user_removal_complete(removal_policy, item, user_id):
                    item.delete()
                    removal_policy.on_all_data_removed(user_id)
                user_removal_complete(removal_policy, item, user_id)


def _get_current_context():
    namespace = namespace_manager.get_namespace()
    course_index = sites.get_course_index()
    app_context = course_index.get_app_context_for_namespace(namespace)
    return app_context


def _get_removal_policy(app_context=None):
    if not app_context:
        app_context = _get_current_context()
    policy_setting_schema = _build_removal_policy_schema()
    policy_name = schema_fields.FieldRegistry.get_field_value(
        policy_setting_schema, app_context.get_environ())
    removal_policy = DataRemovalPolicyRegistry.get_by_name(policy_name)
    return removal_policy


def _user_added_callback(user_id, timestamp):
    """Called back from student lifecycle queue when student (re-)enrolls."""
    removal_policy = _get_removal_policy()
    removal_policy.on_user_add(user_id)

def _prevent_registration_hook(app_context, user_id):
    """Removal policy may forbid re-enroll while deletion is pending."""
    removal_policy = _get_removal_policy(app_context)
    return removal_policy.prevent_registration(app_context, user_id)


def _unenroll_get_hook(app_context):
    """Add field to unenroll form offering data removal, if policy supports."""
    removal_policy = _get_removal_policy(app_context)
    if removal_policy == IndefiniteRetentionPolicy:
        return []
    return [
        safe_dom.Element('p')
            .add_child(safe_dom.Element(
                'input', type='checkbox', name='data_removal', value='True')
                .add_text(' ')
                .add_text(
                    # I18N: Shown when a student is unenrolling from a course.
                    # Gives the student the option to have all their data
                    # permanently removed.
                    app_context.gettext(
                        'Remove all my data from the course.  This is cannot '
                        'be un-done.  If this is not checked, you can '
                        're-register in the future, and your course progress '
                        'will be retained.'
                    )
                )
            ),
        ]


def _unenroll_post_hook(student, request):
    """Called back on user unenroll form submit; check if they want deletion."""
    if request.get('data_removal'):
        removal_policy = _get_removal_policy()
        removal_policy.on_user_removal_intent(student.user_id)


def _user_unenroll_callback(user_id, timestamp):
    removal_policy = _get_removal_policy()
    removal_policy.on_user_unenroll(user_id)


def _build_removal_policy_schema():
    select_data = [(policy.get_name(), policy.get_description())
                    for policy in DataRemovalPolicyRegistry.get_all()]
    select_data.sort(key=lambda item: item[0])
    data_removal_policy = schema_fields.SchemaField(
        DATA_REMOVAL_SETTINGS_SECTION + ':' + REMOVAL_POLICY,
        'Removal Policy', 'string',
        optional=True,
        i18n=False,
        select_data=select_data,
        default_value=ImmediateRemovalPolicy.get_name(),
        description='The policy used for removal of data attributable '
        'to a student when the student unregisters from the course.')
    return data_removal_policy


class IsRegisteredForDataRemovalDescriber(
    admin.BaseAdminHandler.AbstractDbTypeDescriber):

    @classmethod
    def title(cls):
        return 'Registered for Data Removal'

    @classmethod
    def describe(cls, entity_class):
        for fn in models_data_removal.Registry.get_user_id_removers():
            if fn.im_self == entity_class:
                return safe_dom.Text('By user_id')
        for fn in models_data_removal.Registry.get_email_removers():
            if fn.im_self == entity_class:
                return safe_dom.Text('By email')
        if (entity_class.kind() in
            models_data_removal.Registry.get_unindexed_classes()):
            return safe_dom.Text('Map/Reduce job')


custom_module = None

def register_module():

    def notify_module_enabled():
        # Settings page: policy for data cleanup on user unenroll.
        course_settings_fields = (
            lambda course: _build_removal_policy_schema(),
            )
        courses.Course.OPTIONS_SCHEMA_PROVIDERS[
            DATA_REMOVAL_SETTINGS_SECTION].extend(course_settings_fields)
        tabs.Registry.register(
            'settings', DATA_REMOVAL_SETTINGS_SECTION, 'Data Removal',
            lambda handler: settings.CourseSettingsHandler.show_settings_tab(
                handler, DATA_REMOVAL_SETTINGS_SECTION))

        # Register available cleanup policies.
        DataRemovalPolicyRegistry.register(IndefiniteRetentionPolicy)
        DataRemovalPolicyRegistry.register(ImmediateRemovalPolicy)

        # We want to be told when a student signs up or re-registers.
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_ADD][MODULE_NAME] = (
                _user_added_callback)
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_REENROLL][MODULE_NAME] = (
                _user_added_callback)
        models.StudentLifecycleObserver.EVENT_CALLBACKS[
            models.StudentLifecycleObserver.EVENT_UNENROLL][MODULE_NAME] = (
                _user_unenroll_callback)

        # Add hooks to enroll/unenroll handlers to modify page behavior.
        utils.RegisterHandler.PREVENT_REGISTRATION_HOOKS.append(
            _prevent_registration_hook)
        utils.StudentUnenrollHandler.GET_HOOKS.append(_unenroll_get_hook)
        utils.StudentUnenrollHandler.POST_HOOKS.append(_unenroll_post_hook)

        admin.BaseAdminHandler.DB_TYPE_DESCRIBERS.append(
            IsRegisteredForDataRemovalDescriber)


    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Data Removal', 'Remove user data on un-registration',
        [(DataRemovalCronHandler.URL, DataRemovalCronHandler)],
        [],
        notify_module_enabled=notify_module_enabled)
    return custom_module
