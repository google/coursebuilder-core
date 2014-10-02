$(function() {
  var notes = (
      'Note: Uploading translation files will take several seconds, ' +
      'and may time out.  If this happens, you can try ' +
      'importing fewer languages at a time, or use the command ' +
      'line tool.  The tool and its instructions are in your ' +
      'CourseBuilder download in the file tools/i18n/i18n.py.');
  $('#cb-oeditor-form > fieldset')
      .append('<hr>')
      .append($('<div/>').text(notes))
      .append('<div id="translation_messages"/>');

  cb_global.onSaveComplete = function(payload) {
    $('#translation_messages')
        .empty()
        .append('<hr>');
    for (var i = 0; i < payload.messages.length; i++) {
      $('#translation_messages')
          .append($('<div/>').text(payload.messages[i]));
    }
  };
});
