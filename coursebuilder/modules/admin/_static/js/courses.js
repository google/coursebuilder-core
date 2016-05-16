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

  function setMultiCourseActionAvailability(isAvailable) {
    if (isAvailable) {
      $('.multi-course-actions').removeClass('inactive');
    } else {
      $('.multi-course-actions').addClass('inactive');
    }
  }

  function selectAll() {
    // This gets called _after_ checkbox is checked, so 'indeterminate' has
    // been cleared.  Thus we have to look at the rest of the course
    // checkboxes to determine what we should do.  If any is unchecked, we
    // check all; if all are checked, we uncheck all.

    var newState = false;
    $('.gcb-course-checkbox').each(function(_, checkbox){
      newState |= !checkbox.checked;
    });
    $('.gcb-course-checkbox').prop('checked', newState);
    $('#all_courses_select').prop('checked', newState);
    setMultiCourseActionAvailability(newState);
    gcbAdminOperationCount++;
  }

  function selectCourse() {
    // Having clicked the selection checkbox for a single course, set the state
    // of the all-courses selection checkbox accordingly.  All-on -> on;
    // all-off -> off; mixed -> indeterminate.

    var anyChecked = false;
    var anyUnchecked = false;
    $('.gcb-course-checkbox').each(function(_, checkbox){
      anyChecked |= checkbox.checked;
      anyUnchecked |= !checkbox.checked;
    });
    if (anyChecked && anyUnchecked) {
      $('#all_courses_select').prop('indeterminate', true);
    } else {
      $('#all_courses_select')
          .prop('indeterminate', false)
          .prop('checked', anyChecked);
    }
    setMultiCourseActionAvailability(anyChecked);
    gcbAdminOperationCount++;
  }

  var EditMultiCourseAvailabilityPanel = function(xsrfToken, courses, options) {
    this._xsrfToken = xsrfToken;
    this._courses = courses;
    this._documentBody = $(document.body);
    this._lightbox = new window.gcb.Lightbox();
    this._numSuccessResponses = 0;
    this._numFailureResponses = 0;
    this._form = $(
        '<div class="add-course-panel" id="multi-course-edit-panel">' +
        '  <h2 class="title">Set Course Availability</h2>' +
        '  <div class="form-row">' +
        '    <label>Availability</label>' +
        '    <select id="multi-course-select-availability" ' +
        '            name="availability"></select> ' +
        '  </div>' +
        '  <div class="edit-multi-course-list">' +
        '    <table>' +
        '      <thead>' +
        '        <tr id="multi_edit_header_row">' +
        '          <th>Course Name</th>' +
        '          <th>Status</th>' +
        '        </tr>' +
        '      </thead>' +
        '      <tbody id="course_list">' +
        '      </tbody>' +
        '    </table>' +
        '  </div>' +
        '  <div class="controls">' +
        '    <button id="multi-course-save" ' +
        '            class="gcb-button save-button">Save</button>' +
        '    <button id="multi-course-cancel" ' +
        '            class="gcb-button cancel-button">Cancel</button>' +
        '  </div>' +
        '  <div id="multi-course-spinner" class="spinner hidden">' +
        '    <div class="background"></div>' +
        '    <span class="icon spinner md md-settings md-spin"></span>' +
        '  </div>' +
        '</div>');
    var availabilitySelect = this._form.find(
        '#multi-course-select-availability');
    this._availabilitySelect = availabilitySelect;
    $(options).each(function(index, opt) {
      availabilitySelect.append(
          $('<option value=' + opt.value + '>' + opt.title + '</option>'));
    });
    var courseList = this._form.find('#course_list');
    $(courses).each(function(index, course) {
      courseList.append(
          $('<tr><td>' + course.title + '</td>' +
            '<td id="course_status_' + course.namespace + '"> - </td></tr>'));
    });
    this._form.find('#multi-course-save').click(this._save.bind(this));
    this._form.find('#multi-course-cancel').click(this._close.bind(this));
    this._spinner = this._form.find('.spinner');
  };
  EditMultiCourseAvailabilityPanel.prototype.open = function() {
    this._lightbox
      .bindTo(this._documentBody)
      .setContent(this._form)
      .show();
  };
  EditMultiCourseAvailabilityPanel.prototype._save = function() {
    this._showSpinner();
    var availability = this._availabilitySelect.val();
    var errorHandler = this._saveError.bind(this);
    var successHandler = this._saveSuccess.bind(this);
    var completeHandler = this._saveComplete.bind(this);
    var xsrfToken = this._xsrfToken;
    var payload = JSON.stringify({
      course_availability: availability
    });
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
      var url = '/' + course.slug + '/rest/availability';
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
  EditMultiCourseAvailabilityPanel.prototype._showSpinner = function() {
    this._spinner.removeClass('hidden');
  };
  EditMultiCourseAvailabilityPanel.prototype._hideSpinner = function() {
    this._spinner.addClass('hidden');
  };
  EditMultiCourseAvailabilityPanel.prototype._close = function() {
    this._lightbox.close();
  };
  EditMultiCourseAvailabilityPanel.prototype._saveError = function() {
    cbShowMsg('Something went wrong. Please try again.');
    this._spinner.addClass('hidden')
  };
  EditMultiCourseAvailabilityPanel.prototype._saveSuccess = function(data) {
    var data = window.gcb.parseJsonResponse(data);
    var payload = window.gcb.parseJsonResponse(data.payload);
    var courseNamespace = payload.key;
    var availabilityField = $('#availability_' + courseNamespace);
    var statusField = $('#course_status_' + courseNamespace);
    var availability = this._availabilitySelect[0].selectedOptions[0].text

    var message;
    if (data.status != 200) {
      message = data.message || 'Unknown error.';
      this._numFailureResponses++;
    } else {
      availabilityField.text(availability)
      message = 'Saved.';
      this._numSuccessResponses++;
    }
    statusField.text(message);
    statusField.get(0).scrollIntoView();
  };

  EditMultiCourseAvailabilityPanel.prototype._saveComplete = function() {
    var numResponses = this._numSuccessResponses + this._numFailureResponses;
    if (numResponses >= this._courses.length) {
      var availability = this._availabilitySelect.val().replace('_', ' ');
      var message = ('Set availability to ' + availability +
          ' for ' + this._numSuccessResponses + ' course');
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

  function editMultiCourseAvailability() {
    var xsrfToken = $('#edit_multi_course_availability').data('xsrfToken');
    var courses = $('.gcb-course-checkbox:checked').map(
        function(index, item){
          return {
            namespace: $(item).data('course-namespace'),
            title: $(item).data('course-title'),
            slug: $(item).data('course-slug')
          };
        });
    var options = $('#edit_multi_course_availability').data('options');
    // Var name intentionally in global namespace as hook for tests to modify.
    gcb_multi_edit_dialog = new EditMultiCourseAvailabilityPanel(
        xsrfToken, courses, options);
    gcb_multi_edit_dialog.open();
  }

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
      'enrolled_column',
    ],
    'availability_column': [
      'availability_column',
      'title_column',
      'url_column',
      // A "URL Component" is unique; no more columns should need comparing.
    ],
    'enrolled_column': [
      'enrolled_column',
      'title_column',
      'url_column',
      // A "URL Component" is unique; no more columns should need comparing.
    ],
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
  function sortCourseRows() {
    // Sorts rows in the table containing the clicked table header (this).
    var $th = $(this);
    var next = _nextFromHeader($th);
    var $table = $th.closest('table');

    // Only some of the table columns can be used to sort the table rows.
    var hdrs = $table.find('thead > tr > th:not(.gcb-not-sortable)').get();
    _clearHeadersSorted(hdrs, $th.index(), next);

    // Make a slice copy of the _sortBySequence selected by id.
    var ids = _sortBySequence[$th.attr('id')].slice(0);

    // The "compare" multiplier that sets sorted direction by altering the
    // sort comparison return value sign.
    var dir = (next == 'gcb-sorted-descending') ? -1 : 1;

    // Only the rows in the table body (not thead or tfoot) are to be sorted.
    var rows =  $table.find('tbody > tr').get();
    rows.sort(function(trA, trB) {
      for (var i in ids) {
        var id = ids[i];
        var hdr = $table.find('thead > tr > th#' + id).get()[0];
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
      $table.children('tbody').append(tr);
    });

    // Indicate in the clicked table header that the table is now sorted by it.
    _setHeaderSorted($th, next);
  }
  function hintNextSort() {
    // Change the displayed Material Design arrow icon to what *would* be the
    // next sorted state, but do not change the CSS style (which is used to
    // save current sorted state of the table).
    var $th = $(this);
    _setIconFromSorted($th, _nextFromHeader($th));
    _sortedIcon($th).addClass('gcb-sorted-hover');
  }
  function unhintSort() {
    // Restore the displayed Material Design arrow icon (if any) to the current
    // sorted state of the table.
    var $th = $(this);
    _setIconFromSorted($th, _sortedFromHeader($th));
    _sortedIcon($th).removeClass('gcb-sorted-hover');
  }

  function bind() {
    $('#add_course').click(addCourse);
    $('#add_sample_course').click(addSampleCourse);
    $('#all_courses_select').click(selectAll);
    $('#edit_multi_course_availability').click(editMultiCourseAvailability);
    $('.gcb-course-checkbox').click(selectCourse);
    $('div.gcb-list > table > thead > tr > th:not(.gcb-not-sortable)').click(
        sortCourseRows);
    $('div.gcb-list > table > thead > tr > th:not(.gcb-not-sortable)').hover(
        hintNextSort, unhintSort);

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
    $('.gcb-course-checkbox').each(function(_, checkbox){
      anyChecked |= checkbox.checked;
    });
    setMultiCourseActionAvailability(anyChecked);

    // Click on the Title column header to force an initial ascending sort.
    $('div.gcb-list > table > thead > tr > th#title_column').click();
  }

  init();
});
