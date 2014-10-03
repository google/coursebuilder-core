$(function() {
  var notes = (
      'Note: Downloading translation files will take several seconds, ' +
      'and may time out.  If this happens, you can try ' +
      'exporting fewer languages at a time, or use the command ' +
      'line tool.  See .../modules/i18n_dashboard/jobs.py for ' +
      'complete instructions and sample command lines.');
  $('#cb-oeditor-form > fieldset')
      .append('<hr>')
      .append($('<div/>').text(notes));


  cb_global.onSaveComplete = function() {
    cbShowMsgAutoHide(
        'Download of .zip file started; open your browser\'s ' +
        'Downloads window to track progress.')

    var requestData = JSON.stringify({
      'payload': JSON.stringify(cb_global.form.getValue()),
      'xsrf_token': cb_global.xsrf_token
    });

    var f = document.createElement('form');
    f.method = 'POST';
    f.action = cb_global.save_url;
    var i = document.createElement('input');
    i.name = 'request';
    i.setAttribute('value', requestData);
    f.appendChild(i);
    f.submit();
  };
});
