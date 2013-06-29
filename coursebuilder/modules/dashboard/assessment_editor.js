var controller = new AssessmentEditorController(
    cb_global.form,
    function(s) { return window.confirm(s); }
);
controller.init();