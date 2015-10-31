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

__author__ = 'Gun Pinyo (gunpinyo@google.com)'

import os
from xml.etree import cElementTree

import appengine_config
from common import schema_fields
from common import tags
from models import custom_modules
from modules.code_tags import messages

CODETAGS_MODULE_URI = '/modules/code_tags'
CODETAGS_RESOURCES_URI = CODETAGS_MODULE_URI + '/resources'
CODEMIRROR_URI = '/static/codemirror'

SELECT_DATA = [
    # codemirror does not have plain text mode
    # however by setting an incorrect mode it will default to plain text
    ('', 'Plain Text'),
    ('htmlmixed', 'Html'),
    ('javascript', 'JavaScript'),
    ('css', 'CSS'),
    ('python', 'Python'),
    ('ruby', 'Ruby'),
    ('shell', 'Shell'),
    ('xml', 'XML'),
    ('xquery', 'XQuery'),
    ('yaml', 'Yaml'),
    ('perl', 'Perl'),
    ('php', 'PHP'),
    ('coffeescript', 'CoffeeScript'),
    ('clike', 'C (and relative)'),
    ('apl', 'apl'),
    ('asterisk', 'asterisk'),
    ('clojure', 'clojure'),
    ('cobol', 'cobol'),
    ('commonlisp', 'commonlisp'),
    ('cypher', 'cypher'),
    ('d', 'd'),
    ('diff', 'diff'),
    ('django', 'django'),
    ('dtd', 'dtd'),
    ('dylan', 'dylan'),
    ('ecl', 'ecl'),
    ('eiffel', 'eiffel'),
    ('erlang', 'erlang'),
    ('fortran', 'fortran'),
    ('gas', 'gas'),
    ('gfm', 'gfm'),
    ('gherkin', 'gherkin'),
    ('go', 'go'),
    ('groovy', 'groovy'),
    ('haml', 'haml'),
    ('haskell', 'haskell'),
    ('haxe', 'haxe'),
    ('htmlembedded', 'htmlembedded'),
    ('http', 'http'),
    ('jade', 'jade'),
    ('jinja2', 'jinja2'),
    ('julia', 'julia'),
    ('kotlin', 'kotlin'),
    ('livescript', 'livescript'),
    ('lua', 'lua'),
    ('markdown', 'markdown'),
    ('mirc', 'mirc'),
    ('mllike', 'mllike'),
    ('nginx', 'nginx'),
    ('ntriples', 'ntriples'),
    ('octave', 'octave'),
    ('pascal', 'pascal'),
    ('pegjs', 'pegjs'),
    ('pig', 'pig'),
    ('properties', 'properties'),
    ('puppet', 'puppet'),
    ('q', 'q'),
    ('r', 'r'),
    ('rpm', 'rpm'),
    ('rst', 'rst'),
    ('rust', 'rust'),
    ('sass', 'sass'),
    ('scheme', 'scheme'),
    ('sieve', 'sieve'),
    ('slim', 'slim'),
    ('smalltalk', 'smalltalk'),
    ('smarty', 'smarty'),
    ('smartymixed', 'smartymixed'),
    ('solr', 'solr'),
    ('sparql', 'sparql'),
    ('sql', 'sql'),
    ('stex', 'stex'),
    ('tcl', 'tcl'),
    ('tiddlywiki', 'tiddlywiki'),
    ('tiki', 'tiki'),
    ('toml', 'toml'),
    ('turtle', 'turtle'),
    ('vb', 'vb'),
    ('vbscript', 'vbscript'),
    ('velocity', 'velocity'),
    ('verilog', 'verilog'),
    ('z80', 'z80'),
]


class CodeTag(tags.ContextAwareTag):
    """Custom tag for showing piece of code using CodeMirror."""

    binding_name = 'gcb-code'

    @classmethod
    def name(cls):
        return 'Code'

    @classmethod
    def vendor(cls):
        return 'gcb'

    @classmethod
    def required_modules(cls):
        return super(CodeTag, cls).required_modules() + [
            'gcb-code', 'inputex-select']

    @classmethod
    def extra_js_files(cls):
        return ['code_tags_popup.js']

    @classmethod
    def additional_dirs(cls):
        return [os.path.join(
            appengine_config.BUNDLE_ROOT, 'modules', 'code_tags', 'resources')]

    def render(self, node, context):
        code_elt = cElementTree.Element('code')
        code_elt.text = node.text or ''
        code_elt.set('class', 'codemirror-container-readonly')
        code_elt.set('data-mode', node.attrib.get('mode'))
        return code_elt

    def rollup_header_footer(self, context):
        """Include CodeMirror library only when a code tag is present."""

        header = tags.html_string_to_element_tree(
            '<script src="%s/lib/codemirror.js"></script>'
            '<link rel="stylesheet" href="%s/lib/codemirror.css">'
            '<script src="%s/addon/mode/loadmode.js"></script>'
            '<link rel="stylesheet" href="%s/code_tags.css">' % (
                CODEMIRROR_URI, CODEMIRROR_URI, CODEMIRROR_URI,
                CODETAGS_RESOURCES_URI))
        footer = tags.html_string_to_element_tree(
            '<script src="%s/code_tags.js">'
            '</script>' % CODETAGS_RESOURCES_URI)

        return (header, footer)

    def get_icon_url(self):
        return CODETAGS_RESOURCES_URI + '/code_tags.png'

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(CodeTag.name())
        reg.add_property(
            schema_fields.SchemaField(
                'mode', 'Language', 'string',
                optional=True, description=messages.RTE_LANGUAGE,
                select_data=SELECT_DATA))
        reg.add_property(
            schema_fields.SchemaField(
                'code', 'Code', 'text',
                description=messages.RTE_CODE, extra_schema_dict_values={
                    '_type': 'code',
                }, optional=True))
        return reg


custom_module = None


def register_module():
    """Registers this module for use."""

    def on_module_enable():
        tags.Registry.add_tag_binding(CodeTag.binding_name, CodeTag)

    def on_module_disable():
        tags.Registry.remove_tag_binding(CodeTag.binding_name)

    global_routes = [
        (CODETAGS_RESOURCES_URI + '/.*', tags.ResourcesHandler),
    ]
    namespaced_routes = []

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Code Editor and Code Example Display',
        'Allow teacher to use a proper code editor and'
        'allow student to see a proper piece of code',
        global_routes, namespaced_routes,
        notify_module_enabled=on_module_enable,
        notify_module_disabled=on_module_disable)

    return custom_module
