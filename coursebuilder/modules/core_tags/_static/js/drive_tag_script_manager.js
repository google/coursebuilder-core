/*
 * Common utility methods used across clients of Google APIs.
 *
 * @param {object} JSON JSON processing module.
 */
window.GoogleApiClientTools = (function(JSON) {
  module = {};

  module._typeId = 'google-drive';
  // TODO(nretallack): This duplicates code in
  // modules/dashboard/resources/js/view.js.
  // XSSI prefix must be kept in sync with models/transforms.py.
  module._xssiPrefix = ")]}'";

  module.authorized = function() {
    return Boolean(module.getAuthToken());
  };

  module.getAuthToken = function() {
    var token = parent.gapi.auth.getToken();
    if (token) {
      return token.access_token;
    }
  };

  module.getGoogleDriveTagUrl = function() {
    return 'modules/core_tags/googledrivetag';
  };

  module.getTypeId = function() {
    return module._typeId;
  };

  module.onAuthorizeResult = function(callback, authResult) {
    if (authResult && !authResult.error) {
      callback();
    }
  };

  module.parseJson = function(s) {
    return JSON.parse(s.replace(module._xssiPrefix, ''));
  };

  module.partial = function(fn, varArgs) {
    // Partially binds a function. Same implementation as in Google Closure
    // libraries: accept a fn and variadic args. Clone the args, then append
    // additional args to existing ones.
    var args = Array.prototype.slice.call(arguments, 1);
    return function() {
      var newArgs = args.slice();
      newArgs.push.apply(newArgs, arguments);
      return fn.apply(this, newArgs);
    };
  };

  module.stringifyJson = function(o) {
    return JSON.stringify(o);
  }

  return module;
}(JSON));


/*
 * Inserts <script> tags for Google APIs and sets callbacks on them.
 */
window.GoogleScriptManager = (function($) {
  var module = {};

  module._googleApiScriptCallbackName = 'gcbGoogleClientOnApiLoad';
  module._googleApiScriptId = "gcb-google-client-api";
  module._googleApiScriptUrl = "https://apis.google.com/js/api.js";
  module._googleClientScriptCallbackName = 'gcbGoogleClientOnClientLoad';
  module._googleClientScriptUrl = "https://apis.google.com/js/client.js";
  module._googleClientScriptId = "gcb-google-client-client";

  module.insertAll = function() {
    // Inserts api.js and client.js with the callbacks as named above.
    module._insertScriptElement(
      module._googleApiScriptId, module._googleApiScriptUrl,
      module._googleApiScriptCallbackName);
    module._insertScriptElement(
      module._googleClientScriptId, module._googleClientScriptUrl,
      module._googleClientScriptCallbackName);
  };

  module._createScriptElement = function(id, url, onloadFnName) {
    return element = $('<script>')
      .attr('id', id)
      .attr('src', url + '?onload=' + onloadFnName)
      .attr('type', 'text/javascript');
  };

  module._exists = function(jQueryResultArray) {
    return jQueryResultArray.length > 0;
  };

  module._insertScriptElement = function(id, url, onloadFnName) {
    if (module._exists($('#' + id))) {
      return;
    }

    var script = module._createScriptElement(id, url, onloadFnName);
    $('body').append(script);
  }

  return module;
}(jQuery));
