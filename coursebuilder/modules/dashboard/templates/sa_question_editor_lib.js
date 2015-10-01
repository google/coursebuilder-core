function saUpdateToggleFeedbackButtons(saQuestionEditorForm) {
  addToggleFeedbackButton(
      saQuestionEditorForm.getFieldByName('defaultFeedback'));

  $.each(saQuestionEditorForm.getFieldByName('graders').subFields, function() {
    addToggleFeedbackButton(this.getFieldByName('feedback'));
  });
}
function initSaQuestionEditor(saQuestionEditorForm) {
  saUpdateToggleFeedbackButtons(saQuestionEditorForm);

  saQuestionEditorForm.getFieldByName('graders').on('updated', function() {
    saUpdateToggleFeedbackButtons(saQuestionEditorForm);
  });
}
