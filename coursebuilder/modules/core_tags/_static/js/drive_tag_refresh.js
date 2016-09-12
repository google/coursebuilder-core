/*
 * Manages drive tag controls at tag render time.
 *
 * Open issues:
 *
 * - The structure of the preview frame is not the same as the structure of the
 *   content frame: we write into preview directly; content loads its data via
 *   its src. We patch over the most egregious UI differences, but it's not
 *   possible to make the UI the same in all cases. Rather than chase this
 *   forever, it would be nice to change the structure of the preview frame to
 *   match the structure of the content frame.
 * - Butterbar is sometimes not in frame when messages display. It should always
 *   render a fixed height down the page.
 * - In the case of a refetch of a resource that was removed from the datastore,
 *   the iframe reload can hit the browser cache and fail to show contents until
 *   a hard refresh is issued by the user. We could fix this by appending a
 *   nonce to the URL, but in practice it probably won't be a big deal because
 *   the user can always hard refresh.
 * - Contents of the iframe are not post-processed, so bad behavior can result
 *   (for example, links could open in an origin other than the parent frame,
 *   which throws. In the current implementation we eat these errors; this
 *   is bad UX because it looks like clicking on the link doesn't do anything).
 *   We can't know what all users would like to have happen in all cases, so we
 *   need to decide on a reasonable default behavior and a strategy for allowing
 *   authors to add post-processors or renderers to customize behavior for their
 *   content.
 *
 * @param {jQuery} jQuery the jQuery object to use.
 * @param {function} cbShowMsg function that displays a message in the
 *     butterbar.
 * @param {object} GoogleApiClientTools the GoogleApiClientTools to use for
 *     common client operations.
 * @param {object} GoogleScriptManager the GoogleScriptManager to use for
 *     loading Google dependencies.
 */
window.DriveTagControls = (function(
    jQuery, cbShowMsg, GoogleApiClientTools, GoogleScriptManager) {
  var module = {}

  module._apiApiLoaded = null;
  module._buttonClass = 'gcb-button gcb-button-action gcb-button-author';
  module._contentIframeClass = 'google-drive-content-iframe';
  module._driveApiLoaded;
  module._previewIframeClass = 'google-drive-preview-iframe';
  module._previewIframeClasses = 'google-drive gcb-needs-resizing ' +
                                 module._previewIframeClass;
  module._rawContents = 'rawContents';
  module._refreshClass = 'google-drive-refresh';
  module._refreshText = 'Refresh Google Doc';
  module._revertClass = 'google-drive-revert';
  module._revertText = 'Revert';
  module._saveClass = 'google-drive-save';
  module._saveText = 'Save';
  module._scopes = ['https://www.googleapis.com/auth/drive.readonly'];

  module.main = function() {
    module._addScriptCallbackBindings();
    module._initializeControls();
    GoogleScriptManager.insertAll();
  };

  module.onApiLoad = function() {
    window.gapi.load('auth', module._onApiApiLoaded);
  };

  module.onClientLoad = function() {
    window.gapi.client.load('drive', 'v2', module._onDriveApiLoaded);
  };

  module._activateControls = function() {
    module._getControlDivs().each(function(i, div) {
      var context = $(div);
      if (module._valid(context)) {
        module._enableRefreshButton(context);
      };
    });
  };

  module._addScriptCallbackBindings = function() {
    // Google APIs reference their callbacks by an onload argument in the src
    // attribute of the <script> tags that include them. That onload argument
    // cannot dereference dots, so we must expose a dotless toplevel symbol for
    // it.
    window.gcbGoogleClientOnApiLoad = module.onApiLoad;
    window.gcbGoogleClientOnClientLoad = module.onClientLoad;
  };

  module._allApisLoaded = function() {
    // Whether all required Google APIs are loaded and ready to recieve calls.
    return (
      module._apiApiLoaded &&
      module._driveApiLoaded);
  };

  module._authorize = function(callback) {
    parent.gapi.auth.authorize({
      client_id: module._getClientId(),
      scope: module._scopes,
      immediate: false
    }, callback);
  };

  module._disableRefreshButton = function(context) {
    module._getRefreshButton(context)
      .attr('disabled', 'true')
      .unbind('click');
  };

  module._disableRevertButton = function(context) {
    module._getRevertButton(context)
      .attr('disabled', 'true')
      .unbind('click');
  };

  module._disableSaveButton = function(context) {
    module._getSaveButton(context)
      .attr('disabled', 'true')
      .unbind('click');
  };

  module._downloadDocumentContents = function(context, documentId, url) {
    var handler = GoogleApiClientTools.partial(
      module._onDocumentContentsDownloaded, context, documentId);
    $.ajax({
      error: module._onDocumentContentsDownloadError,
      headers: {
        Authorization: 'Bearer ' + GoogleApiClientTools.getAuthToken()
      },
      success: handler,
      type: 'GET',
      url: url
    });
  };

  module._enableRefreshButton = function(context) {
    module._getRefreshButton(context)
      .on('click', module._onRefreshClick)
      .removeAttr('disabled');
  };

  module._enableRevertButton = function(context) {
    module._getRevertButton(context)
      .on('click', module._onRevertClick)
      .removeAttr('disabled');
  };

  module._enableSaveButton = function(context) {
    module._getSaveButton(context)
      .on('click', module._onSaveClick)
      .removeAttr('disabled');
  };

  module._getApiKey = function(context) {
    return $('div.google-drive-controls', context).data('apiKey');
  };

  module._getClickEventParentContext = function(event) {
    return $(event.target).parent();
  };

  module._getClientId = function(context) {
    return $('div.google-drive-controls', context).data('clientId');
  };

  module._getContentIframe = function(context) {
    return $('iframe.' + module._contentIframeClass, context);
  };

  module._getControlDivs = function() {
    return $('div.google-drive-container');
  };

  module._getDocumentId = function(context) {
    return $('div.google-drive-controls', context).data('documentId');
  };

  module._getPreviewIframe = function(context) {
    return $('iframe.' + module._previewIframeClass, context);
  };

  module._getPreviewIframeContents = function(context) {
    return module._getPreviewIframe(context).data(module._rawContents);
  };

  module._getRefreshButton = function(context) {
    return $('a.' + module._refreshClass, context);
  };

  module._getRevertButton = function(context) {
    return $('a.' + module._revertClass, context);
  };

  module._getSaveButton = function(context) {
    return $('a.' + module._saveClass, context)
  };

  module._getXsrfToken = function(context) {
    return $('div.google-drive-controls', context).data('xsrfToken');
  }

  module._hideContentIframe = function(context) {
    module._getContentIframe(context).hide();
  };

  module._hidePreviewIframe = function(context) {
    module._getPreviewIframe(context).hide();
  };

  module._initializeControls = function() {
    module._getControlDivs().each(function(i, div) {
      var parent = $(div);

      if (!module._valid(parent)) {
        // Hide UX if user is not admin. Even if they bypass this client-side
        // check, we don't transmit the XSRF token so they can't issue CB ops.
        return;
      }

      var refreshButton = $('<a>')
        .addClass(module._buttonClass)
        .addClass(module._refreshClass)
        .attr('disabled', 'true')
        .text(module._refreshText);
      var saveButton = $('<a>')
        .addClass(module._buttonClass)
        .addClass(module._saveClass)
        .attr('disabled', 'true')
        .text(module._saveText);
      var revertButton = $('<a>')
        .addClass(module._buttonClass)
        .addClass(module._revertClass)
        .attr('disabled', 'true')
        .text(module._revertText);
      var previewIframe = $('<iframe>')
        .addClass(module._previewIframeClasses)
        .attr('frameborder', '0')
        .attr('scrolling', 'no')
        .attr('width', '100%')
        .css('display', 'none')
        // Match iframe display of Drive content so the UI doesn't jump. This
        // emulation is nowhere near perfect and there can be numerous display
        // differences (for example, if the target doc is very wide).
        // TODO(johncox): rather than patch over UI differences, find a way to
        // make the structure of the iframes match.
        .css('background-color', 'white')
        .css('padding', '96px')
      parent.prepend(previewIframe);
      parent.prepend(refreshButton);
      parent.prepend(saveButton);
      parent.prepend(revertButton);
    });
  }

  module._onApiApiLoaded = function() {
    module._apiApiLoaded = true;
    module._onGoogleApiLoaded();
  };

  module._onDocumentContentsDownloaded = function(
      context, documentId, contents) {
    if (!documentId && contents) {
      cbShowMsg('Unable to get document contents.');
      return;
    }

    module._setPreviewIframeContents(contents, context);
    module._setControlsStateDownloaded(context);
    cbShowMsg('Showing preview. Please Save or Revert new version.');
  };

  module._onDocumentContentsDownloadError = function(xhr, status, error) {
    // Firefox throws a 'cross-origin request blocked' exception in the admin
    // interface but not this refresh interface. It's not clear why; hint to the
    // user that they can avoid these errors by using a different browser. This
    // error will also display when the XHR fails for other reasons, so leave it
    // somewhat general.
    cbShowMsg(
      'Unable to get document contents. If errors persist and you are using ' +
      'a browser other than Chrome, try Chrome.');
  };

  module._onDriveApiLoaded = function() {
    module._driveApiLoaded = true;
    module._onGoogleApiLoaded();
  };

  module._onFileGet = function(context, file) {
    if (!(file &&
          file.id &&
          file.exportLinks &&
          file.exportLinks['text/html'])) {
      cbShowMsg(
        'Unable to access file; refresh aborted. Use Drive to check your ' +
        'permissions.');
      module._setControlsStateInitial(context);
      return;
    }

    cbShowMsg('Downloading...');
    var url = file.exportLinks['text/html'];

    if (url) {
      module._downloadDocumentContents(context, file.id, url);
    }
  };

  module._onCbPost = function(context, response) {
    var defaultError = 'An error occurred; please try again.';
    var json = GoogleApiClientTools.parseJson(response);

    switch (json.status) {
      case 200:
        cbShowMsg(json.message);
        module._setControlsStateInitial(context);
        break;
      case 400:
      case 403:
        cbShowMsg(json.message);
        module._setControlsStateSaveError(context);
        break;
      case 500:
        cbShowMsg(json.message ? json.message : defaultError);
        module._setControlsStateSaveError(context);
        break;
      default:
        cbShowMsg('Something went wrong. Please reload the page to try again.');
    }
  };

  module._onGoogleApiLoaded = function() {
    if (module._allApisLoaded()) {
      module._activateControls();
    }
  };

  module._onRefreshClick = function(event) {
    var context = module._getClickEventParentContext(event);
    module._disableRefreshButton(context);
    var documentId = module._getDocumentId(context);
    cbShowMsg('Refreshing from Google Drive...');

    if (!GoogleApiClientTools.authorized()) {
      var callback = GoogleApiClientTools.partial(
        GoogleApiClientTools.onAuthorizeResult, function() {
          module._processDownload(context, documentId);
        });
      module._authorize(callback);
    } else {
      module._processDownload(context, documentId);
    }
  };

  module._onRevertClick = function(event) {
    var context = module._getClickEventParentContext(event);
    module._setControlsStateReverted(context);
    cbShowMsg('New version reverted.')
  };

  module._onSaveClick = function(event) {
    cbShowMsg('Saving...');
    var context = module._getClickEventParentContext(event);
    var contents = module._getPreviewIframeContents(context);
    var request = GoogleApiClientTools.stringifyJson({
      contents: contents,
      document_id: module._getDocumentId(context),
      type_id: GoogleApiClientTools.getTypeId(),
      xsrf_token: module._getXsrfToken()
    });
    $.ajax({
      data: {request: request},
      dataType: 'text',
      type: 'PUT',
      url: GoogleApiClientTools.getGoogleDriveTagUrl()
    }).done(function(response) {
      module._onCbPost(context, response);
    });
  };

  module._processDownload = function(context, documentId) {
    // Runs a files.get request for the item with the given documentId string.
    var request = parent.gapi.client.drive.files.get({fileId: documentId});
    request.execute(function(file) {
      module._onFileGet(context, file);
    });
  };

  module._reloadContentIframe = function(context) {
    module._getContentIframe()[0].contentWindow.location.reload(true);
  };

  module._setControlsStateDownloaded = function(context) {
    module._showPreviewIframe(context);
    module._hideContentIframe(context);
    module._enableSaveButton(context);
    module._enableRevertButton(context);
  };

  module._setControlsStateInitial = function(context) {
    module._reloadContentIframe(context);
    module._hidePreviewIframe(context);
    module._showContentIframe(context);
    module._enableRefreshButton(context);
    module._disableSaveButton(context);
    module._disableRevertButton(context);
  };

  module._setControlsStateSaveError = function(context) {
    module._enableRevertButton(context);
    module._disableSaveButton(context);
    module._disableRefreshButton(context);
  };

  module._setControlsStateReverted = function(context) {
    module._hidePreviewIframe(context);
    module._showContentIframe(context);
    module._disableRevertButton(context);
    module._disableSaveButton(context);
    module._enableRefreshButton(context);
  };

  module._setPreviewIframeContents = function(contents, context) {
    module._getPreviewIframe(context)
      .data(module._rawContents, contents)  // To skip serialize on save.
      .contents()
      .find('body')
      .empty()
      .append(contents);
  };

  module._showContentIframe = function(context) {
    module._getContentIframe(context).show();
  };

  module._showPreviewIframe = function(context) {
    module._getPreviewIframe(context).show();
  };

  module._valid = function(context) {
    // Whether or not the rendered tag has enough info for us to operate on it.
    return (
      Boolean(module._getApiKey(context)) &&
      Boolean(module._getClientId(context)) &&
      Boolean(module._getDocumentId(context)) &&
      Boolean(module._getXsrfToken(context)))
  };

  return module;
}($, cbShowMsg, GoogleApiClientTools, GoogleScriptManager));
window.DriveTagControls.main();
