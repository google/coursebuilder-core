/**
 * This file provides a shim which can be used by an externally hosted page
 * to require a user to be in session in Course Builder as soon as the page
 * loads.
 *
 * Usage:
 *
 * Deploy this file (ensure-session.js) on some public location on the web. In
 * most cases it will be convenient to deploy it on the same server as your host
 * pages.
 *
 * Include the following code snippet in your host page:
 *
 * <script src="include-the-path-to/ensure-session.js"></script>
 * <script>
 *   gcbSession.login({
 *     cbHost: 'https://the-cb-server.appspot.com',
 *     redirect: false
 *   });
 * </script>
 *
 * You must pass the base URL of your Course Builder host (note, no traling
 * slash) as an argument. If you set the optional argument "redirect" to true
 * then the page will redirect to Course Builder for login if needed as soon
 * as the host page loads. Otherwise, if login is needed, the scipt will insert
 * a button in the page and when the user clicks this button they are taken to
 * the Course Builder login. The button is pages immediately below the
 * gcbSession.login call, so place this script tage in the place in your page
 * where you want a login button to be shown.
 */
window.gcbSession = (function(document) {
  var DATA_URI = '/modules/embed/v1/ensure_session_data.js';
  var ENSURE_SESSION_URI = '/modules/embed/v1/ensure_session';

  function appendScript(scriptUri, scriptBody) {
    document.write('<script');
    if (scriptUri) {
      document.write(' src="' + encodeURI(scriptUri) + '" ');
    }
    document.write('>');
    if (scriptBody) {
      document.write(scriptBody);
    }
    document.write('</script>');
  }

  function appendButton() {
    document.write(
        '<link rel="stylesheet"' +
        '    href="//fonts.googleapis.com/icon?family=Material+Icons">' +
        '<style>' +
        '  .cb-embed-icon {' +
        '    padding-right: 6px;' +
        '    vertical-align: middle;' +
        '  }' +
        '  .cb-embed-sign-in-button {' +
        '    -webkit-font-smoothing: antialiased;' +
        '    background-color: rgb(0, 150, 136);' +
        '    border-radius: 3px;' +
        '    border: 0;' +
        '    box-shadow: 0 2px 5px 0 rgba(0,0,0,.26);' +
        '    box-sizing: border-box;' +
        '    color: rgba(255, 255, 255, 0.87);' +
        '    cursor: inherit;' +
        '    display: inline-block;' +
        '    font-weight: 500;' +
        '    font: 14px RobotoDraft, Roboto, \'Helvetica Neue\', sans-serif;' +
        '    line-height: 36px;' +
        '    margin: 6px 8px;' +
        '    min-height: 36px;' +
        '    min-width: 64px;' +
        '    outline: 0;' +
        '    overflow: hidden;' +
        '    padding: 0 14px 0 8px;' +
        '    position: relative;' +
        '    text-align: center;' +
        '    text-decoration: none;' +
        '    text-transform: uppercase;' +
        '    vertical-align: middle;' +
        '    white-space: nowrap;' +
        '  }' +
        '  .cb-embed-sign-in-container {' +
        '    cursor: pointer;' +
        '    display: inline-block;' +
        '    min-height: 48px;' +
        '  }' +
        '  .cb-embed-sign-in-content {' +
        '    font-weight: 700;' +
        '  }' +
        '</style>' +
        '<div class="cb-embed-sign-in-container">' +
        '  <button class="cb-embed-sign-in-button"' +
        '      onclick="window.gcbSession._doRedirect()">' +
        '    <i class="material-icons cb-embed-icon">play_arrow</i>' +
        '    <span class="cb-embed-sign-in-content">Start</span>' +
        '  </button>' +
        '</div>');
  }

  var gcbSession = {
    _inSession : false,

    login: function(options) {
      this._cbHost = options.cbHost;
      if (! this._cbHost) {
        console.error('Mandatory argument cbHost missing.');
        return;
      }
      this._redirect = options.redirect || false;

      var dataUrl = this._cbHost + DATA_URI;
      appendScript(dataUrl, null);

      var scriptBody = 'window.gcbSession._ensureLogin();';
      appendScript(null, scriptBody);
    },

    _doRedirect() {
      var ensureSessionUrl = this._cbHost + ENSURE_SESSION_URI +
          '?continue=' + encodeURIComponent(window.location);
      window.location = ensureSessionUrl;
    },

    _ensureLogin() {
      if (this._inSession) {
        return;
      }

      if (this._redirect) {
        this._doRedirect();
      } else {
        appendButton();
      }
    }
  };

  return gcbSession;
})(document);
