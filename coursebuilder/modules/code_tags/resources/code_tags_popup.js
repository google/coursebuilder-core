$("select[name='mode']").change(function() {
  cb_global.form.inputsNames.code.setMode($(this).val());
});
