$(function() {
  var notes = (
      'Note: Uploading translation files will take several seconds, ' +
      'and may time out.  If this happens, you can try ' +
      'importing fewer languages at a time, or use the command ' +
      'line tool.  See .../modules/i18n_dashboard/jobs.py for ' +
      'complete instructions and sample command lines.');
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
          .append($('<p/>').text(payload.messages[i]));
    }
  };
});
