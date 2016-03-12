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

"""Collect sets of students into groups.

Group size is currently limited to 100 students due to various efficiency
concerns.  No student-facing operation loads more than one group, but the
admin page for managing groups necessarily loads all groups, so making more
than a few hundred groups is not advised.  (However, it's expected that this
is going to be self-limiting, in an "if it hurts don't do that" sort of way.)
"""

__author__ = 'Mike Gainer (mgainer@google.com)'

import copy
import cgi
import datetime
import os
import urllib

import appengine_config
from common import crypto
from common import resource
from common import safe_dom
from common import schema_fields
from common import utils as common_utils
from common import users
from controllers import utils
from models import courses
from models import custom_modules
from models import data_sources
from models import entities
from models import model_caching
from models import models
from models import roles
from models import services
from models import transforms
from modules.analytics import gradebook
from modules.analytics import student_aggregate
from modules.courses import availability
from modules.dashboard import dashboard
from modules.i18n_dashboard import i18n_dashboard
from modules.oeditor import oeditor
from modules.student_groups import messages

from google.appengine.ext import db

EDIT_STUDENT_GROUPS_PERMISSION = 'Edit Student Groups'
STUDENT_GROUP_ID_TAG = 'student_group_id'
MODULE_NAME = 'Student Groups'
MODULE_NAME_AS_IDENTIFIER = 'student_groups'
_TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'student_groups', 'templates')
EPOCH = datetime.datetime(1970, 1, 1)

custom_module = None


class EmailToObfuscatedUserId(models.BaseEntity):
    """Egregious hack to obtain N user IDs in O(3) DB round trips."""

    user = db.UserProperty(indexed=False)
    last_modified = db.DateTimeProperty(auto_now=True, indexed=True)

    @classmethod
    def lookup(cls, emails):
        """Looks up user IDs by email.

        Very hacky: In order to get a constant number of round-trips to the DB,
        we save a UserProperty.  On fetch, this gets filled in with the user ID
        matching the user's email (if any).

        Args:
          emails: List of email addresses.
        Returns:
          A map of email -> user_id (or None, if there is no such user)
        """
        emails = set(emails)  # For uniqueness.
        temp_objs = [cls(user=users.User(email)) for email in emails]
        keys = entities.put(temp_objs)
        temp_objs = entities.get(keys)

        ret = {t.user.email(): t.user.user_id() for t in temp_objs}

        # Obfuscate user IDs if we have a users service that supports it.
        users_service = users.UsersServiceManager.get()
        if hasattr(users_service, 'one_way_hash_user_id'):
            for email, user_id in ret.iteritems():
                if user_id:
                    ret[email] = users_service.one_way_hash_user_id(user_id)

        # Drop the rows to save space.  This can be lossy;
        # EmailToObfuscatedUserIdCleanup will remove any items left around due
        # to intermittent failures.  (We can't be transactional - we may have
        # over 25 users per call.)
        entities.delete(temp_objs)
        return ret


class EmailToObfuscatedUserIdCleanup(utils.AbstractAllCoursesCronHandler):
    """Exceptions may lead to items hanging on, so clean them up.

    This is done daily, and only for items that are > 1 day old, so we are
    certain we cannot be clobbering rows that are currently being used,
    but we are well within data-cleanup policy provisions.  Note that
    you might be tempted to just throw an @db.transactional decorator
    on EmailToObfuscatedUserId.lookup(), but that'd work only until we
    hit the cross-group limit (25 items, as of 2016-01-15.)
    """

    URL = '/cron/student_groups/batch_delete'
    MIN_AGE = datetime.timedelta(days=1)

    @classmethod
    def is_globally_enabled(cls):
        return True

    @classmethod
    def is_enabled_for_course(cls, app_context):
        return True

    @classmethod
    def cron_action(cls, app_context, global_state):
        cutoff = datetime.datetime.utcnow() - cls.MIN_AGE
        query = EmailToObfuscatedUserId.all(keys_only=True).filter(
            'last_modified <=', cutoff)
        entities.delete(common_utils.iter_all(query))


class StudentGroupMembership(models.BaseEntity):
    """Binds one email address to a group.

    The rows in this table also determine the list of email addresses
    shown to the administrator modifying group membership.  This is not
    necessarily 100% identical with the list of allowed Student records.

    Here, the issue is that we don't want to treat email as a definitive
    permanent identifier for a user identity.  UID is definitive, but it is
    possible that the same email address gets moved around among Google user
    accounts either due to the same human owning both, or more rarely by the
    same email being re-issued to a different human (by some org other than
    Google, which doesn't, AFAIK).

    On the other side of that argument, the likelihood that email re-binding
    happens is very low for any given email.  (About 4% per year, per Gitkit
    team).  Thus, while we treat email as not definitive, neither do we
    aggressively go polling to continually re-verify email-to-userid binding.
    As a compromise position, we do lazy evaluation in the following two
    instances:
    - When the admin modifies the membership of a group.  At that moment,
      the UIDs currently corresponding to the given email addresses are
      looked up, and work is then done on Student records in terms of those
      UIDs.
    - When a person registers as a Student.  The Student lifecycle queue
      notifies us of signup, and at that time, we look up the membership
      record and bind the user to the group at that time.
    Here, we are presuming that group creation and student registration happen
    within the span of a few weeks, and if a given student isn't able to
    access the course as expected, the admin will have the group relatively
    fresh in their mind.  When the student complains, they will hopefully
    be able to provide an email that actually maps to their account.  The
    admin types that in, hits 'Save', and all is well.

    Technically, we can be lying to the course admin (viewing a list of email
    addresses) under the following circumstance:
    1. Admin adds 'president@whitehouse.gov' to group membership.
    2. User currently assigned email 'president@whitehouse.gov' signs up for
       course, and is bound to that group.
    3. An election happens, and 'president@whitehouse.gov' gets bound to
       a different person and thus a different UID.
    4. That account signs up for the course.  Again, the account is bound
       to the group ID.

    Now we have multiple users assigned to the course under the same email,
    and worse, there is no feasible way to affect the first UID's group
    membership, unless we happen to know another email also bound to that
    first user's UID.  Yucky, but rare, and super hard to manage, without
    all identity providers supporting a notification service when emails
    get bound to different identities.

    Key is email of a potential student.  Note that in this instance, it is
    legitimate to make what nominally looks like PII the key of a group
    leader DB record.  For this application, email address is not PII, since
    it's not part of the data added by a user.  Instead, it's a statement of
    intent by a course administrator to _permit_ that email to be included
    in a group, but it makes no provable declaration that the referenced
    person ever signed up for the course.

    """

    group_id = db.IntegerProperty(indexed=True)

    @classmethod
    def delete_group(cls, group_id):
        cls.set_members(group_id, [])

    @classmethod
    def set_members(cls, group_id, emails_to_assign):
        """Put the given emails into the nominated group.

        Note that due to transaction size constraints, the steps below are not
        100% transactionally secure against all possiblity of error.  If
        multiple admins are manipulating the same group at the same time, it's
        possible to get inconsistencies.  Possible bad effects are:
        - Student assigned to wrong group: If different admins have different
          ideas about the right group for a user, at least one is "right".
          Either way, the group membership behavior is always internally
          consistent from the student's experence, and is trivially fixable
          by any admin trying to address the problem.
        - Student record contains dangling pointer to deleted group.
          Code in this class is aware of that possibility, and it's easily
          handled by treating the dangling reference as being equivalent
          to not being in a group.

        Args:
          group_id: ID of the group we are setting emails for.
          emails_to_assign: List of email addresses to put into the group.
            Note that it is legitimate to make this the empty list -
            see delete_group().
        """
        # Sequence of operation requires six DB round trips:
        # 1: Look up students in group by filtered query.
        # 3: Look up email -> UID (put, get-by-key-list, delete-by-key-list)
        # 1: Look up registered students by UID
        # 1: Delete entries from StudentGroupMembership by filtered query
        # 1: Insert entries to StudentGroupMembership *and* update Student
        #    records.
        #
        # Yes, this code results in a lot of round trips.  Note however that
        # it's a fixed number, and not dependent on the number of users in the
        # group.

        # Get the Students currently in the group.
        students_in_group = list(common_utils.iter_all(
            models.Student.all().filter('group_id =', group_id)))

        # Winnow: Match existing student emails to emails-to-assign, and
        # get rid of matches.  This leaves us only with emails for people
        # not yet in the group, and students leaving the group.
        students_to_remove_from_group = []
        emails_to_assign = set(emails_to_assign)
        for student in students_in_group:
            if not student.email in emails_to_assign:
                student.group_id = None
                students_to_remove_from_group.append(student)
                models.StudentCache.remove(student.user_id)
            elif student.email in emails_to_assign:
                emails_to_assign.remove(student.email)

        # For emails not yet in group, get UIDs, and thence students.
        email_to_user_id = EmailToObfuscatedUserId.lookup(emails_to_assign)
        user_id_to_email = {v: k for k, v in email_to_user_id.iteritems() if v}
        students_to_add_to_group = [
            student for student in models.Student.get(
                [db.Key.from_path(models.Student.kind(), uid)
                 for uid in user_id_to_email])
            if student]

        # For students found by email -> uid -> Student, mark student as being
        # in the group, and remove that email-to-add item.  Note that the
        # email is found by looking up in the uid->email map, not using the
        # email currently in the Student, as that may not match the email
        # entered by the admin -- more than one email can map to same UID.
        for student in students_to_add_to_group:
            student.group_id = group_id
            emails_to_assign.remove(user_id_to_email[student.user_id])
            models.StudentCache.remove(student.user_id)
        emails_to_save = [cls(key_name=email, group_id=group_id)
                          for email in emails_to_assign]

        # DB operations.  Potentially up to
        # 2 * StudentGroupAvailability.MAX_NUM_MEMBERS operations, which is
        # over the max number of group leaders that can be affected within
        # one transaction.
        entities.delete(common_utils.iter_all(cls.all(keys_only=True)))
        entities.put(students_to_remove_from_group + students_to_add_to_group +
                     emails_to_save)

    @classmethod
    def get_emails(cls, group_id):
        query = cls.all().filter('group_id =', group_id)
        ret = [b.key().name() for b in common_utils.iter_all(query)]
        query = models.Student.all().filter('group_id =', group_id)
        ret.extend([s.email for s in common_utils.iter_all(query)])
        return ret

    @classmethod
    def user_added_callback(cls, student, profile):
        """Move group membership definitive answer to Student on registration.

        Called back *within transaction* from StudentProfileDAO when a student
        is being added.  Adds up to one additional group leader to the
        cross-group transaction.

        Since we treat the Student object as definitive for
        group membership when a Student object exists for a user, we need to
        move the group membership transactionally with the creation of the
        Student object.

        Ideally, we'd prefer to register with StudentLifecycleObserver, but
        that entails a non-zero delay (a few seconds typically, but there
        are no hard guarantees).  During that time, the user won't be seen
        with the correct group membership, which may lead to 404s if the
        course is private to non-group students.

        Args:
          student: models.models.Student instance.  Guaranteed non-None.
          profile: models.models.PersonalProfile instance.  Guaranteed non-None.
        """
        binding = cls.get_by_key_name(student.email)
        if binding:
            group_id = binding.group_id
            binding.delete()
        else:
            group_id = None

        # Mark the student as being in the group, or having been determined to
        # not be in any group.  As soon as there is a valid Student record,
        # that record is then definitive, and StudentGroupMembership is
        # advisory.
        student.group_id = group_id

        # Technically unnecessary; the _add_new_student_for_current_user_in_txn
        # will also call student.put(), but belt-and-suspenders against future
        # maintenance changes.  Also, not terribly expensive; happens only
        # once per student.
        student.put()

    @classmethod
    def get_student_group_for_current_user(cls, app_context):
        # Admins never get their view modified by group restrictions.
        if roles.Roles.is_course_admin(app_context):
            return None

        # See if we can work out the student group based only on the user_id.
        user = users.get_current_user()
        if not user:
            return None

        student_group, definitive = cls._get_student_group_by_user_id(
            user.user_id())
        if student_group or definitive:
            return student_group

        # If no group and we're not definitively sure that there can be no
        # group, check to see if current user's email address is bound to a
        # group.  We need to care about this case, since group membership for
        # non-registered people can make the course available.  Thus, if we
        # did not check non-Students, they might well be prevented from
        # becoming Students since the registration page availability is gated
        # on course availability.
        binding = StudentGroupMembership.get_by_key_name(user.email())
        if binding:
            return model_caching.CacheFactory.get_manager_class(
                MODULE_NAME_AS_IDENTIFIER).get(binding.group_id)
        return None

    @classmethod
    def get_student_group_by_user_id(cls, user_id):
        """Find group for a user ID known to be for a registered Student.

        This function is intended for use ONLY in situations where the calling
        code is certain that the given user ID does correspond to a registered
        student.  When this is the case, we do not need to fall back to lookup
        by email.  Intended for use by cron jobs and analytics and other things
        without a current user in session.

        Args:
          user_id: String giving the user ID to check
        Returns:
          StudentGroupDAO or None
        """
        student_group, definitive = cls._get_student_group_by_user_id(user_id)
        return student_group

    @classmethod
    def _get_student_group_by_user_id(cls, user_id):
        """Find the student_group (if any) for a given user ID.

        Args:
          user_id: String giving the user ID for the user in question.
        Returns:
          A 2-tuple:
          - The StudentGroupDTO (cached; 1 hour timeout), or None.
          - A boolean: Is this answer 100% definitive?  We are definitively
            sure when we found a real Student record for this user ID.
            When no Student is found, we may need to check membership
            by email.
        """

        student = models.Student.get_by_user_id(user_id)
        if not student or student.is_transient:
            return None, False

        if not student.group_id:
            return None, True
        student_group = model_caching.CacheFactory.get_manager_class(
            MODULE_NAME_AS_IDENTIFIER).get(student.group_id)
        return student_group, True


class StudentGroupEntity(models.BaseEntity):
    """Overrides for per-group course-level settings.

    See also StudentGroupDTO, StudentGroupDAO - normal Entity behavior.

    Since settings here are applicable to course content, and since we don't
    want to have to put hooks all over the core code to enforce that the
    contents of this object and the course contents (units, lessons,
    questions, whatever) are 100% in sync at all times, this information is
    lazily evaluated.  If there is a dead reference to a now-deleted item,
    that's harmless.  If a new item gets added and its properties are not
    overridden here, that's also fine - the course level settings apply.
    """
    data = db.TextProperty(indexed=False)
    updated_on = db.DateTimeProperty(indexed=True)


def _on_student_group_changed(student_groups):
    if not i18n_dashboard.I18nProgressDeferredUpdater.is_translatable_course():
        return
    key_list = [resource.Key(ResourceHandlerStudentGroup.TYPE, sg.id)
                for sg in student_groups]
    i18n_dashboard.I18nProgressDeferredUpdater.update_resource_list(key_list)


class StudentGroupDTO(object):
    """Convenience accessors for data in Student Group entity."""

    NAME_PROPERTY = 'name'
    DESCRIPTION_PROPERTY = 'description'
    OVERRIDES_PROPERTY = 'overrides'

    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict

    @property
    def name(self):
        return self.dict.get(self.NAME_PROPERTY, '')

    @name.setter
    def name(self, value):
        self.dict[self.NAME_PROPERTY] = value

    @property
    def description(self):
        return self.dict.get(self.DESCRIPTION_PROPERTY, '')

    @description.setter
    def description(self, value):
        self.dict[self.DESCRIPTION_PROPERTY] = value

    def _overrides(self):
        return self.dict.setdefault(self.OVERRIDES_PROPERTY, {})

    def set_override(self, keys, value):
        settings = self._overrides()
        for key in keys[:-1]:
            settings = settings.setdefault(key, {})
        settings[keys[-1]] = value

    def get_override(self, keys, default=None):
        settings = self._overrides()
        for key in keys[:-1]:
            settings = settings.setdefault(key, {})
        return settings.get(keys[-1], default)

    def remove_override(self, keys):
        the_dict = self._overrides()
        settings = [the_dict]
        for key in keys[:-1]:
            the_dict = the_dict.setdefault(key, {})
            settings.append(the_dict)

        leaf_dict = None
        while keys and not leaf_dict:
            leaf_dict = settings.pop()
            leaf_key = keys.pop()
            if leaf_key in leaf_dict:
                del leaf_dict[leaf_key]


class NoOverridesStudentGroup(object):
    """Acts like a group, but with no overrides.

    This is used as a stand-in for an actual group to simplify code.  Rather
    than lots of if/else about whether a student is in a group, if a student
    is not in a group, this "group" which does no overrides is provided.
    """

    def get_override(self, keys, default):
        return default


class StudentGroupDAO(models.BaseJsonDao):
    """Persistence manager for Student Group entitities."""

    DTO = StudentGroupDTO
    ENTITY = StudentGroupEntity
    ENTITY_KEY_TYPE = models.BaseJsonDao.EntityKeyTypeId
    POST_SAVE_HOOKS = [_on_student_group_changed]

    @classmethod
    def before_put(cls, dto, entity):
        entity.updated_on = datetime.datetime.utcnow()

        # Clear cache so that current thread always sees latest changes.
        # Useful for admins, so that they always see up-to-date versions in
        # the dashboard even if the cache is enabled (which it is by default).
        model_caching.CacheFactory.get_cache_instance(
            MODULE_NAME_AS_IDENTIFIER).clear()

    @classmethod
    def create_new(cls, the_dict=None):
        the_dict = the_dict or {}
        new_group = StudentGroupDTO(None, the_dict)
        new_group.id = cls.save(new_group)
        return new_group

    @classmethod
    def delete_by_id(cls, the_id):
        dummy_group = StudentGroupDTO(the_id, {})
        try:
            model_caching.CacheFactory.get_cache_instance(
                MODULE_NAME_AS_IDENTIFIER).clear()
            cls.delete(dummy_group)
        except AttributeError:
            # Internally, delete() first loads the object and then deletes it,
            # which is kinda weird, but hey...  If the object is already gone,
            # we get AttributeError calling .delete() on None, so just swallow
            # the exception here.
            pass


class StudentGroupListHandler(object):

    ACTION = 'edit_student_groups'

    @classmethod
    def _render_student_groups_list(cls, handler, student_groups):
        student_groups_for_template = [
            {
                'name': student_group.name,
                'id': student_group.id,
                'description': student_group.description,
                'delete_url': StudentGroupRestHandler.build_delete_url(
                    handler, student_group.id),
            }
            for student_group in student_groups]
        return safe_dom.Template(
            handler.get_template('student_groups_list.html', [_TEMPLATES_DIR]),
            student_groups=student_groups_for_template,
            edit_action=StudentGroupRestHandler.ACTION)

    @classmethod
    def render_groups_view(cls, handler):
        student_groups = sorted(StudentGroupDAO.get_all(),
                                key=lambda group: group.name)
        actions = []
        if len(student_groups) < StudentGroupRestHandler.MAX_NUM_STUDENT_GROUPS:
            actions.append({
                'id': StudentGroupRestHandler.ACTION,
                'caption': 'Add Group',
                'href': handler.get_action_url(StudentGroupRestHandler.ACTION)})
        sections = [{
            'description': messages.STUDENT_GROUPS_DESCRIPTION,
            'actions': actions,
            'pre': cls._render_student_groups_list(handler, student_groups)
            }]
        template_values = {
            'page_title': handler.format_title(MODULE_NAME),
            'sections': sections,
            }
        return template_values

# ------------------------------------------------------------------------------
# REST handlers: for base settings and for availability page.
#

class StudentGroupRestHandler(utils.BaseRESTHandler):

    ACTION = 'edit_student_group'
    URL = '/rest/edit_student_group'

    # An arbitrary limit, here to prevent users from unintentionally adding
    # so many groups the page won't load in <= 60 seconds, and prevent them
    # from being able to administer groups at all (even to prune old ones).
    MAX_NUM_STUDENT_GROUPS = 100

    @classmethod
    def edit_student_group(cls, handler):
        schema = cls.get_schema()
        key = handler.request.get('key') or None
        if key:
            delete_url = cls.build_delete_url(handler, key)
        else:
            delete_url = None

        template_values = {
            'page_title': handler.format_title('Edit Student Group'),
            'main_content': oeditor.ObjectEditor.get_html_for(
                handler, schema.get_json_schema(), schema.get_schema_dict(),
                key,
                handler.canonicalize_url(cls.URL),
                handler.get_action_url(StudentGroupListHandler.ACTION),
                delete_url=delete_url,
                delete_method='delete',
                additional_dirs=[_TEMPLATES_DIR]),
            }
        return template_values

    @classmethod
    def build_delete_url(cls, handler, key):
        delete_url = '%s?%s' % (
            handler.canonicalize_url(cls.URL),
            urllib.urlencode({
                'key': key,
                'xsrf_token': cgi.escape(
                    handler.create_xsrf_token(cls.ACTION))
                }))
        return delete_url

    @classmethod
    def get_schema(cls):
        ret = schema_fields.FieldRegistry('Student Groups')
        ret.add_property(schema_fields.SchemaField(
            StudentGroupDTO.NAME_PROPERTY, 'Group Name', 'string',
            optional=False, i18n=True))
        ret.add_property(schema_fields.SchemaField(
            StudentGroupDTO.DESCRIPTION_PROPERTY, 'Group Description', 'text',
            optional=True, i18n=True))
        return ret

    def get(self):
        key = self.request.get('key')
        if not roles.Roles.is_user_allowed(self.app_context, custom_module,
                                           EDIT_STUDENT_GROUPS_PERMISSION):
            transforms.send_json_response(self, 401, 'Access denied.')
            return
        if not key or key == 'None':
            name = ''
            description = ''
        else:
            group_id = int(key)
            student_group = StudentGroupDAO.load(group_id)
            if not student_group:
                transforms.send_json_response(self, 404, 'Not found.')
                return
            name = student_group.name
            description = student_group.description
        entity = {
            StudentGroupDTO.NAME_PROPERTY: name,
            StudentGroupDTO.DESCRIPTION_PROPERTY: description,
            }
        transforms.send_json_response(
            self, 200, 'OK.', payload_dict=entity,
            xsrf_token=crypto.XsrfTokenManager.create_xsrf_token(self.ACTION))

    def put(self):
        if not roles.Roles.is_user_allowed(self.app_context, custom_module,
                                           EDIT_STUDENT_GROUPS_PERMISSION):
            transforms.send_json_response(self, 401, 'Access denied.')
            return
        request = transforms.loads(self.request.get('request'))
        key = request.get('key')
        if not self.assert_xsrf_token_or_fail(request, self.ACTION,
                                              {'key': key}):
            return
        payload = transforms.loads(request.get('payload', {}))
        group_name = payload.get(StudentGroupDTO.NAME_PROPERTY, '')
        group_description = payload.get(
            StudentGroupDTO.DESCRIPTION_PROPERTY, '')

        # If we are adding a new group, we need to insert a StudentGroupEntity
        # to the DB so that we can have an ID to associate to the emails.
        if not key or key == 'None':
            if len(StudentGroupDAO.get_all()) >= self.MAX_NUM_STUDENT_GROUPS:
                transforms.send_json_response(
                    self, 403, 'Cannot create more groups; already have %s.' %
                    self.MAX_NUM_STUDENT_GROUPS)
                return

            new_group = StudentGroupDAO.create_new({
                StudentGroupDTO.NAME_PROPERTY: group_name,
                StudentGroupDTO.DESCRIPTION_PROPERTY: group_description,
                })
            group_id = new_group.id
        else:
            try:
                group_id = int(key)
                group = StudentGroupDAO.load(group_id)
                if not group:
                    transforms.send_json_response(self, 404, 'Not found.')
                    return
                group.name = group_name
                group.description = group_description
                StudentGroupDAO.save(group)
            except ValueError:
                transforms.send_json_response(self, 400, 'Malformed key.')
                return
        transforms.send_json_response(self, 200, 'Saved.', {'key': group_id})

    def delete(self):
        if not roles.Roles.is_user_allowed(self.app_context, custom_module,
                                           EDIT_STUDENT_GROUPS_PERMISSION):
            transforms.send_json_response(self, 401, 'Access denied.')
            return
        key = self.request.get('key')
        if not self.assert_xsrf_token_or_fail(self.request, self.ACTION,
                                              {'key': key}):
            return

        try:
            group_id = int(key)
        except ValueError:
            transforms.send_json_response(self, 400, 'Malformed key.')
            return

        StudentGroupDAO.delete_by_id(group_id)
        StudentGroupMembership.delete_group(group_id)
        transforms.send_json_response(self, 200, 'Deleted.')


class StudentGroupAvailabilityRestHandler(utils.BaseRESTHandler):

    ACTION = 'edit_student_group_availability'
    URL = '/rest/edit_student_group_availability'
    _MEMBERS = 'members'
    MAX_NUM_MEMBERS = 100
    _AVAILABILITY_NO_OVERRIDE = 'no_override'
    _AVAILABILITY_NO_OVERRIDE_TITLE = 'No Override'

    _STUDENT_GROUP = 'student_group'
    _STUDENT_GROUP_SETTINGS = 'student_group_settings'
    _ELEMENT_SETTINGS = 'element_settings'
    _COURSE_AVAILABILITY = 'course_availability'
    _DEFAULT_COURSE_AVAILABILITY = 'default_course_availability'
    _DEFAULT_AVAILABILITY = 'default_availability'
    _OVERRIDDEN_AVAILABILITY = 'overridden_availability'

    @classmethod
    def get_form(cls, handler):
        student_groups = StudentGroupDAO.get_all()
        if not student_groups:
            return availability.AvailabilityRESTHandler.get_form(handler)

        schema = cls.get_schema(student_groups)
        return oeditor.ObjectEditor.get_html_for(
            handler, schema.get_json_schema(), schema.get_schema_dict(),
            '', handler.canonicalize_url(cls.URL), '',
            additional_dirs=[_TEMPLATES_DIR, availability.TEMPLATES_DIR],
            extra_js_files=[
                'availability.js',
                'student_group_availability.js'],
            extra_css_files=[
                'availability.css',
                'student_group_availability.css'])

    @classmethod
    def get_schema(cls, student_groups):

        element_settings = schema_fields.FieldRegistry(
            'Element Settings', 'Availability settings for course elements',
            extra_schema_dict_values={'className': 'content-element'})
        element_settings.add_property(schema_fields.SchemaField(
            'type', 'Element Kind', 'string',
            i18n=False, optional=True, editable=False, hidden=True))
        element_settings.add_property(schema_fields.SchemaField(
            'id', 'Element Key', 'string',
            i18n=False, optional=True, editable=False, hidden=True))
        element_settings.add_property(schema_fields.SchemaField(
            'indent', 'Indent', 'boolean',
            i18n=False, optional=True, editable=False, hidden=True))
        element_settings.add_property(schema_fields.SchemaField(
            'name', 'Course Outline', 'string',
            i18n=False, optional=True, editable=False,
            extra_schema_dict_values={'className': 'title'}))
        element_settings.add_property(schema_fields.SchemaField(
            cls._DEFAULT_AVAILABILITY, 'Availability from Course', 'string',
            description=services.help_urls.make_learn_more_message(
                messages.AVAILABILITY_DEFAULT_AVAILABILITY_DESCRIPTION,
                'course:availability:availability'),
            i18n=False, optional=True, editable=False,
            extra_schema_dict_values={'className': 'availability'}))
        element_settings.add_property(schema_fields.SchemaField(
            cls._OVERRIDDEN_AVAILABILITY, 'Availability', 'string',
            description=services.help_urls.make_learn_more_message(
                messages.AVAILABILITY_OVERRIDDEN_AVAILABILITY_DESCRIPTION,
                'course:availability:availability'), i18n=False, optional=True,
            select_data=[
                (cls._AVAILABILITY_NO_OVERRIDE,
                 cls._AVAILABILITY_NO_OVERRIDE_TITLE)] + [
                (a, a.title()) for a in courses.AVAILABILITY_VALUES],
            extra_schema_dict_values={'className': 'availability'}))

        group_settings = schema_fields.FieldRegistry(
            'Student Group Availability',
            extra_schema_dict_values={
                'className': (
                    'inputEx-Group new-form-layout hidden-header '
                    'group-availability availability-manager')})
        group_settings.add_property(schema_fields.SchemaField(
            cls._DEFAULT_COURSE_AVAILABILITY,
            'Course Availability for Non-Grouped Students',
            'string', optional=True, i18n=False, editable=False,
            extra_schema_dict_values={
                'wrapperClassName': ['gcb-default-course-availability '
                                     'inputEx-fieldWrapper']}))
        group_settings.add_property(schema_fields.SchemaField(
            cls._COURSE_AVAILABILITY, 'Course Availability for Group', 'string',
            description=messages.GROUP_COURSE_AVAILABILITY,
            i18n=False, optional=True,
            select_data=[
                (cls._AVAILABILITY_NO_OVERRIDE,
                 cls._AVAILABILITY_NO_OVERRIDE_TITLE)] + [
                (p, p.replace('_', ' ').title())
                for p in courses.COURSE_AVAILABILITY_POLICIES],
            extra_schema_dict_values={
                'wrapperClassName': ['gcb-group-course-availability '
                                     'inputEx-fieldWrapper']}))
        group_settings.add_property(schema_fields.FieldArray(
            cls._ELEMENT_SETTINGS, 'Content Availability',
            item_type=element_settings, optional=True,
            extra_schema_dict_values={'className': 'content-availability'}))
        group_settings.add_property(schema_fields.SchemaField(
            cls._MEMBERS, 'Members', 'text',
            i18n=False, optional=True,
            description=messages.GROUP_MEMBERS_DESCRIPTION))

        ret = availability.AvailabilityRESTHandler.get_schema()
        ret.add_property(schema_fields.SchemaField(
            cls._STUDENT_GROUP, 'Set Availability For', 'string',
            i18n=False, optional=True,
            select_data=[
                ('', 'Course')] + [
                (sg.id, 'Student Group: %s' % sg.name)
                for sg in student_groups]))
        ret.add_sub_registry(
            cls._STUDENT_GROUP_SETTINGS, registry=group_settings)
        return ret

    @classmethod
    def _add_unit(cls, unit, elements, student_group, indent=False):
        overridden_availability = student_group.get_override(
            ['unit', str(unit.unit_id), 'availability'],
            cls._AVAILABILITY_NO_OVERRIDE)
        elements.append({
            'type': 'unit',
            'id': unit.unit_id,
            'indent': indent,
            'name': unit.title,
            cls._DEFAULT_AVAILABILITY: unit.availability.title(),
            cls._OVERRIDDEN_AVAILABILITY: overridden_availability,
            })

    @classmethod
    def _add_lesson(cls, lesson, elements, student_group):
        overridden_availability = student_group.get_override(
            ['lesson', str(lesson.lesson_id), 'availability'],
            cls._AVAILABILITY_NO_OVERRIDE)
        elements.append({
            'type': 'lesson',
            'id': lesson.lesson_id,
            'indent': True,
            'name': lesson.title,
            cls._DEFAULT_AVAILABILITY: lesson.availability.title(),
            cls._OVERRIDDEN_AVAILABILITY: overridden_availability,
            })

    @classmethod
    def _traverse_course(cls, course, student_group):
        elements = []
        for unit in course.get_units():
            if unit.is_assessment() and course.get_parent_unit(unit.unit_id):
                continue
            cls._add_unit(unit, elements, student_group, indent=False)
            if unit.is_unit():
                if unit.pre_assessment:
                    cls._add_unit(course.find_unit_by_id(unit.pre_assessment),
                                  elements, student_group, indent=True)
                for lesson in course.get_lessons(unit.unit_id):
                    cls._add_lesson(lesson, elements, student_group)
                if unit.post_assessment:
                    cls._add_unit(course.find_unit_by_id(unit.post_assessment),
                                  elements, student_group, indent=True)
        return elements

    def get(self):
        student_group_id = self.request.get('key')

        course = self.get_course()
        if not student_group_id or student_group_id == 'None':
            student_group_settings = {
                self._ELEMENT_SETTINGS:
                    self._traverse_course(course, NoOverridesStudentGroup()),
                self._MEMBERS: [],
                }
        else:
            student_group_id = int(student_group_id)
            if not roles.Roles.is_user_allowed(self.app_context, custom_module,
                                               EDIT_STUDENT_GROUPS_PERMISSION):
                transforms.send_json_response(self, 401, 'Access denied.')
                return

            student_group = StudentGroupDAO.load(student_group_id)
            if not student_group:
                transforms.send_json_response(self, 404, 'Not found.')
                return
            student_group_settings = {
                self._ELEMENT_SETTINGS:
                    self._traverse_course(course, student_group),
                'members': '\n'.join(
                    StudentGroupMembership.get_emails(student_group_id)),
                self._DEFAULT_COURSE_AVAILABILITY:
                    course.get_course_availability().title().replace('_', ' '),
                self._COURSE_AVAILABILITY: student_group.get_override(
                    [self._COURSE_AVAILABILITY],
                    self._AVAILABILITY_NO_OVERRIDE),
            }

        entity = availability.AvailabilityRESTHandler.construct_entity(course)
        entity[self._STUDENT_GROUP] = student_group_id
        entity[self._STUDENT_GROUP_SETTINGS] = student_group_settings
        transforms.send_json_response(
            self, 200, 'OK.', payload_dict=entity,
            xsrf_token=crypto.XsrfTokenManager.create_xsrf_token(self.ACTION))

    def put(self):
        request = transforms.loads(self.request.get('request'))
        payload = transforms.loads(request.get('payload', {}))
        student_group_id = payload.get(self._STUDENT_GROUP)

        # If no student group key, we are handling the course-level settings;
        # forward control back to the handler from which we usurped the
        # registered action.
        if not student_group_id or student_group_id is None:
            return availability.AvailabilityRESTHandler.classmethod_put(self)

        # Here, we're doing student groups, so verify that permission.
        if not self.assert_xsrf_token_or_fail(request, self.ACTION, {}):
            return
        if not roles.Roles.is_user_allowed(self.app_context, custom_module,
                                           EDIT_STUDENT_GROUPS_PERMISSION):
            transforms.send_json_response(self, 401, 'Access denied.')
            return

        # Update student group settings in student_group object.
        student_group = StudentGroupDAO.load(student_group_id)
        if not student_group:
            transforms.send_json_response(self, 404, 'Not found.')
            return

        student_group.remove_override([self._COURSE_AVAILABILITY])
        student_group.remove_override(['unit'])
        student_group.remove_override(['lesson'])
        group_settings = payload.get(self._STUDENT_GROUP_SETTINGS)
        for item in group_settings.get(self._ELEMENT_SETTINGS, []):
            if (item[self._OVERRIDDEN_AVAILABILITY] !=
                self._AVAILABILITY_NO_OVERRIDE):
                student_group.set_override(
                    [item['type'], item['id'], 'availability'],
                    item[self._OVERRIDDEN_AVAILABILITY])
        if group_settings.get(self._COURSE_AVAILABILITY):
            student_group.set_override(
                [self._COURSE_AVAILABILITY],
                group_settings[self._COURSE_AVAILABILITY])
        StudentGroupDAO.save(student_group)

        # Update references in join table.
        members_text = payload.get(
            self._STUDENT_GROUP_SETTINGS).get(self._MEMBERS)
        members = common_utils.text_to_list(members_text)
        if len(members) > self.MAX_NUM_MEMBERS:
            transforms.send_json_response(
                self, 400, 'A group may contain at most %d members.' %
                self.MAX_NUM_MEMBERS)
            return
        StudentGroupMembership.set_members(int(student_group_id), members)

        transforms.send_json_response(self, 200, 'Saved')


# ------------------------------------------------------------------------------
# Callbacks
#

def _add_student_group_to_event(source, user, data):
    """Callback from event submission to add student group membership info.

    This is necessary so that when we add overrides to analytic map/reduce
    jobs, we have the student's group ID (if any) available so that we can
    inject it into the map/reduce data flow.
    """
    student_group = StudentGroupMembership.get_student_group_by_user_id(
        user.user_id())
    if student_group:
        data[STUDENT_GROUP_ID_TAG] = student_group.id


def _add_student_group_to_map_result(event):
    """Callback for Gradebook analytic: Add student group ID to map result."""
    payload = transforms.loads(event.data)
    ret = {
        'ts': (event.recorded_on - EPOCH).total_seconds(),
        'id': payload.get(STUDENT_GROUP_ID_TAG, ''),
        }
    return ret


def _add_student_group_to_kwargs(kwargs, event_data_items):
    """Callback for Gradebook analytic: Add student group to reduced output."""
    if not event_data_items:
        return
    event_data_items.sort(key=lambda data_item: data_item['ts'])
    if event_data_items[-1]['id'] is not None:
        kwargs['student_group_id'] = str(event_data_items[-1]['id'])


class StudentGroupFilter(data_sources.AbstractEnumFilter):
    """Makes select form values for choosing student group from data sources."""

    @classmethod
    def get_title(cls):
        return 'Student Group'

    @classmethod
    def get_schema(cls):
        """Add schema entry matching field this filters on."""
        reg = schema_fields.FieldRegistry('student_group')
        reg.add_property(schema_fields.SchemaField(
            'student_group_id', 'Student Group ID', 'string',
            optional=True, i18n=False))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def get_choices(cls):
        student_groups = StudentGroupDAO.get_all()
        student_groups.sort(lambda sg: sg.name)
        if not student_groups:
            return []  # Suppress filter from appearing

        ret = []
        ret.append(data_sources.EnumFilterChoice(
            'All Students', '', selected=True))
        ret.append(data_sources.EnumFilterChoice(
            'Students Not In Groups', 'student_group_id='))
        for student_group in student_groups:
            ret.append(data_sources.EnumFilterChoice(
                'Students in Group: ' + student_group.name,
                'student_group_id=%s' % student_group.id))
        return ret


def _add_student_group_to_profile(handler, app_context, student):
    """Callback for student profile page: Add group name/desc to page HTML."""

    student_group = StudentGroupMembership.get_student_group_by_user_id(
        student.user_id)
    if not student_group:
        return None

    if i18n_dashboard.is_translation_required():
        # Copy to prevent clobbering the base language name/descr in the cache.
        student_group = copy.deepcopy(student_group)
        resource_key = resource.Key(ResourceHandlerStudentGroup.TYPE,
                                    student_group.id)
        i18n_dashboard.translate_dto_list(None, [student_group], [resource_key])

    ret = safe_dom.NodeList()
    # I18N: Name of section title appearing on student profile page.  Title
    # is for a small section giving the name of the sub-group (class, section,
    # or other grouping) of students.
    ret.append(safe_dom.Element('h2', className='gcb-section-division')
               .add_text('Student Group'))
    ret.append(safe_dom.Element('p', id='student-group-name')
               .add_text(student_group.name))
    if student_group.description:
        ret.append(safe_dom.Element('p', id='student-group-description')
                   .add_text(student_group.description))
    return ret


def modify_course_environment(app_context, env):
    """Callback: Inject overrides into course-level environment settings."""
    student_group = StudentGroupMembership.get_student_group_for_current_user(
        app_context)
    if not student_group:
        return

    # Apply overrides as applicable.
    # pylint: disable=protected-access
    course_availability = student_group.get_override(
        [StudentGroupAvailabilityRestHandler._COURSE_AVAILABILITY])
    NO_OVERRIDE = StudentGroupAvailabilityRestHandler._AVAILABILITY_NO_OVERRIDE
    if course_availability and course_availability != NO_OVERRIDE:
        setting = courses.COURSE_AVAILABILITY_POLICIES[course_availability]
        env['course']['now_available'] = setting['now_available']
        env['course']['browsable'] = setting['browsable']
        env['reg_form']['can_register'] = setting['can_register']

    # Users named by email into groups are implicitly also whitelisted into
    # the course.
    env['reg_form']['whitelist'] = users.get_current_user().email()


def modify_unit_and_lesson_attributes(course, units, lessons):
    """Callback from Course to modify a student's view of units, lessons."""

    student_group = StudentGroupMembership.get_student_group_for_current_user(
        course.app_context)
    if not student_group:
        return

    # pylint: disable=protected-access
    NO_OVERRIDE = StudentGroupAvailabilityRestHandler._AVAILABILITY_NO_OVERRIDE
    for unit in units:
        unit_availability = student_group.get_override(
            ['unit', str(unit.unit_id), 'availability'])
        if unit_availability and unit_availability != NO_OVERRIDE:
            unit.availability = unit_availability
    for lesson in lessons:
        lesson_availability = student_group.get_override(
            ['lesson', str(lesson.lesson_id), 'availability'])
        if lesson_availability and lesson_availability != NO_OVERRIDE:
            lesson.availability = lesson_availability


class AddToStudentAggregate(
    student_aggregate.AbstractStudentAggregationComponent):
    """Callback to add student group info to student aggregate data source."""

    SECTION = 'student_group'
    ID_FIELD = 'id'
    NAME_FIELD = 'name'

    @classmethod
    def get_name(cls):
        return MODULE_NAME

    @classmethod
    def get_event_sources_wanted(cls):
        return []

    @classmethod
    def build_static_params(cls, unused_app_context):
        return None

    @classmethod
    def process_event(cls, event, static_params):
        return None

    @classmethod
    def produce_aggregate(cls, course, student, unused_static_params,
                          unused_event_items):
        student_group = StudentGroupMembership.get_student_group_by_user_id(
            student.user_id)
        if not student_group:
            return None

        return {
            cls.SECTION: {
                cls.ID_FIELD: student_group.id,
                cls.NAME_FIELD: student_group.name,
            }
        }

    @classmethod
    def get_schema(cls):
        schema = schema_fields.FieldRegistry(cls.SECTION)
        schema.add_property(schema_fields.SchemaField(
            cls.ID_FIELD, 'Student Group ID', 'integer',
            optional=True,
            description=messages.STUDENT_GROUP_ID_DESCRIPTION))
        # Yes, having the name field reported is technically speaking,
        # denormalized.  However, I don't think it too likely that there will
        # be any other components of student groups needing to be exported via
        # data pump.  Thus, just exporting name directly here, rather than
        # having to have an extra table and join statements.
        schema.add_property(schema_fields.SchemaField(
            cls.NAME_FIELD, 'Student Group Name', 'string',
            description=messages.STUDENT_GROUP_NAME_DESCRIPTION, optional=True))
        return schema


class TranslatableResourceStudentGroups(
    i18n_dashboard.AbstractTranslatableResourceType):
    """Support a section in I18N admin interface for student group."""

    @classmethod
    def get_ordering(cls):
        return i18n_dashboard.TranslatableResourceRegistry.ORDERING_LATE

    @classmethod
    def get_title(cls):
        return MODULE_NAME

    @classmethod
    def get_resources_and_keys(cls, course):
        ret = []
        for student_group in StudentGroupDAO.get_all():
            ret.append(
                (student_group,
                 resource.Key(
                     ResourceHandlerStudentGroup.TYPE,
                     student_group.id, course)))
        ret.sort(key=lambda x: x[0].name)
        return ret


class ResourceHandlerStudentGroup(resource.AbstractResourceHandler):
    """Generic resource accessor for applying translations to student groups."""

    TYPE = 'student_group'

    @classmethod
    def get_resource(cls, course, key):
        return StudentGroupDAO.load(key)

    @classmethod
    def get_resource_title(cls, rsrc):
        return rsrc.name

    @classmethod
    def get_schema(cls, course, key):
        return StudentGroupRestHandler.get_schema()

    @classmethod
    def get_data_dict(cls, course, key):
        return cls.get_resource(course, key).dict

    @classmethod
    def get_view_url(cls, rsrc):
        return None

    @classmethod
    def get_edit_url(cls, key):
        return None


def register_module():
    """Callback for module registration.  Sets up URL routes."""

    global custom_module  # pylint: disable=global-statement
    permissions = [
        roles.Permission(EDIT_STUDENT_GROUPS_PERMISSION,
                         messages.EDIT_STUDENT_GROUPS_PERMISSION_DESCRIPTION),
        ]

    def permissions_callback(unused_application_context):
        return permissions

    def notify_module_enabled():
        """Callback at module-enable time, just after module registration.

        Responsible for registering module's callbacks and other items with
        core and other modules.
        """
        model_caching.CacheFactory.build(
            MODULE_NAME_AS_IDENTIFIER, MODULE_NAME + " Caching",
            messages.ENABLE_GROUP_CACHING,
            max_size_bytes=(
                StudentGroupAvailabilityRestHandler.MAX_NUM_MEMBERS * 1024 * 4),
            ttl_sec=60 * 60, dao_class=StudentGroupDAO)

        # Tell permissioning system about permission for this module.
        roles.Roles.register_permissions(custom_module, permissions_callback)

        # Navigation sub-tab for showing list of student groups, and
        # associated role-level permission.
        dashboard.DashboardHandler.add_sub_nav_mapping(
            'settings', MODULE_NAME_AS_IDENTIFIER, 'Student Groups',
            action=StudentGroupListHandler.ACTION,
            contents=StudentGroupListHandler.render_groups_view)
        dashboard.DashboardHandler.map_get_action_to_permission(
            StudentGroupListHandler.ACTION, custom_module,
            EDIT_STUDENT_GROUPS_PERMISSION)

        # Register action for add/edit/delete of student group.
        dashboard.DashboardHandler.add_custom_get_action(
            StudentGroupRestHandler.ACTION,
            handler=StudentGroupRestHandler.edit_student_group,
            in_action=StudentGroupListHandler.ACTION)
        dashboard.DashboardHandler.map_get_action_to_permission(
            StudentGroupRestHandler.ACTION, custom_module,
            EDIT_STUDENT_GROUPS_PERMISSION)

        # Override existing action for availability.  For UX convenience,
        # we want to have the same page modify overall course availability
        # as well as per-group availability.
        dashboard.DashboardHandler.add_custom_get_action(
            availability.AvailabilityRESTHandler.ACTION,
            StudentGroupAvailabilityRestHandler.get_form, overwrite=True)

        # Register a callback to add the user's student group ID (if any) to
        # recorded events.
        models.EventEntity.EVENT_LISTENERS.append(
            _add_student_group_to_event)

        # Register a component with the student-aggregator data pump source
        # so that student-aggregate records get marked with the group ID
        # for that student.
        student_aggregate.StudentAggregateComponentRegistry.register_component(
            AddToStudentAggregate)

        # Register a callback with models.models.StudentProfileDAO to let us
        # know when a student registers.  This allows us to move the
        # Definitive Truth about group membership to the Student record.
        models.StudentProfileDAO.STUDENT_CREATION_HOOKS.append(
            StudentGroupMembership.user_added_callback)

        # Register a callback with Course so that when anyone asks for the
        # student-facing list of units and lessons we can modify them as
        # appropriate.
        courses.Course.COURSE_ELEMENT_STUDENT_VIEW_HOOKS.append(
            modify_unit_and_lesson_attributes)

        # Register a callback with Course so that when the environment is
        # fetched, we can submit overwrite items.
        courses.Course.COURSE_ENV_POST_COPY_HOOKS.append(
            modify_course_environment)

        # Register student group as a generically handle-able translatable
        # resource.
        resource.Registry.register(ResourceHandlerStudentGroup)

        # Register student group as a translatable item; the title and
        # description can appear on student profile pages.
        i18n_dashboard.TranslatableResourceRegistry.register(
            TranslatableResourceStudentGroups)

        # Register a section on the student profile to add the current
        # student's group - if any.
        utils.StudentProfileHandler.EXTRA_PROFILE_SECTION_PROVIDERS.append(
            _add_student_group_to_profile)

        # Register with gradebook to add student group as a filterable
        # item.
        gradebook.RawAnswersDataSource.FILTERS.append(StudentGroupFilter)

        # Register with generator feeding gradebook to add some handling to
        # the map and reduce steps so we can generate our filter-able data
        # column in the generator's output.
        gradebook.RawAnswersGenerator.register_hook(
            MODULE_NAME,
            _add_student_group_to_map_result,
            _add_student_group_to_kwargs)

        # Add our types to the set of DB tables for download/upload of course.
        courses.ADDITIONAL_ENTITIES_FOR_COURSE_IMPORT.add(StudentGroupEntity)
        courses.ADDITIONAL_ENTITIES_FOR_COURSE_IMPORT.add(
            StudentGroupMembership)

    custom_module = custom_modules.Module(
        MODULE_NAME, 'Define and manage groups of students.',
        global_routes=[
            (EmailToObfuscatedUserIdCleanup.URL,
             EmailToObfuscatedUserIdCleanup),
        ], namespaced_routes=[
            (StudentGroupRestHandler.URL,
             StudentGroupRestHandler),
            (StudentGroupAvailabilityRestHandler.URL,
             StudentGroupAvailabilityRestHandler)
        ],
        notify_module_enabled=notify_module_enabled)
    return custom_module
