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

"""Provide the capability for registered students to invite others.

Setup:
    Include the text of the invitation email in course.yaml with the key:

    course:
      invitation_email:
          sender_email: <email_address_in_from_field>
          subject_template: <text_of_the_email>
          body_template: <text_of_the_email>

    The templates can use Jinja includes for the following variables:
        sender_name: The name of the current student, as entered in the
            registration form.
        unsubscribe_url: A URL for the recipient to use to unsubscribe from
            future emails.

    The invitation_email settings in course.yaml can also be edited in the
    Dashboard under Settings > Course Options.
"""


__author__ = 'John Orr (jorr@google.com)'

import logging
import os
import re

import jinja2

import appengine_config
from common import crypto
from common import safe_dom
from common import schema_fields
from common import tags
from controllers import utils
from models import courses
from models import custom_modules
from models import data_removal
from models import models
from models import transforms
from modules.courses import settings
from modules.invitation import messages
from modules.notifications import notifications
from modules.unsubscribe import unsubscribe


# The intent recorded for the emails sent by the notifications module
INVITATION_INTENT = 'course_invitation'
MODULE_NAME = 'invitation'
MODULE_TITLE = 'Invitations'

RESOURCES_PATH = '/modules/invitation/resources'

TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'invitation', 'templates')

INVITATION_EMAIL_KEY = 'invitation_email'
SENDER_EMAIL_KEY = 'sender_email'
SUBJECT_TEMPLATE_KEY = 'subject_template'
BODY_TEMPLATE_KEY = 'body_template'

# In order to prevent spamming, the number of invitations which can be sent per
# user is limited.
MAX_EMAILS = 100


def is_email_valid(email):
    # TODO(jorr): Use google.appengine.api.mail.is_email_valid when Issue 7471
    # is resolved:
    #     https://code.google.com/p/googleappengine/issues/detail?id=7471
    return re.match(
        r'^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,4}$', email, flags=re.IGNORECASE)


class InvitationEmail(object):

    @classmethod
    def is_available(cls, handler):
        env = handler.app_context.get_environ()
        email_env = env['course'].get(INVITATION_EMAIL_KEY, {})
        return (
            email_env.get(SENDER_EMAIL_KEY)
            and email_env.get(SUBJECT_TEMPLATE_KEY)
            and email_env.get(BODY_TEMPLATE_KEY))

    def __init__(self, handler, recipient_email, sender_name):
        self.recipient_email = recipient_email
        env = handler.app_context.get_environ()
        email_env = env['course'].get(INVITATION_EMAIL_KEY)

        self.sender_email = email_env[SENDER_EMAIL_KEY]
        self.subject_template = email_env[SUBJECT_TEMPLATE_KEY]
        self.body_template = email_env[BODY_TEMPLATE_KEY]
        self.email_vars = {
            'sender_name': sender_name,
            'unsubscribe_url': unsubscribe.get_unsubscribe_url(
                handler, recipient_email)
        }

    def _render(self, template, env):
        # Coerce template to unicode in case it is a LazyTranslator.
        template = unicode(template)
        return jinja2.Template(template).render(env)

    @property
    def subject(self):
        return self._render(self.subject_template, self.email_vars)

    @property
    def body(self):
        return self._render(self.body_template, self.email_vars)

    def send(self):
        notifications.Manager.send_async(
            self.recipient_email,
            self.sender_email,
            INVITATION_INTENT,
            self.body,
            self.subject
        )


class InvitationStudentProperty(models.StudentPropertyEntity):
    """Entity to hold the list of people already invited."""

    PROPERTY_NAME = 'invitation-student-property'
    EMAIL_LIST_KEY = 'email_list'

    @classmethod
    def load_or_default(cls, student):
        entity = cls.get(student, cls.PROPERTY_NAME)
        if entity is None:
            entity = cls.create(student, cls.PROPERTY_NAME)
            entity.value = '{}'
        return entity

    def is_in_invited_list(self, email):
        value_dict = transforms.loads(self.value)
        return email in value_dict.get(self.EMAIL_LIST_KEY, [])

    def append_to_invited_list(self, email_list):
        value_dict = transforms.loads(self.value)
        email_set = set(value_dict.get(self.EMAIL_LIST_KEY, []))
        email_set.update(email_list)
        value_dict[self.EMAIL_LIST_KEY] = list(email_set)
        self.value = transforms.dumps(value_dict)

    def invited_list_size(self):
        return len(transforms.loads(self.value))

    def for_export(self, transform_fn):
        """Return a sanitized version of the model, with anonymized data."""

        # Anonymize the email adresses in the email list and drop any
        # additional data in the data value field.

        model = super(InvitationStudentProperty, self).for_export(transform_fn)
        value_dict = transforms.loads(model.value)
        email_list = value_dict.get(self.EMAIL_LIST_KEY, [])
        clean_email_list = [transform_fn(email) for email in email_list]
        model.value = transforms.dumps({self.EMAIL_LIST_KEY: clean_email_list})
        return model


class InvitationHandler(utils.BaseHandler):
    """Renders the student invitation panel."""

    URL = 'modules/invitation'

    def __init__(self):
        super(InvitationHandler, self).__init__()
        self.email_vars = {}

    def render_for_email(self, template):
        return jinja2.Template(template).render(self.email_vars)

    def get(self):
        user = self.personalize_page_and_get_user()
        if user is None:
            self.redirect('/course')
            return

        student = models.Student.get_enrolled_student_by_user(user)
        if student is None:
            self.redirect('/course')
            return

        if not InvitationEmail.is_available(self):
            self.redirect('/course')
            return

        invitation_email = InvitationEmail(self, user.email(), student.name)

        self.template_value['navbar'] = {}
        self.template_value['xsrf_token'] = (
            crypto.XsrfTokenManager.create_xsrf_token(
                InvitationRESTHandler.XSRF_SCOPE))
        self.template_value['subject'] = invitation_email.subject
        self.template_value['body'] = invitation_email.body

        template = self.get_template('invitation.html', [TEMPLATES_DIR])
        self.response.out.write(template.render(self.template_value))


class InvitationRESTHandler(utils.BaseRESTHandler):
    """Custom REST handler for the invitation panel."""

    URL = 'rest/modules/invitation'

    XSRF_SCOPE = 'invitation'

    SCHEMA = {
        'type': 'object',
        'properties': {
            'emailList': {'type': 'string', 'optional': 'true'}
        }
    }

    def before_method(self, verb, path):
        # Handler needs to be locale-aware because the messages must be
        # localized.
        self._old_locale = self.app_context.get_current_locale()
        new_locale = self.get_locale_for(self.request, self.app_context)
        self.app_context.set_current_locale(new_locale)

    def after_method(self, verb, path):
        # Handler needs to be locale-aware because the messages must be
        # localized.
        self.app_context.set_current_locale(self._old_locale)

    def post(self):
        """Handle POST requests."""

        request = transforms.loads(self.request.get('request'))
        if not self.assert_xsrf_token_or_fail(request, self.XSRF_SCOPE, {}):
            return

        user = self.get_user()
        if not user:
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        student = models.Student.get_enrolled_student_by_user(user)
        if not student:
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        if not InvitationEmail.is_available(self):
            transforms.send_json_response(self, 500, 'Unavailable.', {})
            return

        payload_json = request.get('payload')
        payload_dict = transforms.json_to_dict(payload_json, self.SCHEMA)
        email_set = {
            email.strip() for email in payload_dict.get('emailList').split(',')
            if email.strip()}

        if not email_set:
            transforms.send_json_response(
                # I18N: Error indicating no email addresses were submitted.
                self, 400, self.gettext('Error: Empty email list'))
            return

        invitation_data = InvitationStudentProperty.load_or_default(student)

        # Limit the number of emails a user can send, to prevent spamming
        if invitation_data.invited_list_size() + len(email_set) > MAX_EMAILS:
            missing_count = MAX_EMAILS - invitation_data.invited_list_size()
            # I18N: Error indicating that the user cannot add the desired
            # list of additional email addresses to the list of invitations;
            # the total size of the list with the additions would be more
            # than any single user is allowed to send.  No email addresses
            # were added to the list to send, and no further email messages
            # were sent.
            transforms.send_json_response(self, 200, self.gettext(
                'This exceeds your email cap. Number of remaining '
                'invitations: %s. No messages sent.' % missing_count))
            return

        email_messages = []
        for email in email_set:
            if not is_email_valid(email):
                # I18N: Error indicating an email addresses is not well-formed.
                email_messages.append(self.gettext(
                    'Error: Invalid email "%s"' % email))
            elif invitation_data.is_in_invited_list(email):
                # I18N: Error indicating an email addresses is already known.
                email_messages.append(self.gettext(
                    'Error: You have already sent an invitation email to "%s"'
                    % email))
            elif unsubscribe.has_unsubscribed(email):
                # No message to the user, for privacy reasons
                logging.info('Declined to send email to unsubscribed user')
            elif models.Student.is_email_in_use(email):
                # No message to the user, for privacy reasons
                logging.info('Declined to send email to registered user')
            else:
                InvitationEmail(self, email, student.name).send()

        invitation_data.append_to_invited_list(email_set)
        invitation_data.put()

        if email_messages:
            # I18N: Error indicating not all email messages were sent.
            email_messages.insert(0, self.gettext(
                'Not all messages were sent (%s / %s):') % (
                    len(email_set) - len(email_messages), len(email_set)))
            transforms.send_json_response(self, 400, '\n'.join(email_messages))
        else:
            transforms.send_json_response(
                self, 200,
                # I18N: Success message indicating number of emails sent.
                self.gettext('OK, %s messages sent' % len(email_set)))


def get_course_settings_fields():
    enable = schema_fields.SchemaField(
        'course:invitation_email:enabled',
        'Allow Invitation', 'boolean',
        description=messages.ALLOW_INVITATION, extra_schema_dict_values={
            'className': 'invitation-enable inputEx-Field inputEx-CheckBox'},
        optional=True)
    sender_email = schema_fields.SchemaField(
        'course:invitation_email:sender_email',
        'Invitation Origin Email', 'string',
        description='The email address shown as the sender for invitation '
            'emails to this course.',
        extra_schema_dict_values={'className': 'invitation-data inputEx-Field'},
        optional=True, i18n=False)
    subject_template = schema_fields.SchemaField(
        'course:invitation_email:subject_template',
        'Invitation Subject Line', 'string',
        description='The subject line in invitation emails to this course. '
            'Use the string {{sender_name}} to include the name of the student '
            'issuing the invitation in the subject line.',
        extra_schema_dict_values={'className': 'invitation-data inputEx-Field'},
        optional=True)
    body_template = schema_fields.SchemaField(
        'course:invitation_email:body_template',
        'Invitation Body', 'text',
        description=messages.ALLOW_INVITATION,
        extra_schema_dict_values={'className': 'invitation-data inputEx-Field'},
        optional=True)

    return (
        lambda c: enable,
        lambda c: sender_email,
        lambda c: subject_template,
        lambda c: body_template)


def get_student_profile_invitation_link(handler, unused_student, unused_course):
    env = handler.app_context.get_environ()
    email_env = env['course'].get(INVITATION_EMAIL_KEY, {})
    if not email_env.get('enabled'):
        return (None, None)

    # I18N: Title encouraging user to invite friends to join a course
    invitation_title = handler.gettext('Invite Friends')
    if InvitationEmail.is_available(handler):
        invitation_link = safe_dom.A(
                InvitationHandler.URL
                # I18N: Label on control asking user to invite friends to join.
            ).add_text(handler.gettext(
                'Click to send invitations to family and friends'))
    else:
        # I18N: Inviting friends to join a course is not currently enabled.
        invitation_link = safe_dom.Text(handler.gettext(
                'Invitations not currently available'))

    return (
        invitation_title, invitation_link)


def get_student_profile_sub_unsub_link(handler, student, unused_course):
    email = student.email
    is_unsubscribed = unsubscribe.has_unsubscribed(email)

    # I18N: Control allowing user to subscribe/unsubscribe from email invitation
    sub_unsub_title = handler.gettext('Subscribe/Unsubscribe')
    sub_unsub_message = safe_dom.NodeList()

    if is_unsubscribed:
        resubscribe_url = unsubscribe.get_resubscribe_url(handler, email)
        sub_unsub_message.append(safe_dom.Text(
            # I18N: Message - user has unsubscribed from email invitations.
            handler.gettext(
                'You are currently unsubscribed from course-related emails.')))
        sub_unsub_message.append(safe_dom.A(resubscribe_url).add_text(
            # I18N: Control allowing user to re-subscribe to email invitations.
            handler.gettext('Click here to re-subscribe.')))
    else:
        unsubscribe_url = unsubscribe.get_unsubscribe_url(handler, email)
        sub_unsub_message.append(safe_dom.Text(
            # I18N: Text indicating user has opted in to email invitations.
            handler.gettext(
                'You are currently receiving course-related emails. ')))
        sub_unsub_message.append(safe_dom.A(unsubscribe_url).add_text(
            # I18N: Control allowing user to unsubscribe from email invitations.
            handler.gettext('Click here to unsubscribe.')))

    return (
        sub_unsub_title, sub_unsub_message)


custom_module = None


def register_module():
    """Registers this module in the registry."""

    course_settings_fields = get_course_settings_fields()

    def on_module_enabled():
        courses.Course.OPTIONS_SCHEMA_PROVIDERS[
            MODULE_NAME] += course_settings_fields
        courses.Course.OPTIONS_SCHEMA_PROVIDER_TITLES[
            MODULE_NAME] = MODULE_TITLE
        settings.CourseSettingsHandler.register_settings_section(
            MODULE_NAME, title=MODULE_TITLE)
        utils.StudentProfileHandler.EXTRA_STUDENT_DATA_PROVIDERS += [
            get_student_profile_invitation_link,
            get_student_profile_sub_unsub_link]
        settings.CourseSettingsHandler.ADDITIONAL_DIRS.append(
            TEMPLATES_DIR)
        settings.CourseSettingsHandler.EXTRA_JS_FILES.append(
            'invitation_course_settings.js')
        data_removal.Registry.register_indexed_by_user_id_remover(
            InvitationStudentProperty.delete_by_user_id_prefix)

    global_routes = [
        (os.path.join(RESOURCES_PATH, '.*'), tags.ResourcesHandler)]

    namespaced_routes = [
        ('/' + InvitationHandler.URL, InvitationHandler),
        ('/' + InvitationRESTHandler.URL, InvitationRESTHandler)]

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Invitation Page',
        'A page to invite others to register.',
        global_routes, namespaced_routes,
        notify_module_enabled=on_module_enabled)
    return custom_module
