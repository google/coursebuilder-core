/**
 * Script run inside the iframe which presents the lesson editor inside the
 * lesson view
 */
$(function() {
  var currentHeight = 0;

  function postMessage(action, data) {
    var payload = {action: action};
    if (data) {
      payload.data = data;
    }
    window.parent.postMessage(payload, window.location.origin);
  }

  function maybeResize() {
    var height = $('html').height();
    if (height != currentHeight) {
      postMessage('in-place-lesson-editor-height-changed', {
        height: height
      });
      currentHeight = height;
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
