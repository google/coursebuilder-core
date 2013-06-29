function AssessmentEditorController(inputExForm, confirm) {
  this.inputExForm = inputExForm;
  this.confirm = confirm;
}
AssessmentEditorController.prototype.exportToHTMLAssessment = function() {
  // TODO(jorr): Implement exporting
};
AssessmentEditorController.prototype.revertToJSAssessment = function() {
  var CONFIRM_MESSAGE =
    'Do you want to discard your assessment and review questions, ' +
    'and add questions to this assessment using JavaScript syntax? ' +
    'Your assessment and review question set-up will be lost, but ' +
    'the rest of your assessment set-up, as well as your questions ' +
    'in the question bank, will be unaffected.';

  if (this.hasHTMLContent() && !this.confirm(CONFIRM_MESSAGE)) {
    return;
  }

  this.eraseHTMLContent();
  this.hideHTMLEditors();
  this.removeButtons();
  this.showJSEditors();
  this.showExportButton();
};
AssessmentEditorController.prototype.eraseHTMLContent = function() {
  this.findRte(this.inputExForm.inputs[0].inputs, 'html_content')
      .setValue('');
  this.findRte(this.inputExForm.inputs[1].inputs, 'html_review_form')
      .setValue('');
};
AssessmentEditorController.prototype.hideHTMLEditors = function() {
  Y.one('div.html-content').get('parentNode').addClass('hidden');
  Y.one('div.html-review-form').get('parentNode').addClass('hidden');
  Y.one('div.assessment-editor-check-answers').get('parentNode')
      .addClass('hidden');
};
AssessmentEditorController.prototype.hideJSEditors = function() {
  Y.one('div.content').get('parentNode').addClass('hidden');
  Y.one('div.review-form').get('parentNode').addClass('hidden');
};
AssessmentEditorController.prototype.showJSEditors = function() {
  Y.one('div.content').get('parentNode').removeClass('hidden');
  Y.one('div.review-form').get('parentNode').removeClass('hidden');
};
AssessmentEditorController.prototype.showButton = function(label, action) {
  var that = this;
  var button = Y.Node.create(
      '<button class="oeditor-control">' + label + '</button>');
  button.on('click', function(evt) {
    evt.preventDefault();
    action.apply(that);
  })
  var buttonDiv = Y.Node.create(
      '<div class="assessment-editor-button-holder"/>');
  buttonDiv.append(button);
  Y.one('#cb-oeditor-form > fieldset > legend').insert(buttonDiv, 'after');
};
AssessmentEditorController.prototype.removeButtons = function() {
  Y.one('#cb-oeditor-form > fieldset > div.assessment-editor-button-holder')
      .remove();
};
AssessmentEditorController.prototype.showExportButton = function() {
  // TODO(jorr): Uncomment the following line when export is added
  // this.showButton('Export to HTML assessment', this.exportToHTMLAssessment);
};
AssessmentEditorController.prototype.showRevertButton = function() {
  this.showButton('Revert to Javascript assessment', this.revertToJSAssessment);
};
AssessmentEditorController.prototype.isJSAssessment = function() {
  return Y.one('textarea[name=content]').get('value') ||
      Y.one('textarea[name=review_form]').get('value');
};
AssessmentEditorController.prototype.isHTMLAssessment = function() {
  return Y.one('textarea[name=html_content]').get('value') ||
      Y.one('textarea[name=html_review_form]').get('value');
};
AssessmentEditorController.prototype.findRte = function(inputs, rteName) {
  for (var i = 0; i < inputs.length; i++) {
    var input = inputs[i];
    if (input.options && input.options.name == rteName) {
      return input;
    }
  }
  throw 'Cannot find rich text editor: ' + rteName;
};
AssessmentEditorController.prototype.hasHTMLContent = function() {
  return this.findRte(
          this.inputExForm.inputs[0].inputs, 'html_content').getValue() ||
      this.findRte(
          this.inputExForm.inputs[1].inputs, 'html_review_form').getValue();
};
AssessmentEditorController.prototype.init = function() {
  if (this.isJSAssessment()) {
    this.hideHTMLEditors();
    this.showExportButton();
  } else if(this.isHTMLAssessment()) {
    this.hideJSEditors();
  } else {
    this.hideJSEditors();
    this.showRevertButton();
  }
};
