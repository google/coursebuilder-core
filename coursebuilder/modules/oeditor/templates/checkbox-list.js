function bindCheckboxListField(Y) {

  function zip(arrays) {
    return arrays[0].map(function(_,i){
      return arrays.map(function(array){return array[i]})
    });
  }

  var CheckboxListField = function(options) {
    CheckboxListField.superclass.constructor.call(this,options);
  };

  Y.extend(CheckboxListField, Y.inputEx.Field, {
    setOptions: function(options) {
      CheckboxListField.superclass.setOptions.call(this, options);
      this.options.choices = Y.Lang.isArray(options.choices) ?
        options.choices : [];
      this.options.noItemsMessage = options.noItemsMessage || 'No items';
      this.options.noItemsHideField = options.noItemsHideField || false;
    },

    renderComponent: function() {
      var that = this;
      this.wrapEl = $('<div class="inputEx-CheckboxListField-wrapper"></div>')
      this.wrapEl.appendTo(this.fieldContainer);
      this.subFields = this.options.choices.map(function(choice) {
        return that.renderSubField(choice);
      })
      if (!this.options.choices.length) {
        if (this.options.noItemsHideField) {
          // wait until that.fieldContainer is attached to the DOM so we can
          // find its parent.
          setTimeout(function(){
            $(that.fieldContainer).closest('.inputEx-fieldWrapper').remove();
          }, 0);
        } else {
          var noItemsNode = $(
            '<div class="inputEx-CheckboxListField-noItems"></div>');
          noItemsNode.text(this.options.noItemsMessage);
          noItemsNode.appendTo(this.wrapEl);
        }
      }
    },

    renderSubField: function(choice) {
      var opts = {
        'name': this.options.name + '[' + choice.value + ']',
        'rightLabel': choice.label,
        'type': 'boolean',
      };
      var el = Y.inputEx(opts, this);
      var subFieldEl = el.getEl();
      Y.one(subFieldEl).addClass('inputEx-CheckboxListField-subFieldEl');
      this.wrapEl.append(subFieldEl);
      el.on('updated', this.onChange, this, true);
      el.choiceValue = choice.value;
      return el;
    },

    setValue: function(values) {
      this.subFields.forEach(function(subField) {
        subField.setValue($.inArray(subField.choiceValue, values) != -1);
      })
    },

    getValue: function() {
      var result = [];
      this.subFields.forEach(function(subField) {
        if (subField.getValue()) {
          result.push(subField.choiceValue);
        }
      });
      return result;
    },
  });
  Y.inputEx.registerType("checkbox-list", CheckboxListField, [
    {type: 'boolean', label: 'List element type', required: true,
    name: 'elementType'}
  ]);
}
