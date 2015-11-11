function bindDatetimeField(Y) {
  var DatetimeField = function(options) {
    DatetimeField.superclass.constructor.call(this, options);
  };

  Y.extend(DatetimeField, Y.inputEx.DateTimeField, {
    render: function() {
      DatetimeField.superclass.render.call(this);
      Y.one(this.divEl).addClass('gcb-datetime')
          .addClass('inputEx-fieldWrapper')
          .on('click', function(e) { e.preventDefault() });
      var that = this;
      $('<button>Clear</button>')
          .addClass('inputEx-DatePicker-ClearButton')
          .click(function(){
            that.clear();
            that.validateDateTimeConsistent();
          })
          .insertBefore(that.divEl.lastChild);

      if (this.options.description) {
        $('<div class="inputEx-description">')
            .text(this.options.description)
            .attr('id', this.options.id + '-desc')
            .insertBefore(that.divEl.lastChild);
      }
      this.on('updated', this.validateDateTimeConsistent);
    },
    validateDateTimeConsistent: function() {
      var dateField = this.inputs[0];
      var timeField = this.inputs[1];
      if (!timeField.isEmpty() &&
          timeField.getValue() != '00:00:00' &&
          dateField.isEmpty()) {
        $(dateField.divEl).addClass('inputEx-invalid');
        return false;
      }
      $(dateField.divEl).removeClass('inputEx-invalid');
      return true;
    },
    validate: function() {
      return (
          DatetimeField.superclass.validate.call(this) &&
          this.validateDateTimeConsistent());
    },
    setValue: function(val, sendUpdatedEvt) {
      if (val) {
        val = new Date(val);
      }
      DatetimeField.superclass.setValue.call(this, val, sendUpdatedEvt);
    },
    getValue: function() {
      var val = DatetimeField.superclass.getValue.call(this);
      return val ? val.toISOString() : null;
    }
  });

  Y.inputEx.registerType('datetime', DatetimeField, []);
}
