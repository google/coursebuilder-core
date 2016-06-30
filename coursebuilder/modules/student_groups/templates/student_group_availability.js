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

  function setVisibility(groupKey) {
    if (groupKey) {
      $('.course-wide-scope').hide()
      $('.group-scope').show()
    } else {
      $('.course-wide-scope').show()
      $('.group-scope').hide()
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
      cb_global.get_url = cb_global.original_get_url + event.target.value;
      startValueLoad(cb_global);
      setVisibility(event.target.value);
      cb_global.editorControls.populateForm();
    });
  }

  // Re-populating form using official channels has the side effect that all
  // the extra js (this file) is re-imported.  Prevent exponential explosion
  // of registering handlers.
  if (typeof(gcbStudentGroupAvailabilityInitialized) == 'undefined') {
    init();
    setVisibility();
  }
  gcbStudentGroupAvailabilityInitialized = true;
});
