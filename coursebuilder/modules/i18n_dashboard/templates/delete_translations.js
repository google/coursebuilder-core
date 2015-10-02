$(function() {
  var notes = (
      'Note: Deleting translations will take several seconds, ' +
      'and may time out.  If this happens, you can try ' +
      'deleting fewer languages at a time, or use the command ' +
      'line tool.  See .../modules/i18n_dashboard/jobs.py for ' +
      'complete instructions and sample command lines.');
  $('#cb-oeditor-form > fieldset')
      .append('<hr>')
      .append($('<div/>').text(notes));


  var saveCbShowMsg = cbShowMsg;
  cb_global.onSaveClick = function() {
    do_delete = confirm('Really delete translations for these languages?');
    if (do_delete) {
      // Here, we can't change the "saving..." message in OEditor, but
      // we can at least ensure that it disappears briskly.
      cbShowMsg = function() { ; }
    }
    return do_delete;
  }

  cb_global.onSaveComplete = function() {
    cbShowMsg = saveCbShowMsg;
  }
});
