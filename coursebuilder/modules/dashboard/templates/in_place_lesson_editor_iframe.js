/**
 * Script run inside the iframe which presents the lesson editor inside the
 * lesson view
 */
$(function() {
  // Extra vertical padding at the bottom of the ifrane. This is primarily to
  // leave room for the oeditor's edit image popup.
  VERTICAL_PADDING = 80;

  var currentHeight = 0;

  function postMessage(action, data) {
    var payload = {action: action};
    if (data) {
      payload.data = data;
    }
    window.parent.postMessage(payload, window.location.origin);
  }

  function maybeResize() {
    var height = $('body').height();
    if (height != currentHeight) {
      postMessage('in-place-lesson-editor-height-changed', {
        height: height + VERTICAL_PADDING
      });
      currentHeight = height + VERTICAL_PADDING;
    }
  }

  function onSaveComplete(payload) {
    postMessage('in-place-lesson-editor-saved');
  }

  function onCloseClick() {
    postMessage('in-place-lesson-editor-close');
    return false;
  }

  function init() {
    cb_global.onSaveComplete = onSaveComplete;
    cb_global.onCloseClick = onCloseClick;
    setInterval(maybeResize, 100);
    postMessage('in-place-lesson-editor-loaded');
  }

  init();
});
