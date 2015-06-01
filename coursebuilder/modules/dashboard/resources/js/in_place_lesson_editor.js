/**
 * Script run in the lesson view page to manage in-page lesson editing.
 */
$(function() {
  var lessonDiv;
  var editorDiv;

  function openEditorIframe(button) {
    if (iframe) {
      cbShowMsg('In place editing already open. You can only edit one lesson ' +
          'at a time.');
      return;
    }

    lessonDiv = button.closest('.gcb-aside');

    editorDiv = $(
        '<div class="in-place-lesson-editor">' +
        '  <iframe class="hidden"></iframe>' +
        '  <div id="modal-editor" class="hidden">' +
        '    <div class="background"></div>' +
        '  </div>' +
        '  <div class="ajax-spinner">' +
        '    <div class="background"></div>' +
        '    <span class="spinner md md-settings md-spin"></span>' +
        '  </div>' +
        '</div>');

    var iframe = editorDiv.find('iframe');
    var lessonId = button.data('lessonId');
    var src = 'dashboard?' + $.param({
      key: lessonId,
      action: 'in_place_lesson_editor'
    });
    iframe.attr('src', src);

    editorDiv.height(lessonDiv.height());
    lessonDiv.before(editorDiv);
    lessonDiv.hide();
  }

  function onEditButtonClick(evt) {
    openEditorIframe($(evt.target));
  }

  function dispatchPostMessageCallbacks(payload) {
    var action = payload.action;
    if (action == 'in-place-lesson-editor-loaded') {
      onEditorLoaded();
    } else if (action == 'in-place-lesson-editor-close') {
      onEditorClosed();
    } else if (action == 'in-place-lesson-editor-saved') {
      onEditorSaved();
    } else if (action == 'in-place-lesson-editor-height-changed') {
      onHeightChanged(payload.data.height);
    }
  }

  function onEditorLoaded() {
    editorDiv.find('.ajax-spinner').addClass('hidden');
    editorDiv.find('iframe').removeClass('hidden');
  }

  function onEditorClosed() {
    lessonDiv.show();
    editorDiv.remove();
    lessonDiv = null;
    editorDiv = null;
  }

  function onEditorSaved() {
    window.location.reload(true);
  }

  function onHeightChanged(newHeight) {
    editorDiv.height(newHeight);
  }

  function bind() {
    $('button.gcb-edit-lesson-button').click(onEditButtonClick);

    $(window).on('message', function(evt) {
      var evt = evt.originalEvent;
      if (evt.origin == window.location.origin &&
          evt.source == editorDiv.find('iframe').get(0).contentWindow) {
        dispatchPostMessageCallbacks(evt.data);
      }
    });
  }

  function init() {
    bind();
  }

  init();
});
