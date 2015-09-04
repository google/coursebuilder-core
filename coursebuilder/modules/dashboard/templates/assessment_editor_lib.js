function AssessmentEditorController(Y, inputExForm, xsrfToken, confirm, notify,
    formatError) {
  this.Y = Y;
  this.inputExForm = inputExForm;
  this.xsrfToken = xsrfToken;
  this.confirm = confirm;
  this.notify = notify;
  this.formatError = formatError;
}
AssessmentEditorController.prototype.exportToHTMLAssessment = function() {
  var that = this;
  var key = this.Y.one('div.keyHolder').get('text');
  var requestSave = {
    'payload': this.inputExForm.getValue(),
    'key': key,
    'xsrf_token': this.xsrfToken
  };

  this.notify("Saving...");
  this.Y.io('rest/course/asessment/export', {
    method: 'put',
    data: {
      'request': JSON.stringify(requestSave)
    },
    on: {
      complete: function(transactionId, response, args) {
        var json;
        if (response && response.responseText) {
          json = parseJson(response.responseText);
        } else {
          that.notify('The server did not respond. ' +
              'Please reload the page to try again.');
          return;
        }

        if (json.status != 200) {
          that.notify(that.formatError(json.status, json.message));
          return;
        }
        that.notify(json.message);
      }
    }
  });
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
};
AssessmentEditorController.prototype.eraseHTMLContent = function() {
  this.findRte(this.inputExForm.inputs[0].inputs, 'html_content')
      .setValue('');
  this.findRte(this.inputExForm.inputs[1].inputs, 'html_review_form')
      .setValue('');
};
AssessmentEditorController.prototype.hideHTMLEditors = function() {
  this.Y.one('div.html-content').get('parentNode').addClass('hidden');
  this.Y.one('div.html-review-form').get('parentNode').addClass('hidden');
  this.Y.one('div.assessment-editor-check-answers').get('parentNode')
      .addClass('hidden');
};
AssessmentEditorController.prototype.hideJSEditors = function() {
  this.Y.one('div.content').get('parentNode').addClass('hidden');
  this.Y.one('div.review-form').get('parentNode').addClass('hidden');
};
AssessmentEditorController.prototype.showJSEditors = function() {
  this.Y.one('div.content').get('parentNode').removeClass('hidden');
  this.Y.one('div.review-form').get('parentNode').removeClass('hidden');
};
AssessmentEditorController.prototype.showButton = function(label, action) {
  var that = this;
  var button = this.Y.Node.create(
      '<button class="oeditor-control">' + label + '</button>');
  button.on('click', function(evt) {
    evt.preventDefault();
    action.apply(that);
  })
  var buttonDiv = this.Y.Node.create(
      '<div class="assessment-editor-button-holder"/>');
  buttonDiv.append(button);
  this.Y.one('#cb-oeditor-form > fieldset > legend').insert(buttonDiv, 'after');
};
AssessmentEditorController.prototype.removeButtons = function() {
  this.Y.one('#cb-oeditor-form > fieldset > div.assessment-editor-button-holder')
      .remove();
};
AssessmentEditorController.prototype.showRevertButton = function() {
  this.showButton('Revert to Javascript assessment', this.revertToJSAssessment);
};
AssessmentEditorController.prototype.isJSAssessment = function() {
  return this.Y.one('textarea[name=content]').get('value') ||
      this.Y.one('textarea[name=review_form]').get('value');
};
AssessmentEditorController.prototype.isHTMLAssessment = function() {
  return this.Y.one('textarea[name=html_content]').get('value') ||
      this.Y.one('textarea[name=html_review_form]').get('value');
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
  } else {
    this.hideJSEditors();
  }
};
