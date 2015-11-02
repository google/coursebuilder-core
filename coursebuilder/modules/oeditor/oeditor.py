# Copyright 2012 Google Inc. All Rights Reserved.
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

"""Generic object editor view that uses REST services."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import os
import urllib

import jinja2

import appengine_config
from common import crypto
from common import jinja_utils
from common import schema_fields
from common import tags
from common import users
from controllers import sites
from controllers import utils
from models import custom_modules
from models import entities
from models import models as m_models
from models import roles
from models import transforms

from google.appengine.ext import db

# Folder where Jinja template files are stored
TEMPLATES_DIR = os.path.join(
    appengine_config.BUNDLE_ROOT, 'modules', 'oeditor', 'templates')

# a set of YUI and inputex modules required by the editor
COMMON_REQUIRED_MODULES = [
    'inputex-group', 'inputex-form', 'inputex-jsonschema']

TYPES_TO_MODULES = {
    'select':       'inputex-select',
    'string':       'inputex-string',
    'radio':        'inputex-radio',
    'boolean':      'inputex-checkbox',
    'array':        'inputex-list',
    'html':         'gcb-rte',
    'text':         'inputex-textarea',
    'url':          'inputex-url',
    'uneditable':   'gcb-uneditable',
    'integer':      'inputex-integer',
    'hidden':       'inputex-hidden',
    'file':         'inputex-file',
    'number':       'inputex-number',
    'code':         'gcb-code',
    'datetime':     'gcb-datetime',
    'checkbox-list': 'gcb-checkbox-list',
    'group':        'inputex-group',
}
EXTRA_MODULES = ['array-extras', 'io-upload-iframe']
ALL_MODULES = TYPES_TO_MODULES.values() + EXTRA_MODULES

_DEPRECATED_STATIC_URI = '/modules/oeditor/resources'
_STATIC_URI = '/modules/oeditor/_static'

class ObjectEditor(object):
    """Generic object editor powered by jsonschema."""

    # Modules can add extra script tags to the oeditor page by registering a
    # callback function here. The callback function will receive the app_context
    # as an argument, and should return an iterable of strings, each of which is
    # the URL of a script library.
    EXTRA_SCRIPT_TAG_URLS = []

    @classmethod
    def get_html_for(
        cls, handler, schema_json, annotations, object_key,
        rest_url, exit_url,
        additional_dirs=None,
        auto_return=False,
        delete_url=None, delete_message=None, delete_method='post',
        delete_button_caption='Delete',
        display_types=None,
        exit_button_caption='Close',
        extra_args=None,
        extra_css_files=None,
        extra_js_files=None,
        extra_required_modules=None,
        read_only=False,
        required_modules=None,
        save_button_caption='Save',
        save_method='put'):
        """Creates an HTML code needed to embed and operate this form.

        This method creates an HTML, JS and CSS  required to embed JSON
        schema-based object editor into a view.

        Args:
            handler: a BaseHandler class, which will host this HTML, JS and CSS
            schema_json: a text of JSON schema for the object being edited
            annotations: schema annotations dictionary
            object_key: a key of an object being edited
            rest_url: a REST endpoint for object GET/PUT operation
            exit_url: a URL to go to after the editor form is dismissed
            auto_return: whether to return to the exit_url on successful save
            additional_dirs: list of extra directories to look for
                Jinja template files, e.g., JS or CSS files included by modules.
            delete_url: optional URL for delete operation
            delete_message: string. Optional custom delete confirmation message
            delete_method: optional HTTP method for delete operation
            delete_button_caption: string. A caption for the 'Delete' button
            display_types: list of strings. All schema field types
            exit_button_caption: a caption for the 'Close' button
            extra_args: extra request params passed back in GET and POST
            extra_css_files: list of extra CSS files to be included
            extra_js_files: list of extra JS files to be included
            extra_required_modules: list of strings.
                inputex modules not covered by display_types
            read_only: optional flag; if set, removes Save and Delete operations
            required_modules: list of inputex modules required for this editor
            save_button_caption: a caption for the 'Save' button
            save_method: how the data should be saved to the server (put|upload)

        Returns:
            The HTML, JS and CSS text that will instantiate an object editor.
        """

        if required_modules:
            if not set(required_modules).issubset(set(ALL_MODULES)):
                difference = set(required_modules).difference(set(ALL_MODULES))
                raise ValueError(
                    "Unsupported inputEx modules were required: {}".format(
                        difference))
        elif display_types:
            required_modules = list(set(
                TYPES_TO_MODULES[type_name] for type_name in display_types))
        else:
            required_modules = ALL_MODULES

        if extra_required_modules:
            required_modules += extra_required_modules

        if not delete_message:
            kind = transforms.loads(schema_json).get('description')
            if not kind:
                kind = 'content'
            delete_message = 'Are you sure you want to delete this %s?' % kind

        # construct parameters
        get_url = rest_url
        get_args = {'key': object_key}
        post_url = rest_url
        post_args = {'key': object_key}

        if extra_args:
            get_args.update(extra_args)
            post_args.update(extra_args)

        if read_only:
            post_url = ''
            post_args = ''

        rte_tag_data = []
        for tag, tag_class in tags.get_tag_bindings().items():
            rte_tag_data.append({
                'name': tag,
                'vendor': tag_class.vendor(),
                'label': tag_class.name(),
                'iconUrl': tag_class().get_icon_url()})

        editor_prefs = {
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                EditorPrefsRestHandler.XSRF_TOKEN),
            'location': rest_url,
            'key': object_key,
            'prefs': {}
        }
        user = users.get_current_user()
        if user is not None:
            key_name = EditorPrefsDao.create_key_name(
                user.user_id(), rest_url, object_key)
            editor_prefs_dto = EditorPrefsDao.load(key_name)
            if editor_prefs_dto:
                editor_prefs['prefs'] = editor_prefs_dto.dict

        extra_script_tag_urls = []
        for callback in cls.EXTRA_SCRIPT_TAG_URLS:
            for url in callback():
                extra_script_tag_urls.append(url)

        template_values = {
            'enabled': custom_module.enabled,
            'schema': schema_json,
            'get_url': '%s?%s' % (get_url, urllib.urlencode(get_args, True)),
            'save_url': post_url,
            'save_args': transforms.dumps(post_args),
            'exit_button_caption': exit_button_caption,
            'exit_url': exit_url,
            'required_modules': COMMON_REQUIRED_MODULES + required_modules,
            'extra_css_files': extra_css_files or [],
            'extra_js_files': extra_js_files or [],
            'schema_annotations': [
                (item[0], transforms.dumps(item[1])) for item in annotations],
            'save_method': save_method,
            'auto_return': auto_return,
            'delete_button_caption': delete_button_caption,
            'save_button_caption': save_button_caption,
            'rte_tag_data': transforms.dumps(rte_tag_data),
            'delete_message': delete_message,
            'preview_xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                PreviewHandler.XSRF_TOKEN),
            'editor_prefs': transforms.dumps(editor_prefs),
            'extra_script_tag_urls': extra_script_tag_urls
        }

        if delete_url and not read_only:
            template_values['delete_url'] = delete_url
        if delete_method:
            template_values['delete_method'] = delete_method
        if appengine_config.BUNDLE_LIB_FILES:
            template_values['bundle_lib_files'] = True

        return jinja2.utils.Markup(handler.get_template('oeditor.html', (
            [TEMPLATES_DIR] + (additional_dirs or [])
        )).render(template_values))


class PopupHandler(utils.BaseHandler, utils.ReflectiveRequestHandler):
    """A handler to serve the content of the popup subeditor."""

    default_action = 'custom_tag'
    get_actions = ['edit_custom_tag']
    post_actions = []

    def get_template(self, template_name, dirs):
        """Sets up an environment and Gets jinja template."""
        return jinja_utils.get_template(
            template_name, dirs + [os.path.dirname(__file__)])

    def _validate_schema(self, tag, schema):
        text_field_count = 0
        index = schema_fields.FieldRegistryIndex(schema)
        index.rebuild()
        for name in index.names_in_order:
            if index.find(name).type == 'text':
                text_field_count += 1
        if text_field_count > 1:
            return tag.unavailable_schema(
                'This tag has an invalid schema and cannot be edited. '
                'Only one field of type "text" is allowed.')

        return schema

    def get_edit_custom_tag(self):
        """Return the the page used to edit a custom HTML tag in a popup."""
        tag_name = self.request.get('tag_name')
        tag_bindings = tags.get_tag_bindings()
        tag_class = tag_bindings[tag_name]
        tag = tag_class()
        schema = tag.get_schema(self)
        schema = self._validate_schema(tag, schema)

        template_values = {}
        template_values['form_html'] = ObjectEditor.get_html_for(
            self, schema.get_json_schema(), schema.get_schema_dict(), None,
            None, None,
            required_modules=tag_class.required_modules(),
            extra_js_files=tag_class.extra_js_files(),
            extra_css_files=tag_class.extra_css_files(),
            additional_dirs=tag_class.additional_dirs())
        self.response.out.write(
            self.get_template('popup.html', [TEMPLATES_DIR]
        ).render(template_values))


class ButtonbarCssHandler(utils.BaseHandler):
    def get(self):
        css = []
        for tag_name, tag_class in tags.get_tag_bindings().items():
            css.append(
                '.yui-toolbar-%(tag_name)s > .yui-toolbar-icon {'
                '  background: url(%(icon_url)s) !important;'
                '  background-size: 100%% !important;'
                '  left: 5px;'
                '}' % {
                    'tag_name': tag_name,
                    'icon_url': tag_class().get_icon_url()})
        # Ensure this resource is cacheable.
        sites.set_static_resource_cache_control(self)
        self.response.headers['Content-Type'] = 'text/css'
        self.response.out.write('\n'.join(css))


class PreviewHandler(utils.BaseHandler):
    """Handler for the editor's Preview tab."""

    XSRF_TOKEN = 'oeditor-preview-handler'

    def get(self):
        """Deliver the Preview iframe, without user content."""
        self.render('preview_editor.html', additional_dirs=[TEMPLATES_DIR],
            save_location=False)

    def post(self):
        """Deliver the Preview iframe, with embedded HTML from the editor."""
        # By strict use of HTML verbs, this should be a GET, because it only
        # requests data and has no lasting effects. However the "value"
        # parameter is likely to be too big to be passed in URL query data.

        if not self.assert_xsrf_token_or_fail(self.request, self.XSRF_TOKEN):
            return

        # This should be restricted to the course admin because the transformed
        # data returned may contain questions, etc which are not public.
        if not roles.Roles.is_course_admin(self.app_context):
            self.error(401)
            return

        self.template_value['value'] = self.request.get('value', '')
        self.render('preview_editor.html', additional_dirs=[TEMPLATES_DIR])


class EditorPrefsEntity(entities.BaseEntity):
    """Holds the editor preferences for a user and editor location."""
    # The key is a colon-separated triple user_id:url:key where the editor
    # REST URL is the URL passed to ObjectEditor.get_html_for as rest_url. The
    # data is a JSON object of the following form:
    #     {
    #       "field1": {"editorType: "html", ...},
    #       "field2": {
    #         "subfield1": {"editorType: "html", ...}
    #       }
    #     }
    # The schema of the fields in the data object follows the schema of the
    # OEditor object.
    data = db.TextProperty(indexed=False)

    @classmethod
    def create_key_name(cls, user_id, url, key):
        user_id = str(user_id)
        url = url or ''
        key = key or ''
        assert ':' not in user_id
        assert ':' not in url
        return '%s:%s:%s' % (user_id, url, key)

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        user_id, url, key = db_key.name().split(':', 2)
        return db.Key.from_path(
            cls.kind(), cls.create_key_name(transform_fn(user_id), url, key))


class EditorPrefsDto(object):
    def __init__(self, the_id, data_dict):
        self.id = the_id
        self.dict = data_dict


class EditorPrefsDao(m_models.BaseJsonDao):
    DTO = EditorPrefsDto
    ENTITY = EditorPrefsEntity
    ENTITY_KEY_TYPE = m_models.BaseJsonDao.EntityKeyTypeName

    @classmethod
    def create_key_name(cls, user_id, url, key):
        return cls.ENTITY.create_key_name(user_id, url, key)


class EditorPrefsRestHandler(utils.BaseRESTHandler):
    """Record the editor state for rich text editors."""

    XSRF_TOKEN = 'oeditor-editor-prefs-handler'

    def post(self):
        # Receive a payload of the form:
        #     {
        #       "location": url_for_rest_handler,
        #       "key": the key of the object being edited,
        #       "state": object_holding_editor_state
        #     }

        request = transforms.loads(self.request.get('request'))
        if not self.assert_xsrf_token_or_fail(request, self.XSRF_TOKEN, {}):
            return

        user = self.get_user()
        if user is None:
            self.error(401)
            return

        if not roles.Roles.is_course_admin(self.app_context):
            transforms.send_json_response(self, 401, 'Access denied.', {})
            return

        payload = transforms.loads(request.get('payload'))

        key_name = EditorPrefsDao.create_key_name(
            user.user_id(), payload['location'], payload['key'])
        editor_prefs = EditorPrefsDto(key_name, payload['state'])
        EditorPrefsDao.save(editor_prefs)

        transforms.send_json_response(self, 200, 'Saved.', payload_dict={})


def create_bool_select_annotation(
    keys_list, label, true_label, false_label, class_name=None,
    description=None):
    """Creates inputex annotation to display bool type as a select."""
    properties = {
        'label': label, 'choices': [
            {'value': True, 'label': true_label},
            {'value': False, 'label': false_label}]}
    if class_name:
        properties['className'] = class_name
    if description:
        properties['description'] = description
    return (keys_list, {'type': 'select', '_inputex': properties})


custom_module = None


def register_module():
    """Registers this module in the registry."""

    yui_handlers = [
        ('/static/inputex-3.1.0/(.*)', sites.make_zip_handler(
            os.path.join(
                appengine_config.BUNDLE_ROOT, 'lib/inputex-3.1.0.zip'))),
        ('/static/yui_3.6.0/(.*)', sites.make_zip_handler(
            os.path.join(
                appengine_config.BUNDLE_ROOT, 'lib/yui_3.6.0.zip'))),
        ('/static/2in3/(.*)', sites.make_zip_handler(
            os.path.join(
                appengine_config.BUNDLE_ROOT, 'lib/yui_2in3-2.9.0.zip')))]

    if appengine_config.BUNDLE_LIB_FILES:
        yui_handlers += [
            ('/static/combo/inputex', sites.make_css_combo_zip_handler(
                os.path.join(
                    appengine_config.BUNDLE_ROOT, 'lib/inputex-3.1.0.zip'),
                '/static/inputex-3.1.0/')),
            ('/static/combo/yui', sites.make_css_combo_zip_handler(
                os.path.join(appengine_config.BUNDLE_ROOT, 'lib/yui_3.6.0.zip'),
                '/yui/')),
            ('/static/combo/2in3', sites.make_css_combo_zip_handler(
                os.path.join(
                    appengine_config.BUNDLE_ROOT, 'lib/yui_2in3-2.9.0.zip'),
                '/static/2in3/'))]

    namespaced_routes = [
        ('/oeditorpopup', PopupHandler),
        ('/oeditor/preview', PreviewHandler),
        ('/oeditor/rest/editor_prefs', EditorPrefsRestHandler)]

    global_routes = yui_handlers + [
        ('/modules/oeditor/buttonbar.css', ButtonbarCssHandler),
        (_DEPRECATED_STATIC_URI + r'/.*\.css',
            tags.make_deprecated_resources_handler('css/')),
        (_DEPRECATED_STATIC_URI + r'/.*\.js',
            tags.make_deprecated_resources_handler('js/'))]

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Object Editor',
        'A visual editor for editing various types of objects.',
        global_routes, namespaced_routes)
    return custom_module
