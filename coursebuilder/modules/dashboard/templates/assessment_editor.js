var controller = new AssessmentEditorController(
  Y,
  cb_global.form,
  cb_global.xsrf_token,
  function(s) { return window.confirm(s); },
  cbShowMsg,
  formatServerErrorMessage
);
controller.init();

$(function(){
  var graderSelector = '[name="workflow:grader"]';

  function maybeHidePeerReview() {
    var peerReview = $('#peer-review-group');
    if ($(graderSelector).val() == 'auto') {
      peerReview.hide();
    } else {
      peerReview.show();
    }
  }

  maybeHidePeerReview();
  $(document.body).on('change', graderSelector, function(event){
    maybeHidePeerReview();
  });
});
