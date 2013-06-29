var controller = new AssessmentEditorController(
    Y,
    cb_global.form,
    cb_global.xsrf_token,
    function(s) { return window.confirm(s); },
    cbShowMsg,
    formatServerErrorMessage
);
controller.init();