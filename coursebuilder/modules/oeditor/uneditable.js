function bindUneditableField(Y) {
  var UneditableField = function(options) {
    UneditableField.superclass.constructor.call(this, options);
  };

  Y.extend(UneditableField, Y.inputEx.Field, {
    setOptions: function(options) {
      UneditableField.superclass.setOptions.call(this, options);
      this.options.visu = options.visu;
    },
    renderComponent: function() {
      this.wrapEl = Y.inputEx.cn(
        'div', {className: 'inputEx-UneditableField-wrapper'});
      this.fieldContainer.appendChild(this.wrapEl);
    },
    setValue: function(val, sendUpdatedEvt) {
      this.value = val;
      Y.inputEx.renderVisu(this.options.visu, val, this.wrapEl);
      UneditableField.superclass.setValue.call(this, val, sendUpdatedEvt);
    },
    getValue: function() {
      return this.value;
    }
  });

  Y.inputEx.registerType("uneditable", UneditableField, []);
}
