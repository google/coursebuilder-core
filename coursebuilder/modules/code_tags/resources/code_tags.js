CodeMirror.modeURL = "/static/codemirror/mode/%N/%N.js";
$('code.codemirror-container-readonly').each(function() {
  var code = $(this).text();
  $(this).empty();
  var cmInstance = CodeMirror(this, {
    value: code,
    lineNumbers: true,
    readOnly: true
  });
  var mode = $(this).data('mode');
  cmInstance.setOption('mode', mode);
  CodeMirror.autoLoadMode(cmInstance, mode);
});
