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
    if (contentElements.subFields.length == 0) {
      var container = $(contentElements.divEl)
          .find('.content-availability > .inputEx-ListField-childContainer');
      $('<div class="empty-list">No course content available</div>')
          .appendTo(container);
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
  }

  init();
});
