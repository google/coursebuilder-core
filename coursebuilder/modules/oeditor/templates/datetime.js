function bindDatetimeField(Y) {
  var DatetimeField = function(options) {
    DatetimeField.superclass.constructor.call(this, options);
  };

  Y.extend(DatetimeField, Y.inputEx.DateTimeField, {
    render: function() {
      DatetimeField.superclass.render.call(this);
      Y.one(this.divEl).addClass('gcb-datetime')
          .addClass('inputEx-fieldWrapper');
      var that = this;

      // Do not allow buttons to submit the form
      $(this.divEl).on('click', 'button', function(e) {
        e.preventDefault();
      });

      $('<button>Clear</button>')
          .addClass('inputEx-DatePicker-ClearButton')
          .click(function() {
            that.clear();
            that.validateDateTimeConsistent();
          })
          .insertBefore(that.divEl.lastChild);

      if (this.options.description) {
        $('<div class="inputEx-description">')
            .html(this.options.description)
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
      if (this.options.required && dateField.isEmpty()) {
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
    reinterpretTimeZoneToUTC: function(date) {
      // Reinterprets the parts of local Date as being in UTC time zone instead.
      //
      // Local time YYYY/MM/DD HH:MM:SS.mmm parts are reinterpreted as
      // UTC YYYY/MM/DD HH:MM:SS.mmmZ parts. No change is made to the values
      // of any individual Date part. Instead, those parts are kept at the
      // same values and the time zone is just forced to UTC.
      return new Date(Date.UTC(
          date.getFullYear(), date.getMonth(), date.getDate(),
          date.getHours(), date.getMinutes(), date.getSeconds(),
          date.getMilliseconds()));
    },
    reinterpretTimeZoneToLocal: function(date) {
      // Reinterprets the parts of UTC Date as being in local time zone instead.
      //
      // The supplied Date object is in local time, but the caller needs the
      // corresponding UTC parts displayed in a form, not the supplied local
      // time parts. This function recovers those UTC time parts, but forces
      // the time zone to local time.
      return new Date(
          date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(),
          date.getUTCHours(), date.getUTCMinutes(), date.getUTCSeconds(),
          date.getUTCMilliseconds());
    },
    setValue: function(val, sendUpdatedEvt) {
      if (val) {
        // All supported `val` inputs are expected to end up represented in
        // local time in the just-created Date object, and would be displayed
        // in the datetime form element as such. `val` is one of:
        //
        // * A Date object, which is always a local time.
        //
        // * A numeric milliseconds since UTC epoch, which *always* represents
        //   a UTC time to the Date constructor. The resulting Date object
        //   contains that UTC time, but adjusted to the local time zone.
        //
        // * A `dateString` in ISO 8601 date and time "Z" (UTC) format, the
        //   only form currently stored and retrieved by Course Builder. (But
        //   RFC2822/IETF syntax or ISO 8601 time zone specifiers *should*
        //   work, for ECMAScript 6, at least.) Date.parse() correctly handles
        //   the time zone specified, but the resulting Date object is adjusted
        //   to the local time zone.
        var date = new Date(val);
        if ($(this.divEl).hasClass('gcb-utc-datetime')) {
          // The enclosing divEl has the gcb-utc-datetime CSS class, thus
          // indicating that the form field is being used to enter a *UTC*
          // datetime. So, the UTC date and time parts need to be recovered
          // from the local time `date`. Then the time zone must be forced
          // to local time zone, so that those UTC parts are displayed in the
          // datetime form element unchanged.
          val = this.reinterpretTimeZoneToLocal(date);
        } else {
          val = date;
        }
      }
      DatetimeField.superclass.setValue.call(this, val, sendUpdatedEvt);
    },
    getValue: function() {
      // DatetimeField value is always a Date object (or null).
      var date = DatetimeField.superclass.getValue.call(this);
      if (date) {
        if ($(this.divEl).hasClass('gcb-utc-datetime')) {
          // The Date object from the form element is always in local time.
          // Since the enclosing divEl has the gcb-utc-datetime CSS class,
          // the form field was used to enter a *UTC* time. Reinterpret the
          // individual Date parts unchanged as having the UTC time zone.
          date = this.reinterpretTimeZoneToUTC(date);
        }
        return date.toISOString();
      }
      return null;
    }
  });

  Y.inputEx.registerType('datetime', DatetimeField, []);
}
