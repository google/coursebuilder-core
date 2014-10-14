var codeEditor = new CodeEditorControl(
    document.getElementsByName("code")[0]);
// force code editor to load the current mode
codeEditor.setMode($("select[name='mode']").val());

$("select[name='mode']").change(function() {
  codeEditor.setMode($(this).val());
});
