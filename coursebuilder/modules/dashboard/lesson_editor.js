/*
 * Initialize JavaScript functionality specific to the unit/lesson editor. The
 * functionality itself is contained in unit_lesson_editor_lib.js.
 */

var activityImporter = new ActivityImporter(
    Y, cb_global, cbShowMsg, formatServerErrorMessage,
    function(s) {return confirm(s);});
activityImporter.insertImportAssignmentButton();
