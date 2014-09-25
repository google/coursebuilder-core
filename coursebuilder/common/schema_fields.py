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

"""Mapping from schema to backend properties."""

__author__ = 'Abhinav Khandelwal (abhinavk@google.com)'

import collections
import copy
import json


class Property(object):
    """Property."""

    def __init__(
        self, name, label, property_type, select_data=None, description=None,
        optional=False, extra_schema_dict_values=None):
        self._name = name
        self._label = label
        self._property_type = property_type
        self._select_data = select_data
        self._description = description
        self._optional = optional
        self._extra_schema_dict_values = extra_schema_dict_values or {}

    def __str__(self):
        return '%s#%s' % (self._name, self._property_type)

    @property
    def type(self):
        return self._property_type

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return self._description

    @property
    def extra_schema_dict_values(self):
        return self._extra_schema_dict_values

    @property
    def label(self):
        return self._label

    def set_select_data(self, select_data):
        self._select_data = select_data

    def get_display_dict(self):
        return {
            'name': self._name,
            'label': self._label,
            'description': self._description,
            }


class Registry(object):
    """Registry is a collection of Property's."""

    def __init__(self, title, description=None, extra_schema_dict_values=None):
        self._title = title
        self._registry = {'id': title, 'type': 'object'}
        self._description = description
        if description:
            self._registry['description'] = description
        self._extra_schema_dict_values = extra_schema_dict_values
        self._properties = []
        self._sub_registries = collections.OrderedDict()

    @property
    def title(self):
        return self._title

    @property
    def sub_registries(self):
        return self._sub_registries

    def add_property(self, schema_field):
        """Add a Property to this Registry."""
        self._properties.append(schema_field)

    def get_property(self, property_name):
        for prop in self._properties:
            if prop.name == property_name:
                return prop
        return None

    def get_sub_registry(self, sub_registry_name):
        return self._sub_registries.get(sub_registry_name)

    def remove_property(self, property_name):
        prop = self.get_property(property_name)
        if prop:
            return self._properties.pop(self._properties.index(prop))

    def add_sub_registry(
        self, name, title=None, description=None, registry=None):
        """Add a sub registry to for this Registry."""
        if not registry:
            registry = Registry(title, description)
        self._sub_registries[name] = registry
        return registry

    def has_subregistries(self):
        return True if self._sub_registries else False

    def get_display_dict(self):
        return {
            'title': self._title,
            'properties': [p.get_display_dict() for p in self._properties],
            'registries': [r.get_display_dict()
                           for r in self._sub_registries.itervalues()],
            }

    def clone_only_items_named(self, paths):
        """Clone only the selected items from a registry.

        Args:
          paths: Each item is a path into the schema, with slashes as
            separators.  E.g., "foo" would match things at the top level
            named "foo".  Similarly, 'foo/bar/baz' looks in sub-schema
            "foo" for a sub-schema "bar", and within that, "baz."  The
            returned schema would include not just the leaf item, but
            sub-registry 'foo' containing 'bar', containing 'baz'.

            NOTE - Schema hierarchy components are stored separately from
            properties, and so "foo" may well match _both_ a subschema
            _and_ a property, if someone were unwise enough to build
            a schema with overloaded names.

            Also note that colons in names are not special to this function,
            though they may well have special meaning to, e.g., the
            course schema mapping to course.yaml dict hierarchy.  Picking
            out a single such field would use a name such as
            "registration/course:send_welcome_notifications".
        Returns:
          A schema with only the named items present.
        """

        # Arbitrary depth instantiate-on-reference dict constructor
        treebuilder = lambda: collections.defaultdict(treebuilder)

        # Build a tree of nodes from the given paths.
        root = treebuilder()
        for path in paths:
            parts = path.split('/')
            node = root
            for part in parts:
                node = node[part]

        registry = copy.deepcopy(self)
        def delete_all_but(registry, node):
            # pylint: disable-msg=protected-access
            # Copy so deleting does not wreck iterator.
            for prop in copy.copy(registry._properties):
                if prop.name not in node:
                    registry._properties.remove(prop)
            for name, value in registry._sub_registries.iteritems():
                # If this subregistry is not named at all, remove it.
                if name not in node:
                    del registry._sub_registries[name]

                # If the paths-to-save gives sub-entries within this
                # node, then proceed into the node to prune its members.
                # Otherwise, do nothing, leaving the node and all its
                # children in place.
                elif node[name]:
                    delete_all_but(value, node[name])
        delete_all_but(registry, root)
        return registry


class SchemaField(Property):
    """SchemaField defines a simple field."""

    def __init__(
        self, name, label, property_type, select_data=None, description=None,
        optional=False, hidden=False, editable=True, i18n=None,
        extra_schema_dict_values=None, validator=None):
        Property.__init__(
            self, name, label, property_type, select_data=select_data,
            description=description, optional=optional,
            extra_schema_dict_values=extra_schema_dict_values)
        self._hidden = hidden
        self._editable = editable
        self._validator = validator
        self._i18n = i18n

    @property
    def hidden(self):
        return self._hidden

    @property
    def editable(self):
        return self._editable

    @property
    def i18n(self):
        return self._i18n

    def get_json_schema_dict(self):
        """Get the JSON schema for this field."""
        prop = {}
        prop['type'] = self._property_type
        if self._optional:
            prop['optional'] = self._optional
        if self._description:
            prop['description'] = self._description
        if self._i18n:
            prop['i18n'] = self._i18n
        return prop

    def _get_schema_dict(self, prefix_key):
        """Get Schema annotation dictionary for this field."""
        if self._extra_schema_dict_values:
            schema = self._extra_schema_dict_values
        else:
            schema = {}
        schema['label'] = self._label
        if self._hidden:
            schema['_type'] = 'hidden'
        elif not self._editable:
            schema['_type'] = 'uneditable'
        elif self._select_data and '_type' not in schema:
            schema['_type'] = 'select'

        if 'date' is self._property_type:
            if 'dateFormat' not in schema:
                schema['dateFormat'] = 'Y/m/d'
            if 'valueFormat' not in schema:
                schema['valueFormat'] = 'Y/m/d'
        elif self._select_data:
            choices = []
            for value, label in self._select_data:
                choices.append(
                    {'value': value, 'label': unicode(label)})
            schema['choices'] = choices

        if self._description:
            schema['description'] = self._description

        return [(prefix_key + ['_inputex'], schema)]

    def validate(self, value, errors):
        if self._validator:
            self._validator(value, errors)


class FieldArray(SchemaField):
    """FieldArray is an array with object or simple items."""

    def __init__(
        self, name, label, description=None, item_type=None,
        extra_schema_dict_values=None):

        super(FieldArray, self).__init__(
            name, label, 'array', description=description,
            extra_schema_dict_values=extra_schema_dict_values)
        self._item_type = item_type

    @property
    def item_type(self):
        return self._item_type

    def get_json_schema_dict(self):
        json_schema = super(FieldArray, self).get_json_schema_dict()
        json_schema['items'] = self._item_type.get_json_schema_dict()
        return json_schema

    def _get_schema_dict(self, prefix_key):
        dict_list = super(FieldArray, self)._get_schema_dict(prefix_key)
        # pylint: disable-msg=protected-access
        dict_list += self._item_type._get_schema_dict(prefix_key + ['items'])
        # pylint: enable-msg=protected-access
        return dict_list


class FieldRegistry(Registry):
    """FieldRegistry is an object with SchemaField properties."""

    def add_sub_registry(
        self, name, title=None, description=None, registry=None):
        """Add a sub registry to for this Registry."""
        if not registry:
            registry = FieldRegistry(title, description=description)
        self._sub_registries[name] = registry
        return registry

    def get_json_schema_dict(self):
        schema_dict = dict(self._registry)
        schema_dict['properties'] = collections.OrderedDict()
        for schema_field in self._properties:
            schema_dict['properties'][schema_field.name] = (
                schema_field.get_json_schema_dict())
        for key in self._sub_registries.keys():
            schema_dict['properties'][key] = (
                self._sub_registries[key].get_json_schema_dict())
        return schema_dict

    def get_json_schema(self):
        """Get the json schema for this API."""
        return json.dumps(self.get_json_schema_dict())

    def _get_schema_dict(self, prefix_key):
        """Get schema dict for this API."""
        title_key = list(prefix_key)
        title_key.append('title')
        schema_dict = [(title_key, self._title)]

        if self._extra_schema_dict_values:
            key = list(prefix_key)
            key.append('_inputex')
            schema_dict.append([key, self._extra_schema_dict_values])

        base_key = list(prefix_key)
        base_key.append('properties')

        # pylint: disable-msg=protected-access
        for schema_field in self._properties:
            key = base_key + [schema_field.name]
            schema_dict += schema_field._get_schema_dict(key)
        # pylint: enable-msg=protected-access

        for key in self._sub_registries.keys():
            sub_registry_key_prefix = list(base_key)
            sub_registry_key_prefix.append(key)
            sub_registry = self._sub_registries[key]
            # pylint: disable-msg=protected-access
            for entry in sub_registry._get_schema_dict(sub_registry_key_prefix):
                schema_dict.append(entry)
            # pylint: enable-msg=protected-access
        return schema_dict

    def get_schema_dict(self):
        """Get schema dict for this API."""
        return self._get_schema_dict(list())

    @classmethod
    def _add_entry(cls, key_part_list, value, entity):
        if len(key_part_list) == 1:
            entity[key_part_list[0]] = value
            return
        key = key_part_list.pop()
        if not entity.has_key(key):
            entity[key] = {}
        else:
            assert type(entity[key]) == type(dict())
        cls._add_entry(key_part_list, value, entity[key])

    @classmethod
    def convert_json_to_entity(cls, json_entry, entity):
        assert type(json_entry) == type(dict())
        for key in json_entry.keys():
            if type(json_entry[key]) == type(dict()):
                cls.convert_json_to_entity(json_entry[key], entity)
            else:
                key_parts = key.split(':')
                key_parts.reverse()
                cls._add_entry(key_parts, json_entry[key], entity)

    @classmethod
    def _get_field_name_parts(cls, field_name):
        field_name_parts = field_name.split(':')
        field_name_parts.reverse()
        return field_name_parts

    @classmethod
    def _get_field_value(cls, key_part_list, entity):
        if len(key_part_list) == 1:
            if type(entity) == dict and entity.has_key(key_part_list[0]):
                return entity[key_part_list[0]]
            return None
        key = key_part_list.pop()
        if entity.has_key(key):
            return cls._get_field_value(key_part_list, entity[key])
        return None

    def convert_entity_to_json_entity(self, entity, json_entry):
        for schema_field in self._properties:
            field_name = schema_field.name
            field_name_parts = self._get_field_name_parts(field_name)
            value = self._get_field_value(field_name_parts, entity)
            if type(value) != type(None):
                json_entry[field_name] = value

        for key in self._sub_registries.keys():
            json_entry[key] = {}
            self._sub_registries[key].convert_entity_to_json_entity(
                entity, json_entry[key])

    def validate(self, payload, errors):
        for schema_field in self._properties:
            field_name_parts = self._get_field_name_parts(schema_field.name)
            value = self._get_field_value(field_name_parts, payload)
            schema_field.validate(value, errors)

        for registry in self._sub_registries.values():
            registry.validate(payload, errors)

    @classmethod
    def is_complex_name(cls, name):
        return ':' in name

    @classmethod
    def compute_name(cls, parent_names):
        """Computes non-indexed and indexed entity name given parent names."""
        parts = []
        for parent_name in parent_names:
            if parent_name[0] == '[' and parent_name[-1] == ']':
                parts.append('[]')
            else:
                parts.append(parent_name)
        return ':'.join(parts), ':'.join(parent_names)


class SchemaFieldValue(object):
    """This class represents an instance of a field value."""

    def __init__(self, name, field, value, setter):
        """An object that name, value and type of a field.

        Args:
            name: a name of the value
            field: SchemaField object that holds the type
            value: Python object that holds the value
            setter: a function which sets the value in the underlying data
                structure
        """
        self._name = name
        self._field = field
        self._value = value
        self._setter = setter

    @property
    def name(self):
        return self._name

    @property
    def field(self):
        return self._field

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        self._value = new_value
        self._setter(new_value)


class FieldRegistryIndex(object):
    """Helper class that allows fast access to values and their fields."""

    def __init__(self, registry):
        self._registry = registry
        self._names_in_order = []
        self._complex_name_to_field = {}
        self._computed_name_to_field = {}

    @property
    def registry(self):
        return self._registry

    @property
    def names_in_order(self):
        return self._names_in_order

    def _inspect_registry(self, parent_names, registry):
        """Inspects registry and adds its items to the index."""
        for field in registry._properties:  # pylint: disable=protected-access
            name = field.name
            if isinstance(field, FieldArray):
                self._inspect_registry(
                    parent_names + [name, '[]'], field.item_type)
            if registry.is_complex_name(field.name):
                complex_name = field.name
                if complex_name in self._complex_name_to_field:
                    raise KeyError('Field already defined: %s.' % complex_name)
                self._complex_name_to_field[complex_name] = field
                self._names_in_order.append(complex_name)
            else:
                computed_name = ':'.join(parent_names + [field.name])
                if computed_name in self._computed_name_to_field:
                    raise KeyError('Field already defined: %s.' % computed_name)
                self._computed_name_to_field[computed_name] = field
                self._names_in_order.append(computed_name)

        # pylint: disable=protected-access
        for name, registry in registry._sub_registries.items():
            self._inspect_registry(parent_names + [name], registry)

    def rebuild(self):
        """Build an index."""
        self._inspect_registry([], self._registry)

    def find(self, name):
        """Finds and returns a field given field name."""
        field = self._complex_name_to_field.get(name)
        return field if field else self._computed_name_to_field.get(name)


class FieldFilter(object):
    """Filter for collections of schema fields."""

    def __init__(
            self, type_names=None, hidden_values=None, i18n_values=None,
            editable_values=None):
        self._type_names = type_names
        self._hidden_values = hidden_values
        self._i18n_values = i18n_values
        self._editable_values = editable_values

    def _filter(self, named_field_list):
        """Filters a list of name, SchemaField pairs."""
        result = set()
        for name, field in named_field_list:
            if self._type_names and field.type not in self._type_names:
                continue
            if self._hidden_values and field.hidden not in self._hidden_values:
                continue
            if self._editable_values and (
                    field.editable not in self._editable_values):
                continue
            if self._i18n_values and field.i18n not in self._i18n_values:
                continue
            result.add(name)
        return result

    def filter_value_to_type_binding(self, binding):
        """Returns a set of value names that pass the criterion."""
        named_field_list = [
            (field_value.name, field_value.field)
            for field_value in binding.value_list]
        return self._filter(named_field_list)

    def filter_field_registry_index(self, index):
        """Returns the field names in the schema that pass the criterion."""
        named_field_list = [
            (name, index.find(name)) for name in index.names_in_order]
        return self._filter(named_field_list)


class ValueToTypeBinding(object):
    """This class provides mapping of entity attributes to their types."""

    def __init__(self):
        self.value_list = []  # a list of all encountered  SchemaFieldValues
        self.name_to_value = {}  # field name to SchemaFieldValue mapping
        self.name_to_field = {}  # field name to SchemaField mapping
        self.unmapped_names = set()  # a set of field names where mapping failed
        self.index = None  # the indexed set of schema names

    def find_value(self, name):
        return self.name_to_value[name]

    def find_field(self, name):
        return self.name_to_field[name]

    @classmethod
    def _get_setter(cls, entity, key):
        def setter(value):
            entity[key] = value
        return setter

    @classmethod
    def _visit_dict(cls, index, parent_names, entity, binding):
        """Visit dict entity."""
        for _name, _value in entity.items():
            cls._decompose_entity(
                index, parent_names + [_name], _value, binding,
                cls._get_setter(entity, _name))

    @classmethod
    def _visit_list(cls, index, parent_names, entity, binding, setter):
        """Visit list entity."""
        name_no_index, name = index.registry.compute_name(parent_names)
        _field = index.find(name_no_index)
        if _field:
            assert isinstance(_field, FieldArray)
            assert name not in binding.name_to_field
            binding.name_to_field[name] = _field
            assert name not in binding.name_to_value, name
            binding.name_to_value[name] = SchemaFieldValue(
                name, _field, entity, setter)
            for _index, _item in enumerate(entity):
                _item_name = '[%s]' % _index
                cls._decompose_entity(
                    index, parent_names + [_item_name], _item, binding,
                    cls._get_setter(entity, _index))
        else:
            assert name not in binding.unmapped_names
            binding.unmapped_names.add(name)

    @classmethod
    def _visit_attribute(cls, index, parent_names, entity, binding, setter):
        """Visit simple attribute."""
        name_no_index, name = index.registry.compute_name(parent_names)
        _field = index.find(name_no_index)
        if _field:
            _value = SchemaFieldValue(name, _field, entity, setter)
            binding.value_list.append(_value)
            assert name not in binding.name_to_value, name
            binding.name_to_value[name] = _value
            assert name not in binding.name_to_field
            binding.name_to_field[name] = _field
        else:
            assert name not in binding.unmapped_names, name
            binding.unmapped_names.add(name)

    @classmethod
    def _decompose_entity(
        cls, index, parent_names, entity, binding, setter):
        """Recursively decomposes entity."""
        if isinstance(entity, dict):
            cls._visit_dict(index, parent_names, entity, binding)
        elif isinstance(entity, list):
            cls._visit_list(index, parent_names, entity, binding, setter)
        else:
            cls._visit_attribute(index, parent_names, entity, binding, setter)

    @classmethod
    def bind_entity_to_schema(cls, json_dumpable_entity, registry):
        """Connects schema field type information to the entity attributes.

        Args:
            json_dumpable_entity: a Python dict recursively containing other
              dict, list and primitive objects
            registry: a FieldRegistry that holds entity type information
        Returns:
            an instance of ValueToTypeBinding object that maps entity attributes
            to their types
        """
        binding = ValueToTypeBinding()
        index = FieldRegistryIndex(registry)
        index.rebuild()
        cls._decompose_entity(
            index, [], json_dumpable_entity, binding, None)
        binding.index = index
        return binding
