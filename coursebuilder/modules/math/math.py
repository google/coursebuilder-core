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

__author__ = [
    'Neema Kotonya (neemak@google.com)',
    'Gun Pinyo (gunpinyo@google.com)'
]

import os
from xml.etree import cElementTree

import appengine_config
from common import schema_fields
from common import tags
from controllers import sites
from models import custom_modules
from models import services
from modules.math import messages

MATH_MODULE_URI = '/modules/math'
RESOURCES_URI = MATH_MODULE_URI + '/resources'
MATHJAX_URI = MATH_MODULE_URI + '/MathJax'


class MathTag(tags.ContextAwareTag):
    """Custom tag for mathematical notation using MathJax."""

    binding_name = 'gcb-math'

    @classmethod
    def name(cls):
        return 'Mathematical Formula'

    @classmethod
    def vendor(cls):
        return 'gcb'

    def render(self, node, context):
        math_script = cElementTree.XML('<script/>')

        # The formula is "text" type in the schema and so is presented in the
        # tag's body.
        math_script.text = node.text

        input_type = node.attrib.get('input_type')
        if input_type == 'MML':
            math_script.set('type', 'math/mml')
        else:
            math_script.set('type', 'math/tex')

        return math_script

    def rollup_header_footer(self, context):
        """Include MathJax library only when a math tag is present."""

        header = tags.html_string_to_element_tree("""
<script src="%s/MathJax.js?config=TeX-AMS-MML_HTMLorMML">
</script>""" % MATHJAX_URI)
        footer = tags.html_string_to_element_tree('')
        return (header, footer)

    def get_icon_url(self):
        return RESOURCES_URI + '/math.png'

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(MathTag.name())
        reg.add_property(
            schema_fields.SchemaField(
                'input_type', 'Type', 'string', i18n=False,
                optional=True,
                select_data=[('TeX', 'TeX'), ('MML', 'MathML')],
                extra_schema_dict_values={'value': 'TeX'},
                description=services.help_urls.make_learn_more_message(
                    messages.RTE_MATH_TYPE, 'math:math:input_type')))
        reg.add_property(
            schema_fields.SchemaField(
                'formula', 'Mathematical Formula', 'text',
                optional=True,
                description=messages.RTE_MATH_MATHEMATICAL_FORMULA))
        return reg


custom_module = None


def register_module():
    """Registers this module for use."""

    def on_module_disable():
        tags.Registry.remove_tag_binding(MathTag.binding_name)

    def on_module_enable():
        tags.Registry.add_tag_binding(MathTag.binding_name, MathTag)

    global_routes = [
        (RESOURCES_URI + '/.*', tags.ResourcesHandler),
        (MATHJAX_URI + '/(fonts/.*)', sites.make_zip_handler(os.path.join(
            appengine_config.BUNDLE_ROOT, 'lib', 'mathjax-fonts-2.3.0.zip'))),
        (MATHJAX_URI + '/(.*)', sites.make_zip_handler(os.path.join(
            appengine_config.BUNDLE_ROOT, 'lib', 'mathjax-2.3.0.zip')))]
    namespaced_routes = []

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Mathematical Formula Display',
        'Provides a custom tag to embed mathematical formulas using TeX or MML.'
        , global_routes, namespaced_routes,
        notify_module_disabled=on_module_disable,
        notify_module_enabled=on_module_enable)
    return custom_module
