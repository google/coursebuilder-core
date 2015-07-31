if (typeof window._GCB_EMBED === 'undefined') {
  window._GCB_EMBED = {
    embedLibScriptAdded: false,
    jqueryScriptAdded: false,
    stylesheetLinkAdded: false,

    isReady: function() {
      return (
        this.embedLibScriptAdded && this.jqueryScriptAdded &&
        this.stylesheetLinkAdded);
    }
  };
}

(function(pageState) {
  var ENV = JSON.parse('{{ env | js_string }}');
  var EMBED_CSS_URL = ENV['EMBED_CSS_URL'];
  var EMBED_LIB_JS_URL =  ENV['EMBED_LIB_JS_URL'];
  var JQUERY_URL = ENV['JQUERY_URL'];

  function addOnLoadEventListener(f) {
    // TODO(johncox): this breaks in IE8. Need to think about cross-browser
    // compatibility.
    window.addEventListener('load', f);
  }

  function appendEmbedLibScript() {
    if (pageState.embedLibScriptAdded) {
      return;
    }

    appendScript(EMBED_LIB_JS_URL);
    pageState.embedLibScriptAdded = true;
  }

  function appendJqueryScript() {
    if (pageState.jqueryScriptAdded) {
      return;
    }

    appendScript(JQUERY_URL);
    pageState.jqueryScriptAdded = true;
  }

  function appendScript(scriptUri) {
    var scriptTag = document.createElement('script');
    scriptTag.setAttribute('src', scriptUri);
    scriptTag.setAttribute('type', 'text/javascript');
    scriptTag.async = false;
    document.body.appendChild(scriptTag);
  }

  function appendStylesheetLink() {
    if (pageState.stylesheetLinkAdded) {
      return;
    }

    var linkTag = document.createElement('link');
    linkTag.setAttribute('href', EMBED_CSS_URL);
    linkTag.setAttribute('rel', 'stylesheet');
    linkTag.setAttribute('type', 'text/css');
    document.head.appendChild(linkTag);
    pageState.stylesheetLinkAdded = true;
  }

  function onLoadHandler() {
    appendStylesheetLink();
    appendJqueryScript();
    appendEmbedLibScript();  // Requires jQuery.
  }

  function main() {
    addOnLoadEventListener(onLoadHandler);
  }

  main();
})(window._GCB_EMBED);
