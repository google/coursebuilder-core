"""Unit tests for the common.sanitize module."""

__author__ = 'John Orr (jorr@google.com)'

import unittest
from common import safe_dom


class MockNode(safe_dom.Node):

    def __init__(self, value):
        super(MockNode, self).__init__()
        self._value = value

    @property
    def sanitized(self):
        return self._value


class NodeListTests(unittest.TestCase):
    """Unit tests for common.safe_dom.NodeList."""

    def test_list(self):
        """NodeList should escape all its members."""
        node_list = safe_dom.NodeList()
        node_list.append(MockNode('a')).append(MockNode('b'))
        self.assertEqual('ab', node_list.sanitized)

    def test_len(self):
        """NodeList should support len."""
        node_list = safe_dom.NodeList().append(
            MockNode('a')).append(MockNode('b'))
        self.assertEqual(2, len(node_list))

    def test_append_node_list(self):
        """NodeList should support appending both Nodes and NodeLists."""
        node_list = safe_dom.NodeList().append(
            safe_dom.NodeList().append(MockNode('a')).append(MockNode('b'))
        ).append(MockNode('c'))
        self.assertEqual('abc', node_list.__str__())

    def test_insert_node_list(self):
        """NodeList should support inserting Nodes."""
        node_list = safe_dom.NodeList()
        node_list.append(MockNode('a')).append(MockNode('c'))
        node_list.insert(1, MockNode('b'))
        self.assertEqual('abc', node_list.__str__())


class TextTests(unittest.TestCase):
    """Unit tests for common.safe_dom.Text."""

    def test_text_sanitizes(self):
        """Text should sanitize unsafe characters."""
        unsafe_string = '<script>'
        text = safe_dom.Text(unsafe_string)
        self.assertEqual('&lt;script&gt;', text.sanitized)

    def test_str_returns_sanitized(self):
        """The _str__ method should return sanitized text."""
        unsafe_string = '<script>'
        text = safe_dom.Text(unsafe_string)
        self.assertEqual('&lt;script&gt;', text.__str__())


class ElementTests(unittest.TestCase):
    """Unit tests for common.safe_dom.Element."""

    def test_build_simple_element(self):
        """Element should build an element without attributes or children."""
        element = safe_dom.Element('p')
        self.assertEqual('<p></p>', element.__str__())

    def test_reject_bad_tag_names(self):
        """Element should reject bad tag names."""
        bad_names = ['2a', 'a b', '@', '-q']
        for name in bad_names:
            try:
                safe_dom.Element(name)
            except AssertionError:
                continue
            self.fail('Expected an exception: "%s"' % name)

    def test_reject_bad_attribute_names(self):
        """Element should reject bad attribute names."""
        bad_names = ['2a', 'a b', '@', '-q']
        for name in bad_names:
            try:
                safe_dom.Element('p', **{name: 'good value'})
            except AssertionError:
                continue
            self.fail('Expected an exception: "%s"' % name)

    def test_include_attributes(self):
        """Element should include tag attributes."""
        element = safe_dom.Element('button', style='foo', onclick='action')
        self.assertEqual(
            '<button onclick="action" style="foo"></button>',
            element.__str__())

    def test_escape_quotes(self):
        """Element should escape single and double quote characters."""
        element = safe_dom.Element('a', href='a\'b"c`d')
        self.assertEqual(
            '<a href="a&#39;b&quot;c&#96;d"></a>', element.__str__())

    def test_allow_parens(self):
        """Element should allow parentheses in attributes."""
        element = safe_dom.Element('a', action='myAction()')
        self.assertEqual('<a action="myAction()"></a>', element.__str__())

    def test_allow_urls(self):
        """Element should allow urls with a method sepcified in an attribute."""
        element = safe_dom.Element(
            'a', action='http://a.b.com/d/e/f?var1=val1&var2=val2#fra')
        self.assertEqual(
            '<a action="http://a.b.com/d/e/f?var1=val1&amp;var2=val2#fra"></a>',
            element.__str__())

    def test_url_query_chars(self):
        """Element should pass '?' and '=' characters in an attribute."""
        element = safe_dom.Element('a', action='target?action=foo&value=bar')
        self.assertEqual(
            '<a action="target?action=foo&amp;value=bar"></a>',
            element.__str__())

    def test_convert_none_to_empty(self):
        """An attribute with value None should render as empty."""
        element = safe_dom.Element('a', action=None)
        self.assertEqual('<a action=""></a>', element.__str__())

    def test_coerce_className(self):
        """Element should replace the 'className' attrib with 'class'."""
        element = safe_dom.Element('p', className='foo')
        self.assertEqual('<p class="foo"></p>', element.__str__())

    def test_include_children(self):
        """Element should include child elements."""
        element = safe_dom.Element('a').add_child(
            safe_dom.Element('b').add_child(
                safe_dom.Element('c'))
        ).add_child(
            safe_dom.Element('d'))
        self.assertEqual('<a><b><c></c></b><d></d></a>', element.__str__())

    def test_include_node_list(self):
        """Element should include a list of children."""
        element = safe_dom.Element('a').add_children(
            safe_dom.NodeList().append(MockNode('b')).append(MockNode('c')))
        self.assertEqual('<a>bc</a>', element.__str__())

    def test_sanitize_children(self):
        """Element should sanitize child elements as they are included."""
        element = safe_dom.Element('td').add_child(
            safe_dom.Element('a', href='foo"bar').add_text('1<2'))
        self.assertEqual(
            '<td><a href="foo&quot;bar">1&lt;2</a></td>', element.__str__())

    def test_add_text(self):
        """Adding text should add text which will be sanitized."""
        self.assertEqual(
            '<a>1&lt;2</a>', safe_dom.Element('a').add_text('1<2').__str__())

    def test_add_attribute(self):
        """Attributes can be added after initialization."""
        self.assertEqual(
            '<a b="c" d="e" f="g" h="i"></a>',
            safe_dom.Element(
                'a', b='c', d='e').add_attribute(f='g', h='i').__str__())

    def test_void_elements_have_no_end_tags(self):
        """Void elements should have no end tag, e.g., <br/>."""
        void_elements = [
            'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
            'keygen', 'link', 'menuitem', 'meta', 'param', 'source', 'track',
            'wbr']
        for elt in void_elements:
            self.assertEqual('<%s/>' % elt, safe_dom.Element(elt).__str__())

    def test_empty_non_void_elememnts_should_have_end_tags(self):
        """Non-void elements should have their end tags, even when empty."""
        sample_elements = ['p', 'textarea', 'div']
        for elt in sample_elements:
            self.assertEqual(
                '<%s></%s>' % (elt, elt), safe_dom.Element(elt).__str__())


class ScriptElementTests(unittest.TestCase):
    """Unit tests for common.safe_dom.ScriptElement."""

    def test_script_should_not_escape_body(self):
        """"The body of the script tag should not be escaped."""
        script = safe_dom.ScriptElement()
        script.add_text('alert("foo");')
        script.add_text('1 < 2 && 2 > 1;')
        self.assertEqual(
            '<script>alert("foo");1 < 2 && 2 > 1;</script>', script.__str__())

    def test_script_should_reject_close_script_tag_in_body(self):
        """Expect an error if the body of the script tag contains </script>."""
        script = safe_dom.ScriptElement()
        script.add_text('</script>')
        try:
            script.__str__()
            self.fail('Expected an exception')
        except ValueError:
            pass

    def test_script_should_not_allow_child_nodes_to_be_added(self):
        """Script should not allow child nodes to be added."""
        script = safe_dom.ScriptElement()
        try:
            child = safe_dom.Element('br')
            script.add_child(child)
            self.fail('Expected an exception')
        except ValueError:
            pass

        try:
            children = safe_dom.NodeList().append(safe_dom.Element('br'))
            script.add_children(children)
            self.fail('Expected an exception')
        except ValueError:
            pass


class EntityTests(unittest.TestCase):
    """Unit tests for common.safe_dom.Entity."""

    def expect_pass(self, test_text):
        entity = safe_dom.Entity(test_text)
        self.assertEqual(test_text, entity.__str__())

    def expect_fail(self, test_text):
        try:
            safe_dom.Entity(test_text)
        except AssertionError:
            return
        self.fail('Expected an assert exception')

    def test_should_pass_named_entities(self):
        self.expect_pass('&nbsp;')

    def test_should_pass_decimal_entities(self):
        self.expect_pass('&#38;')

    def test_should_pass_hex_entities(self):
        self.expect_pass('&#x26AB;')

    def test_entities_must_start_with_ampersand(self):
        self.expect_fail('nbsp;')

    def test_entities_must_end_with_semicolon(self):
        self.expect_fail('&nbsp')

    def test_named_entities_must_be_all_alpha(self):
        self.expect_fail('&qu2ot;')

    def test_decimal_entities_must_be_all_decimal_digits(self):
        self.expect_fail('&#12A6;')

    def test_hex_entities_must_be_all_hex_digits(self):
        self.expect_fail('&#x26AG')

    def test_entitiesmust_be_non_empty(self):
        self.expect_fail('&;')
        self.expect_fail('&#;')
        self.expect_fail('&#x;')

    def test_should_reject_extraneous_characters(self):
        self.expect_fail(' &nbsp;')
        self.expect_fail('&nbsp; ')

    def test_should_reject_tampering(self):
        entity = safe_dom.Entity('&nbsp;')
        entity._entity = '<script/>'
        try:
            entity.__str__()
        except AssertionError:
            return
        self.fail('Expected an assert exception')


class MockTemplate(object):
    def __init__(self):
        self.render_received_args = None

    def render(self, **kwargs):
        self.render_received_args = kwargs
        return "<div>template</div>"


class TemplateTests(unittest.TestCase):
    def test_template_in_node_list(self):
        template = MockTemplate()
        template_node = safe_dom.Template(template, arg1='foo', arg2='bar')

        self.assertEqual(template.render_received_args, None)
        self.assertEqual(template_node.sanitized, "<div>template</div>")
        self.assertEqual(
            template.render_received_args, {'arg1':'foo', 'arg2':'bar'})

        # put it in the beginning, middle, and end of a node list
        node_list = safe_dom.NodeList().append(
            template_node
        ).append(
            safe_dom.Element('div', className='first')
        ).append(
            template_node
        ).append(
            safe_dom.Element('div', className='second')
        ).append(
            template_node
        )

        expected_nodelist = ('<div>template</div><div class="first"></div>'
            '<div>template</div><div class="second"></div><div>template</div>')
        self.assertEqual(node_list.sanitized, expected_nodelist)

        # wrap that nodelist in an element
        element = safe_dom.Element('div').add_children(node_list)
        self.assertEqual(
            element.sanitized, '<div>{}</div>'.format(expected_nodelist))
