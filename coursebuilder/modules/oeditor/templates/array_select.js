function bindArraySelectField(Y) {
  var ArraySelectField = function(options) {
    ArraySelectField.superclass.constructor.call(this, options);
  };

  Y.extend(ArraySelectField, Y.inputEx.SelectField, {
    setValue: function(val, sendUpdatedEvt){
      if (Y.Lang.isArray(val)) {
        // setValue is called with an array when the framework does a GET
        // to populate the form initially.  At that point, we add choices
        // to our DOM.
        //
        this.options.choices = val;
        for (var i = 0; i < val.length; i++){
          this.addChoice(val[i])
        }
      } else {
        // setValue is also called at other times, but with a single value
        // (the index of the selected item in the choice list).  In this
        // situation, forward the call to the framework so the selection
        // action is recognized and recorded normally.
        ArraySelectField.superclass.setValue.call(this, val, sendUpdatedEvt);
      }
    },
    getValue: function(){
      // Return the choices set, rather than the .value member of the selected
      // item.  This behavior causes our schemas to match for input and output.
      for (var i = 0; i < this.options.choices.length; i++){
        this.options.choices[i].selected = false;
      }
      if (this.el.selectedIndex >= 0){
        this.options.choices[this.el.selectedIndex].selected = true;
      }
      return this.options.choices;
    }
  });

  Y.inputEx.registerType('array-select', ArraySelectField, []);
}
