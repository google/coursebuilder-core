if (typeof window._GCB_EMBED === 'undefined') {
  window._GCB_EMBED = {
    embedCssLinkAdded: false,
    embedLibScriptAdded: false,
    jqueryScriptAdded: false,
    materialIconsCssLinkAdded: false,
    robotoCssLinkAdded: false,

    isReady: function() {
      return (
        this.embedCssLinkAdded && this.embedLibScriptAdded &&
        this.jqueryScriptAdded && this.materialIconsCssLinkAdded &&
        this.robotoCssLinkAdded);
    }
  };
}

(function(pageState) {
  var ENV = JSON.parse('{{ env | js_string }}');
  var EMBED_CSS_URL = ENV['embed_css_url'];
  var EMBED_LIB_JS_URL =  ENV['embed_lib_js_url'];
  var JQUERY_URL = ENV['jquery_url'];
  var MATERIAL_ICONS_URL = ENV['material_icons_url'];
  var ROBOTO_URL = ENV['roboto_url'];

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

  function appendEmbedCssLink() {
    if (pageState.embedCssLinkAdded) {
      return;
    }

    appendStylesheetLink(EMBED_CSS_URL);
    pageState.embedCssLinkAdded = true;
  }

  function appendMaterialIconsCssLink() {
    if (pageState.materialIconsCssLinkAdded) {
      return;
    }

    appendStylesheetLink(MATERIAL_ICONS_URL);
    pageState.materialIconsCssLinkAdded = true;
  }

  function appendRobotoCssLink() {
    if (pageState.robotoCssLinkAdded) {
      return;
    }

    appendStylesheetLink(ROBOTO_URL);
    pageState.robotoCssLinkAdded = true;
  }

  function appendStylesheetLink(linkUrl) {
    if (pageState.stylesheetLinkAdded) {
      return;
    }

    var linkTag = document.createElement('link');
    linkTag.setAttribute('href', linkUrl);
    linkTag.setAttribute('rel', 'stylesheet');
    linkTag.setAttribute('type', 'text/css');
    document.head.appendChild(linkTag);
  }

  function onLoadHandler() {
    appendEmbedCssLink();
    appendMaterialIconsCssLink();
    appendRobotoCssLink();
    appendJqueryScript();
    appendEmbedLibScript();  // Requires jQuery.
  }

  function main() {
    addOnLoadEventListener(onLoadHandler);
  }

  main();
})(window._GCB_EMBED);
