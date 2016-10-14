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
      if (contentContainer.find('.no-course-content').length <= 0) {
        $('<div class="no-course-content">No course content available.</div>')
            .appendTo(contentContainer);
      }
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

    // If there is no course content, add helpful message, which also
    // disguises the fact that a list field with no content looks odd.
    if (contentElements.subFields.length == 0) {
      $('.content-triggers .inputEx-ListField-childContainer:empty')
        .append($('<div class="no-course-content">' +
          'Create course content (units, lessons, assessments) before' +
          ' defining any date/time availability change triggers.</div>'));
    }

    // If course content exists, unhide add/change button.  Also move
    // button to be after list section.
    if (contentElements.subFields.length > 0) {
      $('.content-triggers > a.inputEx-List-link')
      .removeClass('inputEx-List-link')
      .addClass('gcb-button')
      .each(function(index, button) {
        $button = $(button);
        $div = $('<div class="add-content-trigger"></div>');
        $div.insertAfter($button.parent());
        $button.appendTo($div);
      });
    }
  }

  init();
});
