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
    gcbAdminOperationCount++;
  }

  function bind() {
    $('#add_course').click(addCourse);
    $('#add_sample_course').click(addSampleCourse);
    $('#all_courses_select').click(selectAll);
    $('.gcb-course-checkbox').click(selectCourse);

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
  }

  init();
});
