initSaQuestionEditor(cb_global.form);
cb_global.onSaveClick = function() {
  setQuestionDescriptionIfEmpty(cb_global.form);
  return true;
}
