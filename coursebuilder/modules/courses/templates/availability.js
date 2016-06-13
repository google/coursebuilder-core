$(function() {

  function updateNameWithIndentInfo(rowData) {
    if (rowData.indent.getValue()) {
      $(rowData.name.wrapEl).addClass('indent');
    }
  }
  function updateShowWhenUnavailableCheckbox(rowData) {
    if (rowData.availability.getValue() == 'private') {
      rowData.shown_when_unavailable.enable();
    } else {
      rowData.shown_when_unavailable.setValue(false);
      rowData.shown_when_unavailable.disable();
    }
  }
  function init() {
    var contentElements = cb_global.form.inputsNames.element_settings;
    $(contentElements.divEl).addClass('section-with-heading');
    if (contentElements.subFields.length == 0) {
      var contentContainer = $(contentElements.divEl)
          .find('.content-availability > .inputEx-ListField-childContainer');
      $('<div class="no-course-content">No course content available.</div>')
          .appendTo(contentContainer);
    } else {
      $.each(contentElements.subFields, function() {
        var rowData = this.inputsNames;
        updateNameWithIndentInfo(rowData);
        updateShowWhenUnavailableCheckbox(rowData);
        rowData.availability.on('updated', function () {
          updateShowWhenUnavailableCheckbox(rowData);
        });
      });
    }

    var triggers = cb_global.form.inputsNames.content_triggers;
    $(triggers.divEl).addClass('section-with-heading');
    if (triggers.subFields.length == 0) {
      var container = $(triggers.divEl).find(
          '.content-triggers > .inputEx-ListField-childContainer');

      if (contentElements.subFields.length == 0) {
        $('<div class="no-course-content">' +
          'Create course content (units, lessons, assessments) before' +
          ' defining any date/time availability change triggers.</div>')
            .appendTo(container);
      }
    }
    if (contentElements.subFields.length > 0) {
      // Re-parent 'Add...' button to be after entire triggers list section.
      var $button = $($(triggers.divEl).find(
          '.content-triggers > a.inputEx-List-link'));
      $button.insertAfter($button.parent());

      // Unhide the "Add...change" button if course content exists.
      $button.removeClass('inputEx-List-link');
      $button.addClass('gcb-button');
    }
  }

  init();
});
