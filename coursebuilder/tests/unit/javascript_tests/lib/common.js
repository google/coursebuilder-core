/**
 * Utilities for Karma testing.
 */
(function() {

  /**
   * Polyfill for Function.bind.
   */
  var bindPolyfill = function() {
    var theFunction = this;
    var thisArg = arguments[0];
    var posArgs = Array.prototype.slice.call(arguments, 1);
    return function() {
      theFunction.apply(thisArg, posArgs);
    }
  };
  Function.prototype.bind = Function.prototype.bind || bindPolyfill;

})();
