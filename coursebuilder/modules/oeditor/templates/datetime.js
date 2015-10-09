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
    },
    setValue: function(val, sendUpdatedEvt) {
      if (val) {
        val = new Date(val);
      }
      DatetimeField.superclass.setValue.call(this, val, sendUpdatedEvt);
    },
    getValue: function() {
      val = DatetimeField.superclass.getValue.call(this);
      if (! val) {
        return null;
      }

      var year = val.getFullYear();
      var month = val.getMonth() + 1;
      var date = val.getDate();
      var hours = val.getHours();
      var minutes = val.getMinutes();

      function pad(num) {
        return (num < 10 ? '0' : '') + num;
      }
      return year + '-' + pad(month) + '-' + pad(date) +
          ' ' + pad(hours) + ':' + pad(minutes);
    }
  });

  Y.inputEx.registerType('datetime', DatetimeField, []);
}
