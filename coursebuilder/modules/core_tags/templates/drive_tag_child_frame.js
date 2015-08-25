/*
 * Child frame code for Google Drive tag functionality.
 *
 * Requires parent in google_tag_child_parent.js. The child is rendered as an
 * InputEx lightbox. It relays commands to the parent, which does actual work
 * and relays results back to the child.
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
 *
 * @param {jQuery} $ jQuery.
 * @param {object} cb_global the globals object we're adding a save click
 *     handler to. Ideally we'd pass the handler symbol, but it can be
 *     undefined. Do not use this object to access other children; inject the
 *     desired children directly (like form and schema).
 * @param {function} disableAllControlButtons function that disables all InputEx
 *     controls in the popup.
 * @param {function} enableAllControlButtons function that enables all InputEx
 *     controls in the popup.
 * @param {object} form the InputEx form displayed in the lightbox.
 * @param {object} schema the InputEx schema of that form.
 */

window.GcbGoogleDriveTagChild = (function (
    $, cb_global, disableAllControlButtons, enableAllControlButtons, form,
    schema) {
  var module = {};

  module._pickElementId = 'gcb-google-drive-tag-lightbox-control';
  module._apiKey;
  module._clientId;
  module._initializeHandled = false;
  module._typeId;
  module._xsrfToken;

  module.main = function() {
    // Lifecycle is: we configure our UI in a disabled state. We transmit
    // security info (XSRF token, etc.) to the parent page and tell it to set
    // itself up, which requires loading Google APIs via script tags. When all
    // of those are loaded hte parent signals to us that we're ready to run, and
    // we enable our UI.
    if (!module._isConfigured()) {
      return;
    }

    module._insertPickLink();
    module._disableControls();
    module._setUpFrames();
  };

  module._disableControls = function() {
    // There are two levels here: the InputEx level, which owns Save and Close,
    // and our level, which owns Pick. This is annoying and it would be nice to
    // have one interface to all of this, but it's a lot of ugly work to put all
    // buttons into the InputEx schema so we special-case here. First, disable
    // Save and Close at the InputEx level.
    disableAllControlButtons(form);
    // We want to allow users to Close if we never hear back from the parent
    // that we can let them Pick or Save.
    module._enableCloseButtonElement();
    // Now, take care of Pick. Also, we register a custom click handler on Save
    // which we need to remove.
    module._disablePickButtonElement();
  };

  module._disablePickButtonElement = function() {
    module._getPickButtonElement()
      .addClass('inputEx-Button-disabled')
      .off('click');
  };

  module._enableCloseButtonElement = function() {
    // Have to work at the InputEx level here rather than using jQuery so we can
    // get at methods on an InputEx object.
    form.buttons[1].enable();
  };

  module._enableControls = function() {
    // There are two levels here: the InputEx level, which owns Save and Close,
    // and our level, which owns Pick. This is annoying and it would be nice to
    // have one interface to all of this, but it's a lot of ugly work to put all
    // buttons into the InputEx schema so we special-case here. First, enable
    // Save and Close at the InputEx level.
    enableAllControlButtons(form);
    // Enable Pick and put our Save click event back.
    module._enablePickButtonElement();
  };

  module._enablePickButtonElement = function() {
    module._getPickButtonElement()
      .removeClass('inputEx-Button-disabled')
      .off('click')  // Belt-and-suspenders: ensure no duplicate events exist.
      .on('click', module._pick);
  };

  module._getApiKey = function() {
    return module._apiKey;
  };

  module._getClientId = function() {
    return module._clientId;
  };

  module._getDocumentId = function() {
    return module._getParentElement().val();
  };

  module._getInitializeHandled = function() {
    return module._initializeHandled;
  }

  module._getParentElement = function() {
    return $('[name="document-id"]');
  };

  module._getPickButtonElement = function() {
    return $('#' + module._pickElementId);
  };

  module._getTypeId = function() {
    return module._typeId;
  };

  module._getXsrfToken = function() {
    return module._xsrfToken;
  };

  module._handleInitializedMessage = function() {
    // Parent frame may send multiple messages; disregard after the first has
    // been recieved and handled successfully.
    if (module._isInitialized()) {
      return;
    }

    module._enableControls();
    module._registerSaveHandler();
    module._setInitializeHandled(true);
  };

  module._handlePickedMessage = function(data) {
    var documentId = data.originalEvent.data.args.documentId;
    if (documentId) {
      module._setDocumentId(data.originalEvent.data.args.documentId);
    }
  };

  module._insertPickLink = function() {
    var element = $('<a>')
      .addClass('inputEx-Button')
      .attr('id', module._pickElementId)
      .on('click', module._pick)
      .text('Pick');
    module._getParentElement().parent().append(element);
  };

  module._isConfigured = function() {
    return Boolean(module._getApiKey()) && Boolean(module._getClientId());
  };

  module._isInitialized = function() {
    return Boolean(module._getInitializeHandled());
  };

  module._pick = function() {
    top.postMessage(
      top.Dispatcher.makePickMessage(), top.Dispatcher.getOrigin());
  };

  module._processExtraSchemaDictValues = function() {
    if (schema.properties.attributes) {
      var properties = schema.properties.attributes.properties;
    } else {
      var properties = schema.properties;
    }

    var extraValues = properties['document-id']['_inputex'];
    module._apiKey = extraValues['api-key'];
    module._clientId = extraValues['client-id'];
    module._typeId = extraValues['type-id'];
    module._xsrfToken = extraValues['xsrf-token'];
  };

  module._registerSaveHandler = function() {
    // Adds our save handler to the oeditor save stack.
    cb_global.onSaveClick = module._save;
  }

  module._save = function() {
    top.postMessage(
      top.Dispatcher.makeDownloadMessage(module._getDocumentId()),
      top.Dispatcher.getOrigin());
    return true;
  };

  module._setDocumentId = function(value) {
    module._getParentElement().val(value);
  };

  module._setInitializeHandled = function(value) {
    module._initializeHandled = value;
  };

  module._setUpFrames = function() {
    // Configure our own frame to receive communication back from the parent.
    top.Dispatcher.addBinding(
      top.Dispatcher.MESSAGE_TARGET_INITIALIZED,
      GcbGoogleDriveTagChild._handleInitializedMessage);
    top.Dispatcher.addBinding(
      top.Dispatcher.MESSAGE_TARGET_PICKED,
      GcbGoogleDriveTagChild._handlePickedMessage);
    $(window).on(top.Dispatcher.EVENT_NAME, top.Dispatcher.handlePostMessage);

    // Send messages to parent to configure it.
    top.postMessage(
      top.Dispatcher.makeConfigureMessage(
        module._getApiKey(), module._getClientId(), module._getTypeId(),
        module._getXsrfToken()),
      top.Dispatcher.getOrigin());
    top.postMessage(
      top.Dispatcher.makeInitializeMessage(), top.Dispatcher.getOrigin());
  };

  return module;
}(jQuery, cb_global, disableAllControlButtons, enableAllControlButtons,
  cb_global.form, cb_global.schema));
window.GcbGoogleDriveTagChild._processExtraSchemaDictValues();
