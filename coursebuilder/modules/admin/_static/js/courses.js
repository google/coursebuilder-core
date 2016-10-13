// JavaScript event-notification callbacks run asynchronously behind the
// scenes.  Integration tests that verify this page need to wait for the
// callbacks to complete before checking whether the callbacks have completed,
// or else we have a race condition and a flaky test.  This variable is
// incremented by background operations upon completion so that tests can
// block until the relevant callbacks have finished.
//
var gcbAdminOperationCount = 0;

$(function() {

  var AddCoursePanel = function(title, xsrfToken, email, templateCourse) {
    this._xsrfToken = xsrfToken;
    this._documentBody = $(document.body);
    this._lightbox = new window.gcb.Lightbox();
    this._form = $(
        '<div class="add-course-panel">' +
        '  <h2 class="title"></h2>' +
        '  <div class="form-row">' +
        '    <label>Title</label>' +
        '    <input type="text" name="title"' +
        '        placeholder="e.g. New Course">' +
        '  </div>' +
        '  <div class="form-row">' +
        '    <label>URL Component</label>' +
        '    <input type="text" name="name"' +
        '        placeholder="e.g. new_course">' +
        '  </div>' +
        '  <div class="form-row">' +
        '    <label>Admin</label>' +
        '    <input type="text" name="admin_email"' +
        '        placeholder="e.g. admin@example.com">' +
        '  </div>' +
        '  <div class="controls">' +
        '    <button class="gcb-button save-button">OK</button>' +
        '    <button class="gcb-button cancel-button">Cancel</button>' +
        '  </div>' +
        '  <div class="spinner hidden">' +
        '    <div class="background"></div>' +
        '    <span class="icon spinner md md-settings md-spin"></span>' +
        '  </div>' +
        '</div>');
    this._form.find('.title').text(title);
    this._nameInput = this._form.find('[name="name"]');
    this._titleInput = this._form.find('[name="title"]');
    this._adminEmailInput = this._form.find('[name="admin_email"]');
    this._form.find('.save-button').click(this._save.bind(this));
    this._form.find('.cancel-button').click(this._close.bind(this));
    this._spinner = this._form.find('.spinner');

    this._adminEmailInput.val(email);
    this._templateCourse = templateCourse;
  };
  AddCoursePanel.prototype.open = function() {
    this._lightbox
      .bindTo(this._documentBody)
      .setContent(this._form)
      .show();
  };
  AddCoursePanel.prototype._save = function() {
    this._showSpinner();
    var payload = {
      name: this._nameInput.val(),
      title: this._titleInput.val(),
      admin_email: this._adminEmailInput.val(),
      template_course: this._templateCourse
    };
    var request = {
      xsrf_token: this._xsrfToken,
      payload: JSON.stringify(payload)
    };
    $.ajax('/rest/courses/item', {
      method: 'PUT',
      data: {request: JSON.stringify(request)},
      dataType: 'text',
      error: this._saveError.bind(this),
      success: this._saveSuccess.bind(this),
      complete: this._saveComplete.bind(this)
    });
  };
  AddCoursePanel.prototype._showSpinner = function() {
    this._spinner.removeClass('hidden');
  };
  AddCoursePanel.prototype._hideSpinner = function() {
    this._spinner.addClass('hidden');
  };
  AddCoursePanel.prototype._close = function() {
    this._lightbox.close();
  };
  AddCoursePanel.prototype._saveError = function() {
    cbShowMsg('Something went wrong. Please try again.');
  };
  AddCoursePanel.prototype._saveSuccess = function(data) {
    data = window.gcb.parseJsonResponse(data);
    console.log(data);
    if (data.status != 200) {
      var message = data.message || 'Something went wrong. Please try again.';
      cbShowMsg(message);
      return;
    }
    window.location.reload();
  };
  AddCoursePanel.prototype._saveComplete = function() {
    this._hideSpinner();
  };

  function addCourse() {
    var xsrfToken = $('#add_course').data('xsrfToken');
    var email = $('#add_course').data('email');
    new AddCoursePanel('Add Course...', xsrfToken, email, null).open();
  }
  function addSampleCourse() {
    var xsrfToken = $('#add_course').data('xsrfToken');
    var email = $('#add_course').data('email');
    new AddCoursePanel('Add Sample Course...', xsrfToken, email, 'sample')
        .open();
  }

  function setMultiCourseActionAllowed(isAvailable) {
    if (isAvailable) {
      $('#multi_course_actions').removeClass('inactive-container').
          find(".multi-course-actions").removeClass('inactive');
    } else {
      $('#multi_course_actions').addClass('inactive-container').
          find(".multi-course-actions").addClass('inactive');
    }
  }

  function _allColHdrsSel() {
    return 'thead > tr > th';
  }
  function _someColHdrsSel(extra) {
    return _allColHdrsSel() + extra;
  }
  function _colHdrSelById(id) {
    return _someColHdrsSel('#' + id);
  }
  function _fixedHdrTableSel() {
    return '.gcb-list .table-container > table#courses_list.fixed.thead';
  }
  function _coursesListTableSel() {
    return '.gcb-list table#courses_list:not(.fixed)';
  }
  function _coursesListColHdrsSel(extra) {
    return _coursesListTableSel() + ' > ' + _someColHdrsSel(extra);
  }
  function _coursesListColHdrSelById(id) {
    return _coursesListTableSel() + ' > ' + _colHdrSelById(id);
  }
  function _fixedAndScrolled($someTh) {
    // _fixedAndScrolled(), given some <th> in the <thead> of either:
    //   * the non-scrolling 'table.fixed.thead', or
    //   * the actual <table> containing the <tbody> rows to be sorted,
    // returns an object containing these jQuery objects:
    //   $table: the "real" <table> containing the <tbody> rows that scroll
    //     (those to be sorted, course checkboxes checked, etc.).
    //   $th: <th> of interest in the <thead> of $table (indicating the column
    //     to sort by, the "all courses" checkbox, etc.).
    //   $theadTable: the '.fixed.thead' <table> with only column headers.
    //   $theadTh: the <th> in $theadTable corresponding to $th.
    //
    // Since CSS classes on <th> elements actually store the "sorted by"
    // clicked and "hinted at" hover states, both the original and "cloned"
    // <th> elements representing sortable columens need to contain the same
    // state at all times. Similarly, the original #all_courses_select checkbox
    // and its clone should both contain the same checked state.
    //
    // This function is necessary because sortCourseRows() is invoked when
    // the <th> of some sortable column in the courses list table is clicked.
    // However, this <th> may be in the 'table.fixed.thead' clone or it
    // might be in the "real" <table> that contains the <tbody> to be sorted.
    // _fixedAndScrolled() determines which of the two was actually
    // clicked and returns both.
    //
    // hintNextSort() and unhintSort() suffer the same dilemma when they are
    // hovered over, as does the #all_courses_select checkbox when it is
    // clicked.
    var idx = $someTh.index();
    var hdrsSel = _allColHdrsSel();
    var parts = {};

    var $someTable = $someTh.closest('table');

    if ($someTable.hasClass('thead')) {
      // Supplied <th> is inside the '.table-container > table.fixed.thead'.
      parts.$table = $($someTable.siblings('.table-scroller')
          .find('table:not(.fixed)').get()[0]);
      parts.$th = $(parts.$table.find(hdrsSel).get()[idx]);
      parts.$theadTable = $someTable;
      parts.$theadTh = $someTh;
    } else {
      // Supplied <th> is inside the "real" '.table-scroller > table'.
      parts.$table = $someTable;
      parts.$th = $someTh;
      parts.$theadTable = $($someTable.closest('.table-container')
          .find('table.thead').get()[0]);
      parts.$theadTh = $(parts.$theadTable.find(hdrsSel).get()[idx]);
    }
    return parts;
  }
  function _allCourseSelectSel() {
    if (typeof(gcbAllCourseSelectSel) == 'undefined') {
      gcbAllCourseSelectSel = _someColHdrsSel(
          '.gcb-list-select-course #all_courses_select');
    }
    return gcbAllCourseSelectSel;
  }
  function _fixedHdrAllCourseSelectSel() {
    if (typeof(gcbFixedHdrAllCourseSelectSel) == 'undefined') {
      gcbFixedHdrAllCourseSelectSel =_fixedHdrTableSel() +
          ' > ' + _allCourseSelectSel();
    }
    return gcbFixedHdrAllCourseSelectSel;
  }
  function _coursesListAllCourseSelectSel() {
    if (typeof(gcbCoursesListAllCourseSelectSel) == 'undefined') {
      gcbCoursesListAllCourseSelectSel = _coursesListTableSel() +
          ' > ' + _allCourseSelectSel();
    }
    return gcbCoursesListAllCourseSelectSel;
  }
  function _scrolledCourseCheckboxesSel() {
    if (typeof(gcbCoursesListScrolledCheckboxesSel) == 'undefined') {
      gcbCoursesListScrolledCheckboxesSel = _coursesListTableSel() +
          ' > tbody > tr > td.gcb-list-select-course .gcb-course-checkbox';
    }
    return gcbCoursesListScrolledCheckboxesSel;
  }
  function selectAll() {
    // This gets called _after_ checkbox is checked, so 'indeterminate' has
    // been cleared for *one* of the #all_courses_select checkboxes (either
    // the "real" checkbox in '.table-scroller > table' or its "clone" in
    // table.fixed.thead. Rather than try to determine which one was clicked,
    // just clear 'indeterminate' on both.
    $(_coursesListAllCourseSelectSel()).prop('indeterminate', false);
    $(_fixedHdrAllCourseSelectSel()).prop('indeterminate', false);

    // Now examine the rest of the course checkboxes to determine how to
    // update those. If any is unchecked, check all of them; if all are
    // checked, uncheck them all instead.
    var newState = false;

    // NOTE: The .gcb-course-checkbox checkboxes do not suffer the same
    // "cloned" issues as the #all_courses_select checkbox, since the <tbody>
    // containing them was deleted from all of the table.fixed clones.
    $(_scrolledCourseCheckboxesSel()).each(function(_, checkbox){
      newState |= !checkbox.checked;
    });
    $(_scrolledCourseCheckboxesSel()).prop('checked', newState);

    // Now update both the "real" checkbox in '.table-scroller > table' and
    // its "clone" in table.fixed.thead. Only 'checked' is updated.
    // 'indeterminate' is left cleared, since all of the course checkboxes
    // now have an identical state.
    $(_coursesListAllCourseSelectSel()).prop('checked', newState);
    $(_fixedHdrAllCourseSelectSel()).prop('checked', newState);

    setMultiCourseActionAllowed(newState);
    gcbAdminOperationCount++;
  }
  function selectCourse() {
    // Having clicked the selection checkbox for a single course, set the state
    // of the all-courses selection checkbox accordingly.  All-on -> on;
    // all-off -> off; mixed -> indeterminate.
    var anyChecked = false;
    var anyUnchecked = false;

    // (see selectAll() about .gcb-course-checkbox checkboxes not being cloned)
    $(_scrolledCourseCheckboxesSel()).each(function(_, checkbox){
      anyChecked |= checkbox.checked;
      anyUnchecked |= !checkbox.checked;
    });

    // (see selectAll() about #all_courses_select checkbox clones)
    if (anyChecked && anyUnchecked) {
      $(_coursesListAllCourseSelectSel()).prop('indeterminate', true);
      $(_fixedHdrAllCourseSelectSel()).prop('indeterminate', true);
    } else {
      $(_coursesListAllCourseSelectSel())
          .prop('indeterminate', false)
          .prop('checked', anyChecked);
      $(_fixedHdrAllCourseSelectSel())
          .prop('indeterminate', false)
          .prop('checked', anyChecked);
    }
    setMultiCourseActionAllowed(anyChecked);
    gcbAdminOperationCount++;
  }

  // ---------------------------------------------------------------------------
  // Abstract base popup panel that supports modifications to multiple courses.
  //
  // Derived classes should implement the following functions.  These take
  // no parameters other than the implied 'this'.
  //
  // - _getTitle(): Returns a string for titling the popup window.
  // - _getXsrfToken(): Returns a string containing the xsrf token authorizing
  //       changes to course settings.
  // - _getFormFields(): Returns HTML elements that are added to
  //       the popup window.  Typically contains form fields for settings.
  // - _canBeCleared(): Return true if value is clearable, false otherwise.
  // - _getCurrentValue(): Returns a text string giving the current value
  //       for the setting.  This is used to populate the current-value
  //       column in the popup form.
  // - _validate(): Return true/false.  On false, you should highlight
  //       incorrect fields and/or set a butterbar message to indicate
  //       problems.  If this returns false, the Save button does not
  //       save the current settings.
  // - _getSaveUrl(): Return the URL component (e.g., "/rest/assessment")
  //       without the course slug prefix that will accept an HTTP PUT.
  //       This handler *must* return a payload dict with an item named
  //       "key" and a value giving the slug identifying the course.
  // - _getSavePayload(): Return a dict/object containing key/value pairs
  //       of data that is sent in the PUT request to set valid values.
  // - _getClearPayload(): Return a dict/object containing key/value pairs
  //       of data that is sent in the PUT request to clear that setting.
  // - _settingSaved(payload): Called back when a PUT for a given course
  //       returns successfully.  Derived classes may wish to use this
  //       opportunity to update the contents of the page to reflect the new
  //       setting.  The payload parameter is the payload component of the
  //       JSON response returned from the REST handler.
  //
  var EditMultiCoursePanel = function() {
    // Constructors must take no parameters and have no side effects, since
    // declaring class inheritance is done by setting the derived class'
    // .prototype member to a constructed (new'd) instance of the base class.
    // We separate the declaration of the inheritance structure into the
    // constructor-function, and object initialization is deferred to init().
    //
    // Derived classes may wish to call init() as part of their constructor,
    // but doing so implicitly declares that class to be a leaf - it will not
    // be usable as a base class.
  };

  EditMultiCoursePanel.prototype.init = function() {
    this._xsrfToken = this._getXsrfToken();
    this._documentBody = $(document.body);
    this._lightbox = new window.gcb.Lightbox();
    this._numSuccessResponses = 0;
    this._numFailureResponses = 0;
    this._courses = $(_scrolledCourseCheckboxesSel() + ':checked').map(
        function(index, item){
          return {
            namespace: $(item).data('course-namespace'),
            title: $(item).data('course-title'),
            slug: $(item).data('course-slug')
          };
        });

    var formStr = (
        '<div class="add-course-panel multi-course-panel" ' +
        '     id="multi-course-edit-panel">' +
        '  <h2 class="title"></h2>');
    if (this._canBeCleared()) {
      formStr += (
        '  <div id="edit_multi_course_clear_label"> ' +
        '    <input ' +
        '      type="radio" ' +
        '      name="edit_multi_course_choice" ' +
        '      id="edit_multi_course_clear" ' +
        '      value="clear"> ' +
        '      Clear Setting ' +
        '  </div> ' +
        '  <div id="edit_multi_course_set_label"> ' +
        '    <input ' +
        '      type="radio" ' +
        '      name="edit_multi_course_choice" ' +
        '      id="edit_multi_course_set" ' +
        '      value="set"> ' +
        '      Set Setting: ' +
        '    <div class="edit-multi-course-settings" ' +
        '         id="edit_multi_course_settings"> ' +
        '    </div> ' +
        '  </div> ')
    } else {
      formStr += (
        '    <div class="edit-multi-course-settings" ' +
        '         id="edit_multi_course_settings"> ' +
        '    </div> ');
    }
    formStr += (
        '  <div class="edit-multi-course-list">' +
        '    <table>' +
        '      <thead>' +
        '        <tr id="multi_edit_header_row">' +
        '          <th class="edit-multi-course-coursename">Course Name</th>' +
        '          <th class="edit-multi-course-value">Current Value</th>' +
        '          <th class="edit-multi-course-status">Saved?</th>' +
        '        </tr>' +
        '      </thead>' +
        '      <tbody id="course_list">' +
        '      </tbody>' +
        '    </table>' +
        '  </div>' +
        '  <div class="controls">' +
        '    <button id="multi-course-save" ' +
        '            class="gcb-button save-button">Save</button>' +
        '    <button id="multi-course-close" ' +
        '            class="gcb-button cancel-button">Close</button>' +
        '  </div>' +
        '  <div id="multi-course-spinner" class="spinner hidden">' +
        '    <div class="background"></div>' +
        '    <span class="icon spinner md md-settings md-spin"></span>' +
        '  </div>' +
        '</div>');
    this._form = $(formStr);
    var titleElement = this._form.find('.title');
    titleElement.text(this._getTitle());
    var settingsDiv = this._form.find('#edit_multi_course_settings');
    settingsDiv.append(this._getFormFields());
    var courseList = this._form.find('#course_list');
    var that = this;
    $(this._courses).each(function(index, course) {
      var currentValue = that._getCurrentValue(course.namespace);
      courseList.append(
          $('<tr><td class="edit-multi-course-coursename">' +
            course.title +
            '</td><td id="current_value_' + course.namespace + '">' +
            currentValue +
            '</td><td id="course_status_' + course.namespace + '">' +
            ' - ' +
            '</td></tr>'));
    });
    var saveButton = this._form.find('#multi-course-save');
    if (this._canBeCleared()) {
      saveButton.prop('disabled', true);
      this._form.find('input[name="edit_multi_course_choice"]').change(
          function(event){
            saveButton.prop('disabled', false);
          });
    }
    saveButton.click(this._save.bind(this));
    this._form.find('#multi-course-close').click(this._close.bind(this));
    this._spinner = this._form.find('.spinner');
  };
  EditMultiCoursePanel.prototype.open = function() {
    this._lightbox
      .bindTo(this._documentBody)
      .setContent(this._form)
      .show();
  };
  EditMultiCoursePanel.prototype._validate = function() {
    return true;
  };
  EditMultiCoursePanel.prototype._getCurrentValue = function(courseNamespace) {
    return '';  // Override in concrete classes.
  };
  EditMultiCoursePanel.prototype._save = function() {
    if (!this._validate()) {
      return;
    }
    if (!confirm('You are about to change settings in ' +
        this._courses.length + ' courses.  Continue?')) {
      return;
    }
    this._showSpinner();
    var errorHandler = this._saveError.bind(this);
    var successHandler = this._saveSuccess.bind(this);
    var completeHandler = this._saveComplete.bind(this);
    var xsrfToken = this._xsrfToken;
    var saveUrl = this._getSaveUrl();

    var payload;
    if ($('input[name="edit_multi_course_choice"]:checked').val() == 'clear') {
      payload = JSON.stringify(this._getClearPayload());
    } else {
      payload = JSON.stringify(this._getSavePayload());
    }
    this._numSuccessResponses = 0;
    this._numFailureResponses = 0;

    $(this._courses).each(function(index, course){
      var statusField = $('#course_status_' + course.namespace);
      statusField.text(' - ');

      var request = {
        key: course.namespace,
        xsrf_token: xsrfToken,
        payload: payload,
      };
      var url = '/' + course.slug + saveUrl;
      url = url.replace('//', '/');

      $.ajax(url, {
        method: 'PUT',
        data: {request: JSON.stringify(request)},
        dataType: 'text',
        error: errorHandler,
        success: successHandler,
        complete: completeHandler
      });
    });
  };
  EditMultiCoursePanel.prototype._showSpinner = function() {
    this._spinner.removeClass('hidden');
  };
  EditMultiCoursePanel.prototype._hideSpinner = function() {
    this._spinner.addClass('hidden');
  };
  EditMultiCoursePanel.prototype._close = function() {
    this._lightbox.close();
  };
  EditMultiCoursePanel.prototype._saveError = function() {
    cbShowMsg('Something went wrong. Please try again.');
    this._spinner.addClass('hidden')
  };
  EditMultiCoursePanel.prototype._saveSuccess = function(data) {
    var data = window.gcb.parseJsonResponse(data);
    var payload = window.gcb.parseJsonResponse(data.payload);

    var courseNamespace = payload.key;
    var statusField = $('#course_status_' + courseNamespace);
    var message;
    if (data.status != 200) {
      message = data.message || 'Unknown error.';
      this._numFailureResponses++;
    } else {
      this._settingSaved(payload);
      message = 'Saved.';
      this._numSuccessResponses++;
    }
    statusField.text(message);
    statusField.get(0).scrollIntoView();
  };

  EditMultiCoursePanel.prototype._saveComplete = function() {
    var numResponses = this._numSuccessResponses + this._numFailureResponses;
    if (numResponses >= this._courses.length) {
      var message = (
          'Updated settings in ' + this._numSuccessResponses +' course');
      if (this._numSuccessResponses != 1) {
        message += 's';
      }
      if (this._numFailureResponses > 0) {
        message += ' and had ' + this._numFailureResponses + ' error';
        if (this._numFailureResponses != 1) {
          message += 's';
        }
      }
      message += '.';
      $('#multi_edit_header_row').get(0).scrollIntoView();
      cbShowMsgAutoHide(message);
      this._hideSpinner();
    }
  };

  // ---------------------------------------------------------------------------
  // For editing availability on multiple courses.
  //
  // Used for immediate change of course availability, and also as a base class
  // for changing course start/end date + availability settings.
  //
  EditMultiCourseAvailabilityPanel = function () {
    EditMultiCoursePanel.call(this);
  };
  EditMultiCourseAvailabilityPanel.prototype = new EditMultiCoursePanel();
  EditMultiCourseAvailabilityPanel.prototype._getTitle = function() {
    return 'Set Course Availability';
  };
  EditMultiCourseAvailabilityPanel.prototype._getXsrfToken = function() {
    return $('#edit_multi_course_availability').data('xsrfToken');
  };
  EditMultiCourseAvailabilityPanel.prototype._getFormFields = function() {
    var ret = $(
        '<div class="form-row">' +
        '  <select ' +
        '      id="multi-course-select-availability" ' +
        '      name="availability">' +
        '  </select>' +
        '</div>'
        );
    var availabilitySelect = ret.find('#multi-course-select-availability');
    this._availabilitySelect = availabilitySelect;
    var options = $('#edit_multi_course_availability').data('options');
    $(options).each(function(index, opt) {
      availabilitySelect.append(
          $('<option value=' + opt.value + '>' + opt.title + '</option>'));
    });
    availabilitySelect.change(function(event) {
      availabilitySelect.removeClass('input-invalid');
    });
    return ret
  };
  EditMultiCourseAvailabilityPanel.prototype._canBeCleared = function() {
    return false;
  };
  EditMultiCourseAvailabilityPanel.prototype._validate = function() {
    if (!this._canBeCleared()) {
      var isValid = (this._availabilitySelect.val() != '');
      if (isValid) {
        this._availabilitySelect.removeClass('input-invalid');
      } else {
        this._availabilitySelect.addClass('input-invalid');
      }
      return isValid;
    }
    return true;
  };
  EditMultiCourseAvailabilityPanel.prototype._getCurrentValue = function(
      courseNamespace) {
    return $('#availability_' + courseNamespace).text().trim();
  };
  EditMultiCourseAvailabilityPanel.prototype._getSaveUrl = function() {
    return '/rest/multi_availability';
  };
  EditMultiCourseAvailabilityPanel.prototype._getSavePayload = function() {
    var availability = this._availabilitySelect.val();
    return {
      trigger_action: 'merge',
      course_availability: availability
    };
  };
  EditMultiCourseAvailabilityPanel.prototype._getClearPayload = function() {
    return {
      trigger_action: 'merge',
      course_availability: ''
    };
  };
  EditMultiCourseAvailabilityPanel.prototype._settingSaved = function(payload) {
    var courseNamespace = payload.key;
    var availability = this._availabilitySelect[0].selectedOptions[0].text;
    $('#availability_' + courseNamespace).text(availability);
    $('#current_value_' + courseNamespace).text(availability);
  };
  function editMultiCourseAvailability() {
    // Var name intentionally in global namespace as hook for tests to modify.
    window.gcb_multi_edit_dialog = new EditMultiCourseAvailabilityPanel();
    window.gcb_multi_edit_dialog.init();
    window.gcb_multi_edit_dialog.open();
  };

  // ---------------------------------------------------------------------------
  // Edit courses' start or end date and new availability on that date.
  EditMultiCourseDatePanel = function () {
    EditMultiCourseAvailabilityPanel.call(this);
  }
  EditMultiCourseDatePanel.prototype = new EditMultiCourseAvailabilityPanel();
  EditMultiCourseDatePanel.prototype.init = function(start_or_end) {
    this._start_or_end = start_or_end;  // "start" or "end".
    this._start_or_end_title = (
        start_or_end[0].toUpperCase() + start_or_end.substring(1));
    EditMultiCourseAvailabilityPanel.prototype.init.call(this);
  };
  EditMultiCourseDatePanel.prototype._getTitle = function() {
    return 'Set Course ' + this._start_or_end_title + ' Date and Availability';
  };
  EditMultiCourseDatePanel.prototype._getFormFields = function() {
    // Tack on all the .class names required for parent/child CSS class
    // matching in this one datetime-container div.
    var fields = $(
        '<div class="form-row">' +
        '  <label id="availability-label">Change course availability to: ' +
        '  </label>' +
        '  <label>On ' + this._start_or_end_title + ' Date (UTC): ' +
        '    <div id="datetime-container" ' +
        '         class="new-form-layout yui3-skin-sam yui-skin-sam"></div>' +
        '  </label> ' +
        '</div>'
        );
    fields.find('#availability-label').append(
        EditMultiCourseAvailabilityPanel.prototype._getFormFields.call(this));

    YUI.add('gcb-datetime', bindDatetimeField, '3.1.0', {
      requires: ['inputex-datetime']
    });
    var self = this;
    var yuiConf = getYuiConfig(cb_global.bundle_lib_files);
    YUI(yuiConf).use('gcb-datetime', function(Y) {
      self._datetime_field = new Y.inputEx.typeClasses.datetime(
          {parentEl: fields.find('#datetime-container')[0]});
      // Course start and end dates are in UTC, so trigger special conversions
      // between the stored values and the values displayed to the user, which
      // are always in local time (not UTC).
      $(self._datetime_field.divEl).addClass('gcb-utc-datetime');
      // Mark minutes field in date picker as not editable.  Date/time
      // picker looks odd with just the hours field, so leave minutes
      // field there with default value of :00, which is what we want,
      // since the do-trigger cron job fires ~hourly.
      $(self._datetime_field.divEl).find(
          '.inputEx-CombineField-separator + .inputEx-fieldWrapper select'
          ).prop('disabled', 'true');
      self._datetime_field.options.required = true;
    });

    return fields;
  };
  EditMultiCourseDatePanel.prototype._canBeCleared = function() {
    return true;
  }
  EditMultiCourseDatePanel.prototype._validate = function() {
    if ($('input[name="edit_multi_course_choice"]:checked').val() == 'clear') {
      return true;
    }
    return this._datetime_field.validate();
  };
  EditMultiCourseDatePanel.prototype._getSaveUrl = function() {
    // Decide whether to call set... or clear... depending on whether
    // the date field is blank or not.  It's substantially more convenient
    // to do this at this layer rather than in the server because of the
    // tight integration of parsing + setting code, which will just ignore
    // items which appear malformed (e.g., which have a blank date field. :-> )
    if ($('input[name="edit_multi_course_choice"]:checked').val() == 'clear') {
      return '/rest/multi_clear_start_end';
    } else {
      return '/rest/multi_set_start_end';
    }
  };
  EditMultiCourseDatePanel.prototype._getSavePayload = function() {
    var availability = this._availabilitySelect.val();
    var when = this._datetime_field.getValue();
    var setting_name = 'course_' + this._start_or_end;
    var ret = {}
    if (when) {
      ret[setting_name] = [{
        'availability': availability,
        'milestone': setting_name,
        'when': when
      }];
    } else {
      ret = {
        'milestone': setting_name,
      };
    }
    return ret;
  };
  EditMultiCourseDatePanel.prototype._getClearPayload = function() {
    return {'milestone': 'course_' + this._start_or_end};
  };
  EditMultiCourseDatePanel.prototype._getCurrentValue = function(
      courseNamespace) {
    return $('#' + this._start_or_end + '_date_full_' + courseNamespace).text();
  };
  EditMultiCourseDatePanel.prototype._settingSaved = function(payload) {
    var courseNamespace = payload.key;

    if ($('input[name="edit_multi_course_choice"]:checked').val() == 'clear') {
      $('#' + this._start_or_end + '_date_' + courseNamespace).text('');
      $('#' + this._start_or_end + '_date_full_' + courseNamespace).text('');
      $('#current_value_' + courseNamespace).text('');
    } else {
      var availability = this._availabilitySelect[0].selectedOptions[0].text;
      var startDate = this._datetime_field.getValue();

      startDate = startDate.substring(0, 10);
      var startDateTime = (
          this._datetime_field.getValue().replace('T', ' ').substring(0, 19))
      var msg = availability + ' on ' + startDateTime;
      $('#' + this._start_or_end + '_date_' + courseNamespace).text(startDate);
      $('#' + this._start_or_end + '_date_full_' + courseNamespace).text(msg);
      $('#current_value_' + courseNamespace).text(msg);
    }
  };
  function editMultiCourseStartDate() {
    // Var name intentionally in global namespace as hook for tests to modify.
    window.gcb_multi_edit_dialog = new EditMultiCourseDatePanel();
    window.gcb_multi_edit_dialog.init('start');
    window.gcb_multi_edit_dialog.open();
  };
  function editMultiCourseEndDate() {
    // Var name intentionally in global namespace as hook for tests to modify.
    window.gcb_multi_edit_dialog = new EditMultiCourseDatePanel();
    window.gcb_multi_edit_dialog.init('end');
    window.gcb_multi_edit_dialog.open();
  };


  // ---------------------------------------------------------------------------
  // For editing category name on multiple courses.
  //
  EditMultiCourseCategoryPanel = function () {
    EditMultiCoursePanel.call(this);
  };
  EditMultiCourseCategoryPanel.prototype = new EditMultiCoursePanel();
  EditMultiCourseCategoryPanel.prototype._getTitle = function() {
    return 'Set Course Category';
  };
  EditMultiCourseCategoryPanel.prototype._getXsrfToken = function() {
    return $('#edit_multi_course_category').data('xsrfToken');
  };
  EditMultiCourseCategoryPanel.prototype._getFormFields = function() {
    var ret = $(
        '<div class="form-row">' +
        '  <label>Category</label>' +
        '  <input ' +
        '      type="text" ' +
        '      id="multi-course-category" ' +
        '      name="category">' +
        '</div>'
        );
    var category = ret.find('#multi-course-category');
    category.change(function() {
      $('#multi-course-category').removeClass('input-invalid');
    });
    category.keypress(function() {
      $('#multi-course-category').removeClass('input-invalid');
    });
    this._category = category;
    return ret;
  };
  EditMultiCourseCategoryPanel.prototype._canBeCleared = function() {
    return true;
  }
  EditMultiCourseCategoryPanel.prototype._validate = function() {
    if ($('input[name="edit_multi_course_choice"]:checked').val() == 'clear') {
      return true;
    }
    var isValid = this._category.val() != ''
    if (isValid) {
        this._category.removeClass('input-invalid');
      } else {
        this._category.addClass('input-invalid');
      }
    return isValid
  }
  EditMultiCourseCategoryPanel.prototype._getCurrentValue = function(
      courseNamespace) {
    return $('#category_' + courseNamespace).text();
  };
  EditMultiCourseCategoryPanel.prototype._getSaveUrl = function() {
    return '/rest/course/settings';
  };
  EditMultiCourseCategoryPanel.prototype._getSavePayload = function() {
    var category = this._category.val();
    return {
      'homepage': {
        'course:category_name': category
      }
    };
  };
  EditMultiCourseCategoryPanel.prototype._getClearPayload = function() {
    return {
      'homepage': {
        'course:category_name': ''
      }
    };
  };
  EditMultiCourseCategoryPanel.prototype._settingSaved = function(payload) {
    var courseNamespace = payload.key;
    if ($('input[name="edit_multi_course_choice"]:checked').val() == 'clear') {
      $('#category_' + courseNamespace).text('');
      $('#current_value_' + courseNamespace).text('');
    } else {
      $('#category_' + courseNamespace).text(this._category.val());
      $('#current_value_' + courseNamespace).text(this._category.val());
    }
  };
  function editMultiCourseCategory() {
    // Var name intentionally in global namespace as hook for tests to modify.
    gcb_multi_edit_dialog = new EditMultiCourseCategoryPanel();
    gcb_multi_edit_dialog.init();
    gcb_multi_edit_dialog.open();
  };

  // --------------------------------------------------------------------------
  // For editing course availability in Explorer page boolean setting

  EditMultiCourseShowInExplorerPanel = function () {
    EditMultiCoursePanel.call(this);
  };
  EditMultiCourseShowInExplorerPanel.prototype = new EditMultiCoursePanel();
  EditMultiCourseShowInExplorerPanel.prototype._getTitle = function() {
    return 'Set Whether Course Is Shown In Explorer';
  };
  EditMultiCourseShowInExplorerPanel.prototype._getXsrfToken = function() {
    return $('#edit_multi_course_show_in_explorer').data('xsrfToken');
  };
  EditMultiCourseShowInExplorerPanel.prototype._getFormFields = function() {
    var ret = $(
        '<div class="form-row">' +
        '  <label>Show In Explorer?' +
        '    <div> ' +
        '      <label class="multi-course-show-in-explorer-yes"> ' +
        '        <input ' +
        '          type="radio" ' +
        '          id="multi-course-show-in-explorer-yes" ' +
        '          name="show_in_explorer"> Yes ' +
        '      </label> ' +
        '    </div> ' +
        '    <div> ' +
        '      <label class="multi-course-show-in-explorer-no"> ' +
        '        <input ' +
        '          type="radio" ' +
        '          id="multi-course-show-in-explorer-no" ' +
        '          name="show_in_explorer"> No ' +
        '      </label> ' +
        '    </div> ' +
        '  </label>' +
        '</div>'
        );
    this._show_in_explorer_yes = ret.find('#multi-course-show-in-explorer-yes');
    this._show_in_explorer_no = ret.find('#multi-course-show-in-explorer-no');
    var that = this;
    this._show_in_explorer_yes.change(function(event) {
      that._show_in_explorer_yes.parent().removeClass('input-invalid');
      that._show_in_explorer_no.parent().removeClass('input-invalid');
    });
    this._show_in_explorer_no.change(function(event) {
      that._show_in_explorer_yes.parent().removeClass('input-invalid');
      that._show_in_explorer_no.parent().removeClass('input-invalid');
    });
    return ret;
  };
  EditMultiCourseShowInExplorerPanel.prototype._validate = function() {
    var is_yes = this._show_in_explorer_yes.prop('checked');
    var is_no = this._show_in_explorer_no.prop('checked');
    if (is_yes == is_no) {
      this._show_in_explorer_yes.parent().addClass('input-invalid');
      this._show_in_explorer_no.parent().addClass('input-invalid');
    } else {
      this._show_in_explorer_yes.parent().removeClass('input-invalid');
      this._show_in_explorer_no.parent().removeClass('input-invalid');
    }
    return is_yes != is_no;
  };
  EditMultiCourseShowInExplorerPanel.prototype._canBeCleared = function() {
    return false;
  };
  EditMultiCourseShowInExplorerPanel.prototype._getCurrentValue = function(
      courseNamespace) {
    return $('#show_in_explorer_' + courseNamespace).text();
  };
  EditMultiCourseShowInExplorerPanel.prototype._getSaveUrl = function() {
    return '/rest/course/settings';
  };
  EditMultiCourseShowInExplorerPanel.prototype._getSavePayload = function() {
    var show_in_explorer = this._show_in_explorer_yes.prop('checked');
    return {
      'homepage': {
        'course:show_in_explorer': show_in_explorer
      }
    };
  };
  EditMultiCourseShowInExplorerPanel.prototype._settingSaved = (
      function(payload) {
        var courseNamespace = payload.key;
        var message = '';
        if (this._show_in_explorer_yes.prop('checked')) {
          message = 'Yes';
        } else {
          message = 'No';
        }
        $('#show_in_explorer_' + courseNamespace).text(message);
        $('#current_value_' + courseNamespace).text(message);
      }
  );
  function editMultiCourseShowInExplorer() {
    // Var name intentionally in global namespace as hook for tests to modify.
    window.gcb_multi_edit_dialog = new EditMultiCourseShowInExplorerPanel();
    window.gcb_multi_edit_dialog.init();
    window.gcb_multi_edit_dialog.open();
  };

  var _sortBySequence = {
    // The key is the element #id of the primary "clicked on" sortable table
    // column header.
    //
    // The value is an ordered "sort-by sequence" list of those table column
    // headers for each column by which to compare two table rows.
    //
    // If the two rows have equal cell values in the current column (beginning
    // with the first one in the sort-by sequence list) being compared, the
    // comparison continues with the cell values in those same two rows, but
    // corresponding to the next column in the sort-by sequence list.
    //
    // The comparisons continue until either two cell values are non-equal,
    // or the sort-by sequence list is exhausted, which *would* indicate that
    // the two rows are identical. Two rows being identical should never
    // actually happen in practice, because once the "URL Component" column
    // values are compared, the comparison should complete. The URL component
    // values are expected to be unique (and thus two rows can never share a
    // value for that column.
    'title_column': [
      'title_column',
      'url_column',
      // A "URL Component" is unique; no more columns should need comparing.
    ],
    'url_column': [
      'url_column',
      'title_column',
      'availability_column',
      'start_date_column',
      'end_date_column',
      'category_column',
      'enrolled_column',
    ],
    'availability_column': [
      'availability_column',
      'title_column',
      'url_column',
      'start_date_column',
      'end_date_column',
      'category_column'
      // A "URL Component" is unique; no more columns should need comparing.
    ],
    'enrolled_column': [
      'enrolled_column',
      'title_column',
      'url_column',
      'start_date_column',
      'end_date_column',
      'category_column'
      // A "URL Component" is unique; no more columns should need comparing.
    ],
    'start_date_column': [
      'start_date_column',
      'end_date_column',
      'url_column',
      'title_column',
      'availability_column',
      'category_column',
      'enrolled_column'
    ],
    'end_date_column': [
      'end_date_column',
      'start_date_column',
      'url_column',
      'title_column',
      'availability_column',
      'category_column',
      'enrolled_column'
    ],
    'category_column': [
      'category_column',
      'url_column',
      'title_column',
      'availability_column',
      'start_date_column',
      'end_date_column',
      'enrolled_column'
    ]
  };
  function _sortedIcon($th) {
    // Returns the Material Design icon container in the supplied table header.
    return $th.children('i.gcb-sorted-icon').eq(0);
  }
  function _setIconFromSorted($th, sorted) {
    // Sets the displaed Material Design arrow icon based on sorted class.
    var $icon = _sortedIcon($th);

    // If no recognized gcb-sorted class is supplied, set the Material Design
    // arrow container to an empty string. Otherwise set it to 'arrow_upward'
    // or 'arrow_downward' based on the sorted order.
    var arrow = (sorted == 'gcb-sorted-descending') ? 'arrow_downward' :
        (sorted == 'gcb-sorted-ascending') ? 'arrow_upward' : '';
    $icon.text(arrow);
    $icon.removeClass('gcb-sorted-hover');
  }
  function _sortedFromHeader($th) {
    // Returns the first gcb-sorted CSS class encountered, from the following
    // order of priority:
    //   'gcb-sorted-descending', 'gcb-sorted-descending'
    // or 'gcb-sorted-none' if no recognized gcb-sorted class was found.
    return $th.hasClass('gcb-sorted-descending') ? 'gcb-sorted-descending' :
        $th.hasClass('gcb-sorted-ascending') ? 'gcb-sorted-ascending' :
        'gcb-sorted-none';
  }
  function _nextFromHeader($th) {
    // _nextFromHeader() examines the current CSS classes of the <th> to
    // decide the order by which the column would be sorted *next* if the
    // column header were clicked.
    //
    // If gcb-sorted order is already ascending, return descending. Otherwise,
    // (for descending or no sorted order at all), return ascending.
    return $th.hasClass('gcb-sorted-ascending') ?
        'gcb-sorted-descending' : 'gcb-sorted-ascending';
  }
  function _textToSortBy(tr, idx) {
    // Returns the text to sort by in a given column of the supplied row.
    var $td = $(tr).children('td').eq(idx);

    // Each element in a table row has the text by which the column should be
    // sorted in a different "container". Some are in link anchors, and some
    // are just plain text. This function finds the inner element at the
    // specified index in the row actually containing the text to sort by.
    var elem = $td.find('.gcb-text-to-sort-by').get()[0];
    return $(elem).text();
  }
  var _compareOptions = {
    // The key is the element #id of a sortable table column header.
    //
    // The value is an "options" object supplied to localeCompare to tune
    // how two row cells in the column in question are compared.
    //
    // These defaults are assumed and thus not explicitly specified unless being
    // overridden:
    //   localeMatcher:     'best fit'
    //   usage:             'sort'     // Comparison is being done to sort.
    //   sensitivity:       'variant'  // Consider case, accents, diacritics.
    //   ignorePunctuation: 'false'
    //   caseFirst:         'false'    // Use locale default.
    'title_column': {
      sensitivity: 'accent',   // Case-insensitive, but still use accents, etc.
      ignorePunctuation: 'true',
    },
    'url_column': {
      sensitivity: 'accent',   // Case-insensitive, but still use accents, etc.
    },
    'availability_column': {
      sensitivity: 'accent',   // Case-insensitive, but still use accents, etc.
      ignorePunctuation: 'true',
    },
    'enrolled_column': {
      numeric: 'true',
    },
  };
  function _compareSortByText(trA, trB, id, idx, dir) {
    // Compares, for the purposes of sorting a collection of strings, two text
    // text values, after trimming any leading and trailing whitespace, as
    // case-insensitive strings.
    var textA = _textToSortBy(trA, idx).trim();
    var textB = _textToSortBy(trB, idx).trim();

    // An empty value (or one that becomes empty after all leading and trailing
    // whitespace has been removed) always sorts "at the end" (for +1 dir sign,
    // or at the beginning for -1 dir sign), unless both are empty, in which
    // case both are "equally empty".
    if (textA === "") {
      if (textB === "") {
        return 0;
      }
      return dir;
    }
    if (textB === "") {
      return -dir;
    }
    return textA.localeCompare(textB, undefined, _compareOptions[id]) * dir;
  }
  function _clearHeadersSorted(hdrs) {
    // Clears any existing sorted column state from the supplied table headers.
    $.each(hdrs, function(unused, th) {
      $th = $(th);
      _setIconFromSorted($th, 'gcb-sorted-none');
      $th.addClass('gcb-sorted-none');
      $th.removeClass('gcb-sorted-ascending gcb-sorted-descending');
    });
  }
  function _setHeaderSorted($th, sorted) {
    // Set the supplied table header to the supplied sorted state.
    $th.removeClass(
        'gcb-sorted-none gcb-sorted-ascending gcb-sorted-descending');
    $th.addClass(sorted);
    _setIconFromSorted($th, sorted);
  }
  function _sortableColHdrsSel() {
    return _someColHdrsSel(':not(.gcb-not-sortable)');
  }
  function _coursesListSortableColHdrsSel() {
    return _coursesListTableSel() + ' > ' + _sortableColHdrsSel();
  }
  function _sortableHeaders($table) {
    // Only some of the table columns can be used to sort the table rows.
    return $table.find(_sortableColHdrsSel()).get();
  }
  function sortCourseRows() {
    // sortCourseRows() sorts rows in the <tbody> of the courses list table
    // by the column corresponding to the clicked <thead> <th> (this)
    var parts = _fixedAndScrolled($(this));
    var next = _nextFromHeader(parts.$th);

    // Clear any Material Design sort direction arrows from all sortable
    // column headers, in both the "real" <table> and the ".fixed.thead" one.
    _clearHeadersSorted(_sortableHeaders(parts.$table));
    _clearHeadersSorted(_sortableHeaders(parts.$theadTable));

    // Make a slice copy of the _sortBySequence selected by id.
    var ids = _sortBySequence[parts.$th.attr('id')].slice(0);

    // The "compare" multiplier that sets sorted direction by altering the
    // sort comparison return value sign.
    var dir = (next == 'gcb-sorted-descending') ? -1 : 1;

    // Only the rows in the table body (not thead or tfoot) are to be sorted.
    var rows =  parts.$table.find('tbody > tr').get();
    rows.sort(function(trA, trB) {
      for (var i in ids) {
        var id = ids[i];
        var hdr = parts.$table.find(_colHdrSelById(id)).get()[0];
        var cmp = _compareSortByText(trA, trB, id, $(hdr).index(), dir);
        if (cmp != 0) {
          // Element text values are different, so no more column checking.
          return cmp;
        }
      }
      return 0;
    });

    // Update the table rows.
    $.each(rows, function(unused, tr) {
      parts.$table.children('tbody').append(tr);
    });

    // Indicate in the clicked table header that the table is now sorted by it.
    _setHeaderSorted(parts.$th, next);
    _setHeaderSorted(parts.$theadTh, next);
  }
  function hintNextSort() {
    // Change the displayed Material Design arrow icon to what *would* be the
    // next sorted state, but do not change the CSS style (which is used to
    // save current sorted state of the table).
    var parts = _fixedAndScrolled($(this));
    var next = _nextFromHeader(parts.$th);
    _setIconFromSorted(parts.$th, next);
    _sortedIcon(parts.$th).addClass('gcb-sorted-hover');
    _setIconFromSorted(parts.$theadTh, next);
    _sortedIcon(parts.$theadTh).addClass('gcb-sorted-hover');
  }
  function unhintSort() {
    // Restore the displayed Material Design arrow icon (if any) to the current
    // sorted state of the table.
    var parts = _fixedAndScrolled($(this));
    var sorted = _sortedFromHeader(parts.$th);
    _setIconFromSorted(parts.$th, sorted);
    _sortedIcon(parts.$th).removeClass('gcb-sorted-hover');
    _setIconFromSorted(parts.$theadTh, sorted);
    _sortedIcon(parts.$theadTh).removeClass('gcb-sorted-hover');
  }

  function bind() {
    $('#add_course').click(addCourse);
    $('#add_sample_course').click(addSampleCourse);
    $(_coursesListAllCourseSelectSel()).click(selectAll);
    $('#edit_multi_course_availability').click(editMultiCourseAvailability);
    $('#edit_multi_course_start_date').click(editMultiCourseStartDate);
    $('#edit_multi_course_end_date').click(editMultiCourseEndDate);
    $('#edit_multi_course_category').click(editMultiCourseCategory);
    $('#edit_multi_course_show_in_explorer').click(
        editMultiCourseShowInExplorer);
    $(_scrolledCourseCheckboxesSel()).click(selectCourse);

    $(_coursesListSortableColHdrsSel()).click(sortCourseRows);
    $(_coursesListSortableColHdrsSel()).hover(hintNextSort, unhintSort);

    // Forms have no submit control unless this JS runs successfully to
    // add the are-you-sure safety check.
    $("[delete_course]")
        .append('<button ' +
            'class="gcb-list__icon gcb-list__icon--rowhover material-icons">' +
            'delete</button')
        .submit(function(event) {
          return confirm(
            'You are about to permanently and unrecoverably ' +
            'delete this course.  Really proceed?');
        });
  }
  function init() {
    bind();

    var anyChecked = false;
    $(_scrolledCourseCheckboxesSel()).each(function(_, checkbox){
      anyChecked |= checkbox.checked;
    });
    setMultiCourseActionAllowed(anyChecked);

    // Click on the Title column header to force an initial ascending sort.
    $(_coursesListColHdrSelById('title_column')).click();
  }

  init();

  /* New jQuery plugin/method for recalculating the table height.  A
     bit more work could make this reusable across page tables. */
  (function($) {
    $.fn.recalculateCourseTableHeight = function() {
      return this.each(function() {
        var $this = $(this), $titleRowFixed, $footerRowFixed;

        function init() {
          // wrap tables with relative positioned div
          $this.wrap(
              '<div class="table-container">' +
              '  <div class="table-scroller">' +
              '  </div>' +
              '</div>');
          // cloned header elem, keep event bindings
          $titleRowFixed = $this.clone(true);
          // cloned footer elem, keep event bindings
          $footerRowFixed = $this.clone(true);
          $titleRowFixed.find("tbody")
              .remove().end().find("tfoot")
              .remove().end().addClass("fixed thead")
              .prependTo($this.closest(".table-container"));
          $footerRowFixed.find("tbody")
              .remove().end().find("thead")
              .remove().end().addClass("fixed tfoot")
              .appendTo($this.closest(".table-container"));
          fixSizing();
        }

        function fixSizing(){
          // Evaluate necessity of a fixed height table.
          var tableHeight = $this.height();
          var contentAreaHeight = $("#gcb-main-area").
              closest(".mdl-layout__content").
              outerHeight();
          var buttonAreaHeight = $("#gcb-main-area").
              find(".gcb-button-toolbar").
              outerHeight();
          var footerAreaHeight = $("#gcb-footer").outerHeight();
          var paddingAdjustment = $("#gcb-main-content").outerHeight() -
              $("#gcb-main-content").height();
          var scrollerMaxHeight = contentAreaHeight - buttonAreaHeight -
              footerAreaHeight - paddingAdjustment - 12;
          if (tableHeight > scrollerMaxHeight){
            $this.closest(".table-container").addClass("limit-table-height")
                .find(".table-scroller").css(
                    "max-height", (scrollerMaxHeight) + "px");
          } else {
            $this.closest(".table-container")
                .removeClass("limit-table-height")
                .find(".table-scroller")
                .css("max-height", "none");
          }

          // Reset widths in case table sizing changed based on tbody
          $titleRowFixed.width( $this.width() );
          $titleRowFixed.find("th").each(function(index) {
            $(this).css("width", $this.find("th").eq(index).outerWidth()+"px");
          });

          $footerRowFixed.width( $this.width() );
          $footerRowFixed.find("td").each(function(index) {
            $(this).css("width", $this.find("th").eq(index).outerWidth()+"px");
          });
        }
        init();
        $(window).resize(fixSizing);
      });
    };
  })(jQuery);

  /* run plugin after window load so that we're confident layout is calc. */
  $(window).load(function(){
    $("#courses_list").recalculateCourseTableHeight();
  });
});
