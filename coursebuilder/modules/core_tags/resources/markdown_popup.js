var codeEditor = new CodeEditorControl(
    document.getElementsByName("markdown")[0]);
// force code editor to load the current mode
codeEditor.setMode("markdown");

$("select[name='mode']").change(function() {
  codeEditor.setMode($(this).val());
});
