(function() {
  // protect against double-loading
  if (window.gcb) {
    return;
  }

  window.gcb = {
    _XSSI_PREFIX: ")]}'",
    parseJsonResponse: function(responseString) {
      return JSON.parse(responseString.replace(this._XSSI_PREFIX, ''));
    }
  };

  var modules = {
    // TODO(jorr): Bring Butterbar in here.
    collapse: {
      js: ['_static/collapse/collapse.js'],
      css: ['_static/collapse/collapse.css']
    },
    list: {
      js: [],
      css: ['_static/list/list.css']
    },
    lightbox: {
      js: ['_static/lightbox/lightbox.js'],
      css: ['_static/lightbox/lightbox.css']
    },
    'toggle-button': {
      js: [],
      css: ['_static/toggle-button/toggle-button.css']
    }
  };
  var base = '/modules/core_ui/';

  for (var name in modules) {
    if (! modules.hasOwnProperty(name)) {
      continue;
    }
    var module = modules[name];
    for (var i = 0; i < module.css.length; i++) {
      var uri = module.css[i];
      var link = document.createElement('link');
      link.setAttribute('rel', 'stylesheet');
      link.setAttribute('href', base + uri);
      document.head.appendChild(link);
    }
  }

  $(function() {
    $.each(modules, function(_, module) {
      $.each(module.js, function(_, uri) {
        $('body').append($('<script>').attr('src', base + uri));
      });
    });
  });
})();
