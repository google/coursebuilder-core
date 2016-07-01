$(function() {
  // Awful, awful hack.  We are wrapping the course-level availability page,
  // and that page has some custom JavaScript that counts on seeing its
  // schema at the top level under the form fields, which is reasonable.
  // However, we want to have a convenient way to mark student-groups fields
  // and course-level fields for show/hide based on the user's selection
  // on the which-set-are-we-affecting picker.  Thus, we need to manually
  // go into the form fields here and add some CSS class stuff.  Can't do
  // that at schema construction time, because the course-level stuff must
  // be at the top of the schema, so anything we rely on there will affect
  // everything.  Sigh.

  function getPreviousSettingsFor() {
    if (typeof(gcbPreviousSettingsFor) == 'undefined') {
      // The initial "Settings For" <select> state is always the "Course"
      // default <option>, an empty student_group_id string.
      gcbPreviousSettingsFor = '';
    }
    return gcbPreviousSettingsFor;
  }

  function setSettingsFor(nextSettingsFor) {
    gcbPreviousSettingsFor = nextSettingsFor;

    if (nextSettingsFor) {
      // For a specific student group, as opposed to the course-wide defaults,
      // nextSettingsFor is a decimal integer as a string.
      $('.course-wide-scope').hide()
      $('.group-scope').show()
    } else {
      // An empty string indicates the the default "Course" <option>, for
      // course-wide settings, as opposed to settings for a specific student
      // group.
      $('.course-wide-scope').show()
      $('.group-scope').hide()
    }
  }

  function getLastStudentGroup(cbGlobal) {
    var lastStudentGroup = null;
    // First, try to obtain student_group from the last-saved form value.
    if (cbGlobal.lastSavedFormValue) {
      lastStudentGroup = cbGlobal.lastSavedFormValue.student_group;
    }
    // If no student_group was obtained from the last-saved form value (and
    // an empty string *is* a valid value, indicating the "Course" default
    // <option>), obtain the last-selected "Settings For" value (which is
    // also either the "Course" default or a student group ID integer as a
    // string.
    if ((!lastStudentGroup) && (lastStudentGroup != '')) {
      lastStudentGroup = getPreviousSettingsFor();
    }
    return lastStudentGroup;
  }

  function okToSetSettingsFor(cbGlobal, nextSettingsFor) {
    if (cbGlobal.is_deleted) {
      return true;
    }

    // student_group does not represent actual form state until the point
    // where the [Save] button is actually pressed. At that time, it indicates
    // *what* state the form actually contains (course-wide availability
    // settings or those for the specified student group) that will be saved.
    var nextFormValue = cbGlobal.form.getValue();
    var nextStudentGroup = nextFormValue.student_group;

    // Do not have deepEquals() compare the student_group value, since it is,
    // by definition, changed every time a different <option> is chosen from
    // the "Settings For" <select>. Instead, set it to the last-saved form
    // value to which nextFormValue is being compared, for the purposes of
    // determining if any actual form state needs saving before switching.
    var lastStudentGroup = getLastStudentGroup(cbGlobal);
    nextFormValue.student_group = lastStudentGroup;

    var okToSwitch = deepEquals(cbGlobal.lastSavedFormValue, nextFormValue);
    nextFormValue.student_group = nextStudentGroup;

    if (!okToSwitch) {
      var prefix;
      if (lastStudentGroup) {
        prefix = 'These student group availability settings';
      } else {
        prefix = 'These course-wide availablity settings';
      }
      okToSwitch = confirm(prefix + ' have unsaved changes that will be' +
          ' lost if you switch.\n\nOK to switch anyway?');
    }

    if (okToSwitch) {
      // The student_group value *should* already be nextSettingsFor, but
      // just in case, force it to the supplied event.target.value of the
      // "Settings For" <select>.
      nextFormValue.student_group = nextSettingsFor;
      cbGlobal.lastSavedFormValue = nextFormValue;
    }
    return okToSwitch;
  }

  function selectSettingsFor(cbGlobal, settingsForSelect) {
    var nextSettingsFor = settingsForSelect.value;

    if (okToSetSettingsFor(cbGlobal, nextSettingsFor)) {
      cbGlobal.get_url = cbGlobal.original_get_url + nextSettingsFor;
      startValueLoad(cbGlobal);
      setSettingsFor(nextSettingsFor);
      cbGlobal.editorControls.populateForm();
    } else {
      settingsForSelect.value = getLastStudentGroup(cbGlobal);
    }
  }

  function init() {
    // Save original query URL for simplicity in building variants for
    // individual groups.
    cb_global.original_get_url = cb_global.get_url;

    // Set indents on things needing to be indented.
    var contentElements = (cb_global.form.inputsNames.
        student_group_settings.inputsNames.element_settings);
    $.each(contentElements.subFields, function() {
      var rowData = this.inputsNames;
      if (rowData.indent.getValue()) {
        $(rowData.name.wrapEl).addClass('indent');
      }
    });

    // Move the what-set-are-we-affecting picker to be the first element on
    // the form.  It's not first because, again, the course-wide availability
    // stuff necessarily comes first.
    var fieldset = cb_global.form.fieldset;
    var picker = cb_global.form.inputsNames['student_group'];
    fieldset.insertBefore(picker.divEl, fieldset.firstChild);

    // When the select field changes, need to repopulate form w/ values for
    // that particular group.  (Don't want to have to load all groups up
    // front when this form loads)
    $(picker.el).on('change', function(event){
      selectSettingsFor(cb_global, event.target);
    });
  }

  // Re-populating form using official channels has the side effect that all
  // the extra js (this file) is re-imported.  Prevent exponential explosion
  // of registering handlers.
  if (typeof(gcbStudentGroupAvailabilityInitialized) == 'undefined') {
    init();
    // The "Settings For" <select> state always starts out with the "Course"
    // default <option> (an empty student_group_id string) selected.
    setSettingsFor('');
  }
  gcbStudentGroupAvailabilityInitialized = true;
});
