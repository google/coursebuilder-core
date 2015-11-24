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

"""Core custom tags."""

__author__ = 'John Orr (jorr@google.com)'

import os
import re
import urllib
import urlparse
from xml.etree import cElementTree
import markdown

import appengine_config
from common import crypto
from common import jinja_utils
from common import schema_fields
from common import tags
from common import utils as common_utils
from controllers import utils
from models import courses
from models import custom_modules
from models import models
from models import roles
from models import services
from models import transforms
from modules.core_tags import messages
from modules.oeditor import oeditor


_MODULE_PATH = '/modules/core_tags'
_STATIC_URL = _MODULE_PATH + '/_static/'
_OEDITOR_STATIC_URL = '/modules/oeditor/_static/'

_DRIVE_TAG_REFRESH_SCRIPT = _STATIC_URL + 'js/drive_tag_refresh.js'
_IFRAME_RESIZE_SCRIPT = _OEDITOR_STATIC_URL + 'js/resize_iframes.js'
_PARENT_FRAME_SCRIPT = _STATIC_URL + 'js/drive_tag_parent_frame.js'
_SCRIPT_MANAGER_SCRIPT = _STATIC_URL + 'js/drive_tag_script_manager.js'

_TEMPLATES_ABSPATH = os.path.join(os.path.dirname(__file__), 'templates')
_GOOGLE_DRIVE_TAG_PATH = _MODULE_PATH + '/googledrivetag'
_GOOGLE_DRIVE_TAG_RENDERER_PATH = _MODULE_PATH + '/googledrivetagrenderer'


def _escape_url(url, force_https=True):
    """Escapes/quotes url parts to sane user input."""
    scheme, netloc, path, query, unused_fragment = urlparse.urlsplit(url)
    if force_https:
        scheme = 'https'
    path = urllib.quote(path)
    query = urllib.quote_plus(query, '=?&;')
    return urlparse.urlunsplit((scheme, netloc, path, query, unused_fragment))


def _replace_url_query(url, new_query):
    """Replaces the query part of a URL with a new one."""
    scheme, netloc, path, _, fragment = urlparse.urlsplit(url)
    return urlparse.urlunsplit((scheme, netloc, path, new_query, fragment))


class _Runtime(object):
    """Derives runtime configuration state from CB application context."""

    def __init__(self, app_context):
        self._app_context = app_context
        self._environ = self._app_context.get_environ()

    def can_edit(self):
        return roles.Roles.is_course_admin(self._app_context)

    def courses_can_use_google_apis(self):
        return courses.COURSES_CAN_USE_GOOGLE_APIS.value

    def configured(self):
        return (
            self.courses_can_use_google_apis() and
            bool(self.get_api_key()) and
            bool(self.get_client_id()))

    def get_api_key(self):
        course, google, api_key = courses.CONFIG_KEY_GOOGLE_API_KEY.split(':')
        return self._environ.get(course, {}).get(google, {}).get(api_key, '')

    def get_client_id(self):
        course, google, client_id = courses.CONFIG_KEY_GOOGLE_CLIENT_ID.split(
            ':')
        return self._environ.get(
            course, {}
        ).get(
            google, {}
        ).get(
            client_id, '')

    def get_slug(self):
        return self._app_context.get_slug()


class CoreTag(tags.BaseTag):
    """All core custom tags derive from this class."""

    @classmethod
    def vendor(cls):
        return 'gcb'

    @classmethod
    def create_icon_url(cls, name):
        """Creates a URL for an icon with a specific name."""
        return os.path.join(_STATIC_URL, 'images', name)


class GoogleDoc(CoreTag):
    """Custom tag for a Google Doc."""

    @classmethod
    def name(cls):
        return 'Google Doc'

    def render(self, node, unused_handler):
        height = node.attrib.get('height') or '300'
        link = node.attrib.get('link')
        url = _escape_url(_replace_url_query(link, 'embedded=true'))
        iframe = cElementTree.XML("""
<iframe class="google-doc" title="Google Doc" type="text/html" frameborder="0">
</iframe>""")
        iframe.set('src', url)
        iframe.set('style', 'width: %spx; height: %spx' % (700, height))
        return iframe

    def get_icon_url(self):
        return self.create_icon_url('docs.png')

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(GoogleDoc.name())
        reg.add_property(
            # To get this value, users do File > Publish to the web..., click
            # 'Start publishing', and then copy and paste the Document link.
            # Changes to the publication status of a document or to its
            # contents do not appear instantly.
            schema_fields.SchemaField(
                'link', 'Document Link', 'string',
                description=messages.DOCUMENT_LINK_DESCRIPTION))
        reg.add_property(
            schema_fields.SchemaField(
                'height', 'Height', 'string', i18n=False,
                optional=True,
                extra_schema_dict_values={'value': '300'},
                description=messages.DOCUMENT_HEIGHT_DESCRIPTION))
        return reg


class GoogleDrive(CoreTag, tags.ContextAwareTag):
    """Custom tag for Google Drive items."""

    CONTENT_CHUNK_TYPE = 'google-drive'

    @classmethod
    def additional_dirs(cls):
        return [_TEMPLATES_ABSPATH]

    @classmethod
    def extra_css_files(cls):
        return ['google_drive_tag.css']

    @classmethod
    def extra_js_files(cls):
        return ['drive_tag_child_frame.js', 'google_drive_tag_lightbox.js']

    @classmethod
    def name(cls):
        return 'Google Drive'

    @classmethod
    def on_register(cls):
        oeditor.ObjectEditor.EXTRA_SCRIPT_TAG_URLS.append(
            cls._oeditor_extra_script_tags_urls)

    @classmethod
    def on_unregister(cls):
        oeditor.ObjectEditor.EXTRA_SCRIPT_TAG_URLS.remove(
            cls._oeditor_extra_script_tags_urls)

    @classmethod
    def _get_tag_renderer_url(cls, slug, type_id, resource_id):
        args = urllib.urlencode(
            {'type_id': type_id, 'resource_id': resource_id})
        slug = '' if slug == '/' else slug  # Courses may be at / or /slug.
        return '%s%s?%s' % (slug, _GOOGLE_DRIVE_TAG_RENDERER_PATH, args)

    @classmethod
    def _oeditor_extra_script_tags_urls(cls):
        script_urls = []
        if courses.COURSES_CAN_USE_GOOGLE_APIS.value:
            # Order matters here because scripts are inserted in the order they
            # are found in this list, and later ones may refer to symbols from
            # earlier ones.
            script_urls.append(_SCRIPT_MANAGER_SCRIPT)
            script_urls.append(_PARENT_FRAME_SCRIPT)
        return script_urls

    def get_icon_url(self):
        return self.create_icon_url('drive.png')

    def get_schema(self, handler):
        api_key = None
        client_id = None
        if handler:
            runtime = _Runtime(handler.app_context)
            if not runtime.configured():
                return self.unavailable_schema(
                    services.help_urls.make_learn_more_message(
                        messages.GOOGLE_DRIVE_UNAVAILABLE,
                        'core_tags:google_drive:unavailable'))

            api_key = runtime.get_api_key()
            client_id = runtime.get_client_id()

        reg = schema_fields.FieldRegistry(GoogleDrive.name())
        reg.add_property(
            schema_fields.SchemaField(
                'document-id', 'Document ID', 'string',
                description=messages.DOCUMENT_ID_DESCRIPTION,
                extra_schema_dict_values={
                    'api-key': api_key,
                    'client-id': client_id,
                    'type-id': self.CONTENT_CHUNK_TYPE,
                    'xsrf-token': GoogleDriveRESTHandler.get_xsrf_token(),
                }, i18n=False))

        return reg

    def render(self, node, context):
        runtime = _Runtime(context.handler.app_context)
        resource_id = node.attrib.get('document-id')
        src = self._get_tag_renderer_url(
            runtime.get_slug(), self.CONTENT_CHUNK_TYPE, resource_id)

        tag = cElementTree.Element('div')
        tag.set('class', 'google-drive google-drive-container')

        if runtime.can_edit():
            controls = cElementTree.Element('div')
            controls.set('class', 'google-drive google-drive-controls')
            controls.set('data-api-key', runtime.get_api_key())
            controls.set('data-client-id', runtime.get_client_id())
            controls.set('data-document-id', resource_id)
            controls.set(
                'data-xsrf-token', GoogleDriveRESTHandler.get_xsrf_token())
            tag.append(controls)

        iframe = cElementTree.Element('iframe')
        iframe.set(
            'class',
            'google-drive google-drive-content-iframe gcb-needs-resizing')
        iframe.set('frameborder', '0')
        iframe.set('scrolling', 'no')
        iframe.set('src', src)
        iframe.set('title', 'Google Drive')
        iframe.set('width', '100%')
        tag.append(iframe)

        return tag

    def rollup_header_footer(self, context):
        runtime = _Runtime(context.handler.app_context)
        can_edit = runtime.can_edit()
        srcs = [_IFRAME_RESIZE_SCRIPT]

        if can_edit:  # Harmless but wasteful to give to non-admins.
            srcs = [_SCRIPT_MANAGER_SCRIPT] + srcs

        header = cElementTree.Element('div')

        for src in srcs:
            script = cElementTree.Element('script')
            script.set('src', src)
            header.append(script)

        # Put in footer so other scripts will already be loaded when our main
        # fires. Give script to admins only (though note that even if non-admins
        # grab the script we won't give them the XSRF tokens they need to issue
        # CB AJAX ops).

        footer = cElementTree.Element('div')

        if can_edit:
            script = cElementTree.Element('script')
            script.set('src', _DRIVE_TAG_REFRESH_SCRIPT)
            footer.append(script)

        return (header, footer)


class GoogleDriveRESTHandler(utils.BaseRESTHandler):

    _XSRF_TOKEN_NAME = 'modules-core-tags-google-drive'
    XSRF_TOKEN_REQUEST_KEY = 'xsrf_token'

    @classmethod
    def get_xsrf_token(cls):
        return crypto.XsrfTokenManager.create_xsrf_token(cls._XSRF_TOKEN_NAME)

    def put(self):
        if not courses.COURSES_CAN_USE_GOOGLE_APIS.value:
            self.error(404)
            return

        request = transforms.loads(self.request.get('request', ''))

        if not self.assert_xsrf_token_or_fail(
                request, self._XSRF_TOKEN_NAME, {}):
            return

        contents = request.get('contents')
        document_id = request.get('document_id')
        type_id = request.get('type_id')

        if not (contents and document_id):
            transforms.send_json_response(
                self, 400, 'Save failed; no Google Drive item chosen.')
            return

        if not type_id:
            transforms.send_json_response(
                self, 400, 'Save failed; type_id not set')
            return

        key = None
        try:
            key = self._save_content_chunk(contents, type_id, document_id)
        except Exception, e:  # On purpose. pylint: disable=broad-except
            transforms.send_json_response(
                self, 500, 'Error when saving: %s' % e)
            return

        transforms.send_json_response(
            self, 200, 'Success.', payload_dict={'key': str(key)})

    def _save_content_chunk(self, contents, type_id, resource_id):
        key = None
        uid = models.ContentChunkDAO.make_uid(type_id, resource_id)
        matches = models.ContentChunkDAO.get_by_uid(uid)

        if not matches:
            key = models.ContentChunkDAO.save(models.ContentChunkDTO({
                'content_type': 'text/html',
                'contents': contents,
                'resource_id': resource_id,
                'type_id': type_id,
            }))
        else:
            # There is a data race in the DAO -- it's possible to create two
            # entries at the same time with the same UID. If that happened,
            # use the first one saved.
            dto = matches[0]
            dto.contents = contents
            dto.content_type = 'text/html'
            key = models.ContentChunkDAO.save(dto)

        return key


class GoogleDriveTagRenderer(utils.BaseHandler):

    def get(self):
        if not courses.COURSES_CAN_USE_GOOGLE_APIS.value:
            self.error(404)
            return

        resource_id = self.request.get('resource_id')
        type_id = self.request.get('type_id')

        if not (resource_id and type_id):
            self._handle_error(400, 'Bad request')
            return

        matches = models.ContentChunkDAO.get_by_uid(
            models.ContentChunkDAO.make_uid(type_id, resource_id))

        if not matches:
            self._handle_error(404, 'Content chunk not found')
            return

        # There is a data race in the DAO -- it's possible to create two entries
        # at the same time with the same UID. If that happened, use the first
        # one saved.
        chunk = matches[0]

        template = jinja_utils.get_template(
            'drive_item.html', [_TEMPLATES_ABSPATH])
        self.response.out.write(template.render({'contents': chunk.contents}))

    def _handle_error(self, code, message):
        template = jinja_utils.get_template(
            'drive_error.html', [_TEMPLATES_ABSPATH])
        self.error(code)
        self.response.out.write(template.render({
            'code': code,
            'message': message,
        }))


class GoogleSpreadsheet(CoreTag):
    """Custom tag for a Google Spreadsheet."""

    @classmethod
    def name(cls):
        return 'Google Spreadsheet'

    def render(self, node, unused_handler):
        height = node.attrib.get('height') or '300'
        link = node.attrib.get('link')
        url = _escape_url('%s&amp;chrome=false' % link.split('&output')[0])
        iframe = cElementTree.XML("""
<iframe class="google-spreadsheet" title="Google Spreadsheet" type="text/html"
    frameborder="0">
</iframe>""")
        iframe.set('src', url)
        iframe.set('style', 'width: %spx; height: %spx' % (700, height))
        return iframe

    def get_icon_url(self):
        return self.create_icon_url('spreadsheets.png')

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(GoogleSpreadsheet.name())
        reg.add_property(
            # To get this value, users do File > Publish to the web..., click
            # 'Start publishing', and then copy and paste the link above 'Copy
            # and paste the link above'. Changes to the publication status of a
            # document or to its contents do not appear instantly.
            schema_fields.SchemaField(
                'link', 'Link', 'string',
                description=messages.GOOGLE_SPREADSHEET_LINK_DESCRIPTION))
        reg.add_property(
            schema_fields.SchemaField(
                'height', 'Height', 'string',
                description=messages.GOOGLE_SPREADSHEET_HEIGHT_DESCRIPTION,
                extra_schema_dict_values={'value': '300'},
                i18n=False, optional=True))
        return reg


class YouTube(CoreTag):

    @classmethod
    def name(cls):
        return 'YouTube Video'

    def render(self, node, handler):
        video_id = node.attrib.get('videoid')
        if handler.can_record_student_events():
            return self._render_with_tracking(video_id)
        else:
            return self._render_no_tracking(video_id)

    def _render_no_tracking(self, video_id):
        """Embed video without event tracking support."""
        you_tube_url = (
            'https://www.youtube.com/embed/%s'
            '?feature=player_embedded&amp;rel=0') % video_id
        iframe = cElementTree.XML("""
<div class="gcb-video-container">
  <iframe class="youtube-player" title="YouTube Video Player"
    type="text/html" frameborder="0" allowfullscreen="allowfullscreen">
  </iframe>
</div>""")
        iframe[0].set('src', you_tube_url)
        return iframe

    def _render_with_tracking(self, video_id):
        """Embed video and enable event tracking."""
        video_id = jinja_utils.js_string_raw(video_id)
        uid = common_utils.generate_instance_id()
        dom = cElementTree.XML("""
<p>
    <script></script>
    <script></script>
</p>""")
        dom.attrib['id'] = uid
        dom[0].attrib['src'] = os.path.join(
            _STATIC_URL, 'js', 'youtube_video.js')
        dom[1].text = 'gcbTagYoutubeEnqueueVideo("%s", "%s");' % (video_id, uid)
        return dom

    def get_icon_url(self):
        return self.create_icon_url('youtube.png')

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(YouTube.name())
        reg.add_property(schema_fields.SchemaField(
            'videoid', 'Video ID', 'string',
            description=messages.VIDEO_ID_DESCRIPTION))
        return reg


class Html5Video(CoreTag):

    @classmethod
    def name(cls):
        return 'HTML5 Video'

    def render(self, node, handler):
        if handler.can_record_student_events():
            tracking_text = (
                '<script src="' + os.path.join(
                    _STATIC_URL, 'js', 'html5_video.js') + '">' +
                '</script>' +
                '<script>' +
                '  gcbTagHtml5TrackVideo("%s");' % (
                    jinja_utils.js_string_raw(node.attrib.get('instanceid'))) +
                '</script>')
        else:
            tracking_text = ''
        video_text = (
            '<div>' +
            '  <video></video>'
            '%s' % tracking_text +
            '</div>')
        video = cElementTree.XML(video_text)
        video[0].set('id', node.attrib.get('instanceid'))
        video[0].set('src', node.attrib.get('url'))
        if node.attrib.get('width'):
            video[0].set('width', node.attrib.get('width'))
        if node.attrib.get('height'):
            video[0].set('height', node.attrib.get('height'))
        video[0].set('controls', 'true')
        return video

    def get_icon_url(self):
        return self.create_icon_url('html5-badge-h-solo.png')

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(Html5Video.name())
        reg.add_property(
            schema_fields.SchemaField(
                'url', 'Video URL', 'url',
                description=messages.HTML5_VIDEO_URL_DESCRIPTION,
                optional=False))
        reg.add_property(schema_fields.SchemaField(
            'width', 'Width', 'integer',
            description=messages.HTML5_VIDEO_WIDTH_DESCRIPTION,
            optional=True))
        reg.add_property(schema_fields.SchemaField(
            'height', 'Height', 'integer',
            description=messages.HTML5_VIDEO_HEIGHT_DESCRIPTION,
            optional=True))
        return reg


class GoogleGroup(CoreTag):

    @classmethod
    def name(cls):
        return 'Google Group'

    def render(self, node, handler):
        # Note: in Firefox, this component requires a full hostname to work.
        # If you are working in the development environment and are accessing
        # this component at localhost, please replace 'localhost' with
        # '127.0.0.1' instead.
        _, netloc, _, _, _ = urlparse.urlsplit(handler.request.uri)

        parent_url_suffix = ''
        if (appengine_config.PRODUCTION_MODE or
            not netloc.startswith('localhost')):
            parent_url_suffix = (
                '?parenturl=%s' % urllib.quote(handler.request.uri, safe=''))

        group_name = node.attrib.get('group')
        category_name = node.attrib.get('category')
        embedded_forum_url = (
            'https://groups.google.com/forum/embed/%s#!categories/%s/%s' % (
                parent_url_suffix,
                urllib.quote(group_name),
                urllib.quote(category_name)
            ))
        iframe = cElementTree.XML("""
<p>
  <iframe class="forum-embed" title="Google Group Embed"
    type="text/html" width="700" height="300" frameborder="0">
  </iframe>
</p>""")
        iframe[0].set('src', embedded_forum_url)
        return iframe

    def get_icon_url(self):
        return self.create_icon_url('forumembed.png')

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(GoogleGroup.name())
        reg.add_property(schema_fields.SchemaField(
            'group', 'Group Name', 'string', i18n=False,
            description=services.help_urls.make_learn_more_message(
                messages.RTE_GOOGLE_GROUP_GROUP_NAME,
                'core_tags:google_group:name')))
        reg.add_property(schema_fields.SchemaField(
            'category', 'Category Name', 'string', optional=True, i18n=False,
            description=messages.RTE_GOOGLE_GROUP_CATEGORY_NAME))
        return reg


class IFrame(CoreTag):

    def render(self, node, unused_handler):
        src = node.attrib.get('src')
        title = node.attrib.get('title')
        height = node.attrib.get('height') or '400'
        width = node.attrib.get('width') or '650'

        iframe = cElementTree.XML(
            '<iframe style="border: 0;"></iframe>'
        )

        iframe.set('src', _escape_url(src, force_https=False))
        iframe.set('title', title)
        iframe.set('width', width)
        iframe.set('height', height)
        return iframe

    def get_icon_url(self):
        return self.create_icon_url('iframe.png')

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(IFrame.name())
        reg.add_property(schema_fields.SchemaField(
            'src', 'Embed URL', 'string',
            description=messages.RTE_IFRAME_EMBED_URL,
            extra_schema_dict_values={'_type': 'url', 'showMsg': True}))
        reg.add_property(schema_fields.SchemaField(
            'title', 'Title', 'string', description=messages.RTE_IFRAME_TITLE))
        reg.add_property(schema_fields.SchemaField(
            'height', 'Height', 'string', i18n=False, optional=True,
            extra_schema_dict_values={'value': '400'},
            description=messages.RTE_IFRAME_HEIGHT))
        reg.add_property(schema_fields.SchemaField(
            'width', 'Width', 'string', i18n=False, optional=True,
            extra_schema_dict_values={'value': '650'},
            description=messages.RTE_IFRAME_WIDTH))
        return reg


class Include(CoreTag):

    @classmethod
    def name(cls):
        return 'HTML Asset'

    def render(self, node, handler):
        template_path = re.sub('^/+', '', node.attrib.get('path'))
        base_path = os.path.dirname(template_path)
        base_file = os.path.basename(template_path)
        handler.init_template_values(handler.app_context.get_environ())
        handler.template_value['base_path'] = base_path
        html_text = handler.render_template_to_html(
            handler.template_value, base_file,
            additional_dirs=[
                os.path.join(appengine_config.BUNDLE_ROOT, 'views'),
                appengine_config.BUNDLE_ROOT,
                os.path.join(appengine_config.BUNDLE_ROOT, base_path),
            ])
        return tags.html_string_to_element_tree(html_text)

    def get_icon_url(self):
        return self.create_icon_url('include.png')

    def get_schema(self, handler):
        expected_prefix = os.path.join(appengine_config.BUNDLE_ROOT,
                                       'assets/html')

        select_data = []
        if handler:
            all_files = handler.app_context.fs.list(expected_prefix,
                                                    include_inherited=True)
            for name in all_files:
                if name.startswith(expected_prefix):
                    name = name.replace(appengine_config.BUNDLE_ROOT, '')
                    select_data.append(
                        (name, name.replace('/assets/html/', '')))

        reg = schema_fields.FieldRegistry(Include.name())
        reg.add_property(schema_fields.SchemaField(
            'path', 'File Path', 'string', optional=False,
            select_data=select_data,
            description=messages.HTML_ASSET_FILE_PATH_DESCRIPTION))
        return reg


class Markdown(tags.ContextAwareTag, CoreTag):

    @classmethod
    def name(cls):
        return 'Markdown'

    @classmethod
    def required_modules(cls):
        return super(Markdown, cls).required_modules() + ['gcb-code']

    @classmethod
    def additional_dirs(cls):
        return [os.path.join(
            appengine_config.BUNDLE_ROOT, 'modules', 'core_tags', 'resources')]

    def get_icon_url(self):
        return self.create_icon_url('markdown.png')

    def render(self, node, context):
        # The markdown is "text" type in the schema and so is presented in the
        # tag's body.
        html = ''
        if node.text:
            html = markdown.markdown(node.text)
        return tags.html_string_to_element_tree(
            '<div class="gcb-markdown">%s</div>' % html)

    def rollup_header_footer(self, context):
        """Include markdown css only when markdown tag is present."""
        header = tags.html_string_to_element_tree(
            '<link href="{}/css/markdown.css" rel="stylesheet">'.format(
                _STATIC_URL))
        footer = tags.html_string_to_element_tree('')
        return (header, footer)

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(Markdown.name())
        reg.add_property(schema_fields.SchemaField(
            'markdown', 'Markdown', 'text',
            description=services.help_urls.make_learn_more_message(
                messages.RTE_MARKDOWN_MARKDOWN, 'core_tags:markdown:markdown'),
            extra_schema_dict_values={
                'mode': 'markdown', '_type': 'code',
            }, optional=False))
        return reg


custom_module = None


def register_module():
    """Registers this module in the registry."""

    custom_tags = [
        GoogleDoc, GoogleDrive, GoogleSpreadsheet, YouTube, Html5Video,
        GoogleGroup, IFrame, Include, Markdown]

    def make_binding_name(custom_tag):
        return 'gcb-%s' % custom_tag.__name__.lower()

    def on_module_disable():
        for custom_tag in custom_tags:
            tags.Registry.remove_tag_binding(make_binding_name(custom_tag))

        # Unregsiter extra libraries required by GoogleDrive
        GoogleDrive.on_unregister()

    def on_module_enable():
        for custom_tag in custom_tags:
            tags.Registry.add_tag_binding(
                make_binding_name(custom_tag), custom_tag)

        # Register extra libraries required by GoogleDrive
        GoogleDrive.on_register()

    global custom_module  # pylint: disable=global-statement

    global_routes = []
    namespaced_routes = [
        (_GOOGLE_DRIVE_TAG_PATH, GoogleDriveRESTHandler),
        (_GOOGLE_DRIVE_TAG_RENDERER_PATH, GoogleDriveTagRenderer),
    ]

    custom_module = custom_modules.Module(
        'Core Custom Tags Module',
        'A module that provides core custom tags.',
        global_routes, namespaced_routes,
        notify_module_enabled=on_module_enable,
        notify_module_disabled=on_module_disable)
    return custom_module
