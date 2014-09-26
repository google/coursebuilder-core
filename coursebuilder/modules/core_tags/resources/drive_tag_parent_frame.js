/*
 * Parent frame code for Google Drive tag functionality.
 *
 * Requires child in google_tag_child_frame.js. The parent is loaded after
 * oeditor.js. It accepts commands from the child frame, which is rendered as an
 * InputEx lightbox, does work, and relays results back to the child.
 *
 * It's weird that we're using postMessage here but we still reach in between
 * the frames sometimes. We could have avoided using postMessage, but in that
 * case the complexity of scoping jQuery operations would have been exposed over
 * and over, and getting it wrong would be very easy (and sometimes very
 * subtle). We could avoid this much more compactly by partially binding jQuery,
 * which results in compact code that does black magic. This approach is weird,
 * but it is very obvious at every callsite, which is the least bad alternative.
 *
 * TODO(johncox): go through when writing tests and make private things actually
 * private.
 */

/*
 * Post message dispatcher for messages between this frame and its children.
 * Also contains factories for the messages themselves, which should be used
 * to compose postMessage calls.
 */
window.Dispatcher = (function() {
  var module = {};

  module.EVENT_NAME = 'message';
  module.MESSAGE_TARGET_CONFIGURE = 'configure';
  module.MESSAGE_TARGET_DOWNLOAD = 'download'
  module.MESSAGE_TARGET_INITIALIZE = 'initialize';
  module.MESSAGE_TARGET_INITIALIZED = 'initialized';
  module.MESSAGE_TARGET_PICK = 'pick';
  module.MESSAGE_TARGET_PICKED = 'picked';

  module._bindings = {};

  module.addBinding = function(targetName, fn) {
    module._bindings[targetName] = fn;
  };

  module.getOrigin = function() {
    return window.location.protocol + '//' + window.location.host;
  };

  module.handlePostMessage = function(event) {
    if (!Dispatcher._checkPostMessage(event)) {
      return;
    }

    var targetFn = module._getTargetFn(event.originalEvent.data.target);
    if (targetFn) {
      targetFn(event);
    }
  };

  module.makeConfigureMessage = function(apiKey, clientId, typeId, xsrfToken) {
    return {
      target: module.MESSAGE_TARGET_CONFIGURE,
      args: {
        apiKey: apiKey,
        clientId: clientId,
        typeId: typeId,
        xsrfToken: xsrfToken
      }
    }
  };

  module.makeDownloadMessage = function(documentId) {
    return {
      target: module.MESSAGE_TARGET_DOWNLOAD,
      args: {
        documentId: documentId
      }
    }
  };

  module.makeInitializeMessage = function() {
    return {
      target: module.MESSAGE_TARGET_INITIALIZE
    }
  };

  module.makeInitializedMessage = function() {
    return {
      target: module.MESSAGE_TARGET_INITIALIZED
    }
  };

  module.makePickMessage = function() {
    return {
      target: module.MESSAGE_TARGET_PICK,
    }
  };

  module.makePickedMessage = function(documentId) {
    return {
      target: module.MESSAGE_TARGET_PICKED,
      args: {
        documentId: documentId
      }
    }
  };

  module._checkInternal = function(event) {
    return Boolean(
      event.originalEvent &&
      event.originalEvent.data &&
      event.originalEvent.data.target &&
      event.originalEvent.origin);
  };

  module._checkOrigin = function(origin) {
    return (origin === module.getOrigin());
  };

  module._checkPostMessage = function(event) {
    return (module._checkInternal(event) && module._checkValid(event))
  };

  module._checkValid = function(event) {
    return Boolean(
      module._checkOrigin(event.originalEvent.origin) &&
      event.originalEvent.data.target);
  };

  module._getTargetFn = function(targetName) {
    return module._bindings[targetName];
  };

  return module;
}());

/*
 * Inserts <script> tags for Google APIs and sets callbacks on them.
 */
window.GoogleScriptManager = (function() {
  var module = {};

  module._googleApiScriptCallbackName = 'gcbGoogleClientOnApiLoad';
  module._googleApiScriptId = "gcb-google-client-api";
  module._googleApiScriptUrl = "https://apis.google.com/js/api.js";
  module._googleClientScriptCallbackName = 'gcbGoogleClientOnClientLoad';
  module._googleClientScriptUrl = "https://apis.google.com/js/client.js";
  module._googleClientScriptId = "gcb-google-client-client";

  module.insertAll = function() {
    // Inserts api.js and client.js with the callbacks as named above.
    var parent = module.getScriptParentElement();

    if (module._exists(parent)) {
      return;
    }

    parent = module._insertScriptParentElement();
    var apiScript = module._createScriptElement(
      module._googleApiScriptId, module._googleApiScriptUrl,
      module._googleApiScriptCallbackName);
    var clientScript = module._createScriptElement(
      module._googleClientScriptId, module._googleClientScriptUrl,
      module._googleClientScriptCallbackName);
    parent.append(apiScript);
    parent.append(clientScript);
  };

  module.getScriptParentElement = function() {
    return $("#" + module._scriptParentElementId);
  };

  module._createScriptElement = function(id, url, onloadFnName) {
    return element = $('<script>')
      .attr('id', id)
      .attr('src', url + '?onload=' + onloadFnName)
      .attr('type', 'text/javascript');
  };

  module._createScriptParentElement = function() {
    return $("<div>")
      .attr('id', module._scriptParentElementId)
      .css('display', 'none');
  };

  module._exists = function(jQueryResultArray) {
    return jQueryResultArray.length > 0;
  };

  module._insertScriptParentElement = function() {
    var element = module._createScriptParentElement();
    $('body').append(element);
    return element;
  };

  return module;
}($));

/*
 * Parent frame code for InputEx lightbox child for the Google Drive custom tag.
 *
 * The child is rendered in a lightbox and accepts user input. The child relays
 * this to the parent via postMessage; the parent talks to Google and relays
 * results back to the child via postMessage. We put most behavior in the parent
 * because major UX (the Drive picker) needs to be rendered at the parent level,
 * and you get better UX for error reporting (the admin butterbar) at the parent
 * level.
 */
window.GcbGoogleDriveTagParent = (function($, JSON) {
  var module = {};

  module._apiKey;
  module._apiApiLoaded = false;
  module._clientId;
  module._driveApiLoaded = false;
  module._editorIframeId = "modal-editor-iframe";
  module._oldArrayToPrettyJsonString;
  module._oldObjectToPrettyJsonString;
  module._pickerApiLoaded = false;
  module._scopes = ["https://www.googleapis.com/auth/drive.readonly"];
  module._typeId;
  module._xsrfToken;
  // XSSI prefix must be kept in sync with models/transforms.py.
  module._xssiPrefix = ")]}'";

  module._PICKER_LOADED = 'loaded';
  module._PICKER_PICKED = 'picked'

  module.onApiLoad = function() {
    top.gapi.load('auth', module._onApiApiLoaded);
    top.gapi.load('picker', module._onPickerApiLoaded);
  };

  module.onClientLoad = function() {
    top.gapi.client.load('drive', 'v2', module._onDriveApiLoaded);
  };

  module._addDispatcherBindings = function () {
    window.Dispatcher.addBinding(
      window.Dispatcher.MESSAGE_TARGET_CONFIGURE,
      GcbGoogleDriveTagParent._handleConfigureMessage)
    window.Dispatcher.addBinding(
      window.Dispatcher.MESSAGE_TARGET_DOWNLOAD,
      GcbGoogleDriveTagParent._handleDownloadMessage)
    window.Dispatcher.addBinding(
      window.Dispatcher.MESSAGE_TARGET_INITIALIZE,
      GcbGoogleDriveTagParent._handleInitializeMessage)
    window.Dispatcher.addBinding(
      window.Dispatcher.MESSAGE_TARGET_PICK,
      GcbGoogleDriveTagParent._handlePickMessage)
  };

  module._addScriptCallbackBindings = function() {
    // Google APIs reference their callbacks by an onload argument in the src
    // attribute of the <script> tags that include them. That onload argument
    // cannot dereference dots, so we must expose a dotless toplevel symbol for
    // it.
    top.gcbGoogleClientOnApiLoad = module.onApiLoad;
    top.gcbGoogleClientOnClientLoad = module.onClientLoad;
  };

  module._allApisLoaded = function() {
    // Whether all required Google APIs are loaded and ready to recieve calls.
    return (
      module._apiApiLoaded &&
      module._driveApiLoaded &&
      module._pickerApiLoaded);
  }

  module._authorize = function(callback) {
    top.gapi.auth.authorize({
      client_id: module._getClientId(),
      scope: module._scopes,
      immediate: false
    }, callback);
  };

  module._authorized = function() {
    return Boolean(module._getAuthToken());
  };

  module._configured = function() {
    return (
      Boolean(module._getApiKey()) &&
      Boolean(module._getClientId()) &&
      Boolean(module._getXsrfToken()))
  };

  module._downloadDocumentContents = function(documentId, url) {
    // Downloads Google drive document contents given their URL.
    var handler = module._partial(
      module._onDocumentContentsDownloaded, documentId);
    $.ajax({
      error: handler,
      headers: {
        Authorization: 'Bearer ' + module._getAuthToken()
      },
      success: handler,
      type: 'GET',
      url: url
    });
  };

  module._getApiKey = function() {
    return module._apiKey;
  };

  module._getAuthToken = function() {
    var token = top.gapi.auth.getToken();
    if (token) {
      return token.access_token;
    }
  };

  module._getClientId = function() {
    return module._clientId;
  };

  module._getGoogleDriveTagUrl = function() {
    var slug = top.window.location.pathname.split('/')[1];
    return '/' + slug + '/modules/core_tags/googledrivetag';
  };

  module._getInputExIframeWindow = function() {
    return $("#" + module._editorIframeId)[0].contentWindow;
  };

  module._getTypeId = function() {
    return module._typeId;
  };

  module._getXsrfToken = function() {
    return module._xsrfToken;
  };

  module._handleConfigureMessage = function(event) {
    // Handles message sent from child with configuration data for requests. We
    // must have this data before we can talk securely with either Google or
    // with Course Builder.
    if (module._configured()) {
      return;
    }

    if (!(event.originalEvent.data.args.apiKey &&
          event.originalEvent.data.args.clientId &&
          event.originalEvent.data.args.typeId &&
          event.originalEvent.data.args.xsrfToken)) {
      return;
    }

    module._setApiKey(event.originalEvent.data.args.apiKey);
    module._setClientId(event.originalEvent.data.args.clientId);
    module._setTypeId(event.originalEvent.data.args.typeId);
    module._setXsrfToken(event.originalEvent.data.args.xsrfToken);
  };

  module._handleDownloadMessage = function(event) {
    // Handles message sent from child when user clicks Save.

    // TODO(johncox): find out why this isn't firing on some clicks.
    var documentId = event.originalEvent.data.args.documentId;
    if (!documentId) {
      cbShowMsg('No Google Drive document specified; skipping download')
      return;
    }

    cbShowMsg('Starting download...')
    if (!module._authorized()) {
      var callback = module._partial(
        module._onAuthorizeResult,
        module._partial(module._processDownload, documentId));
      module._authorize(callback);
    } else {
      module._processDownload(documentId);
    }
  };

  module._handleInitializeMessage = function(unused_event) {
    // Handles child iframe message sent to indicate parent should initialize
    // itself for use. When we're done initializing, we need to signal back to
    // the child that we're ready for input, and the child needs to not send
    // input until this happens or input will vanish.
    GoogleScriptManager.insertAll()
  };

  module._handlePickMessage = function(unused_event) {
    // Handles child iframe message sent when user clicks Pick button.
    if (!module._authorized()) {
      var callback = module._partial(
        module._onAuthorizeResult, module._showPicker);
      module._authorize(callback);
    } else {
      module._showPicker();
    }
  };

  module._onApiApiLoaded = function() {
    module._apiApiLoaded = true;
    module._onGoogleApiLoaded();
  };

  module._onAuthorizeResult = function(callback, authResult) {
    if (authResult && !authResult.error) {
      callback();
    }
  };

  module._onCbPost = function(response) {
    var defaultError = 'An error occurred; please try again.';
    var json = module._parseJson(response);

    switch (json.status) {
      case 200:
      case 400:
      case 403:
        cbShowMsg(json.message);
        break;
      case 500:
        cbShowMsg(json.message ? json.message : defaultError);
        break;
      default:
        cbShowMsg(defaultError);
    }
  };

  module._onDocumentContentsDownloaded = function(documentId, contents) {
    // Process the downloaded contents of a Drive document.
    if (!documentId && contents) {
      cbShowMsg('Unable to get document contents.');
      return;
    }

    cbShowMsg('Saving file...')
    // Serialization in $.ajax afoul of an infinite recursion with the InputEx
    // patches to Array and Object in place, so we remove/restore them around
    // the call.
    module._removeInputExFunctions();
    var request = JSON.stringify({
      contents: contents,
      document_id: documentId,
      type_id: module._getTypeId(),
      xsrf_token: module._getXsrfToken()
    });
    $.ajax({
      data: {request: request},
      dataType: 'text',
      type: 'PUT',
      url: module._getGoogleDriveTagUrl()
    }).done(module._onCbPost);
    module._restoreInputExFunctions();
  };

  module._onDriveApiLoaded = function() {
    module._driveApiLoaded = true;
    module._onGoogleApiLoaded();
  };

  module._onFileGet = function(file) {
    // Downloads the contents of a file based on the results of a files.get op.
    if (!(file &&
          file.id &&
          file.exportLinks &&
          file.exportLinks['text/html'])) {
      cbShowMsg('Unable to access file; download aborted.');
      return;
    }

    cbShowMsg('Downloading...');
    var url = file.exportLinks['text/html'];

    if (url) {
      module._downloadDocumentContents(
        file.id, url, module._onDocumentContentsDownloaded);
    }
  };

  module._onGoogleApiLoaded = function() {
    // When all Google APIs are done loading, signal the child iframe that we're
    // ready to accept user actions.
    if (module._allApisLoaded()) {
      module._getInputExIframeWindow().postMessage(
        window.Dispatcher.makeInitializedMessage(),
        window.Dispatcher.getOrigin());
    }
  };

  module._onPickerApiLoaded = function() {
    module._pickerApiLoaded = true;
    module._onGoogleApiLoaded();
  };

  module._onPick = function(data) {
    if (data.action !== module._PICKER_LOADED) {
      // _onPick is called on load for the picker, on cancel, and when a user
      // picks an item. Restore except in case of load; in that case we are in
      // the context of the picker and want to leave the functions swapped out
      // until control is returned to InputEx.
      module._restoreInputExFunctions();
    }

    if (data.action === module._PICKER_PICKED) {
      var documentId = data.docs[0].id;
      if (documentId) {
        module._getInputExIframeWindow().postMessage(
          window.Dispatcher.makePickedMessage(documentId),
          window.Dispatcher.getOrigin());
      }
    }
  };

  module._parseJson = function(s) {
    return JSON.parse(s.replace(module._xssiPrefix, ''));
  };

  module._partial = function(fn, varArgs) {
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

  module._processDownload = function(documentId) {
    // Runs a files.get request for the item with the given documentId string.
    var request = top.gapi.client.drive.files.get({fileId: documentId});
    request.execute(module._onFileGet);
  };

  module._setApiKey = function(value) {
    module._apiKey = value;
  };

  module._setClientId = function(value) {
    module._clientId = value;
  };

  module._setTypeId = function(value) {
    module._typeId = value;
  };

  module._setXsrfToken = function(value) {
    module._xsrfToken = value;
  };

  module._showPicker = function() {
    var picker = new top.google.picker.PickerBuilder()
      .addView(new top.google.picker.View(top.google.picker.ViewId.DOCUMENTS))
      .enableFeature(top.google.picker.Feature.NAV_HIDDEN)
      .setAppId(module._getClientId())
      .setCallback(module._onPick)
      .setDeveloperKey(module._getApiKey())
      .setOAuthToken(module._getAuthToken())
      .setOrigin(window.Dispatcher.getOrigin())
      .build();
    module._removeInputExFunctions();
    picker.setVisible(true);
  };

  module._removeInputExFunctions = function() {
    // InputEx adds a JSON prettifier to Array and Object. This works fine for
    // InputEx code but blows up the Google Picker's setVisible(). Before we can
    // make the picker visible, we have to move these functions out of the way.
    module._oldArrayToPrettyJsonString = Array.prototype.toPrettyJSONString;
    module._oldObjectToPrettyJsonString = Object.prototype.toPrettyJSONString;
    delete Array.prototype.toPrettyJSONString;
    delete Object.prototype.toPrettyJSONString;
  };

  module._restoreInputExFunctions = function() {
    // Put back the items removed by _removeInputExFunctions.
    Array.prototype.toPrettyJSONString = module._oldObjectToPrettyJsonString;
    Object.prototype.toPrettyJSONString = module._oldObjectToPrettyJsonString;
  };

  module._setUpParentFrame = function() {
    top.GcbGoogleDriveTagParent._addDispatcherBindings();
    top.GcbGoogleDriveTagParent._addScriptCallbackBindings();
    $(window).on(
      window.Dispatcher.EVENT_NAME, window.Dispatcher.handlePostMessage);
  };

  return module;
}($, JSON));
window.GcbGoogleDriveTagParent._setUpParentFrame();
