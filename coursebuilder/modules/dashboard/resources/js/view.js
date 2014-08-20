//XSSI prefix. Must be kept in sync with models/transforms.py.
var XSSI_PREFIX = ")]}'";
var ESC_KEY = 27;

/**
 * Parses JSON string that starts with an XSSI prefix.
 */
function parseJson(s) {
  return JSON.parse(s.replace(XSSI_PREFIX, ""));
}

function setDraftStatusCallback(data, padlock) {
  var response = parseJson(data);
  if (response.status != 200){
    cbShowAlert("Error: " + response.message);
    return;
  }
  var payload = parseJson(response.payload);
  if (payload.is_draft) {
    padlock.removeClass("icon-unlocked");
    padlock.addClass("icon-locked");
  } else {
    padlock.removeClass("icon-locked");
    padlock.addClass("icon-unlocked");
  }
  cbShowMsgAutoHide(response.message);
}

/**
 * Toggle draft status on click on padlock icon.
 */
function setUpDraftStatus() {
  $(".icon-draft-status.active").on("click", function(e) {
    var padlock = $(this);
    var setDraft = $(this).hasClass("icon-unlocked");
    $.post(
      "dashboard",
      {
        action: "set_draft_status",
        key: $(this).data("key"),
        type: $(this).data("component-type"),
        set_draft: setDraft ? 1 : 0,
        xsrf_token: $(this).parents("#course-outline").data(
          "status-xsrf-token")
      },
      function(data) {
        setDraftStatusCallback(data, padlock);
      },
      "text"
    );
  });
}

/**
 * Fills in local times using data-timestamp attribute.
 */
function setLocalTimes() {
  $(".assets-table tbody .timestamp").each(function() {
    if ($(this).data("timestamp")) {
      $(this).html((new Date(
        parseFloat($(this).data("timestamp"))*1000)).toLocaleString());
    }
  });
}
function openModal(modal) {
  // Bind Esc press to close window
  $(document).on("keyup.modal", function(e) {
    if (e.keyCode == ESC_KEY) {
        closeModal(modal);
    }
  });
  modal.show();
}

function closeModal(modal) {
  modal.hide();
  //Remove Esc binding
  $(document).off("keyup.modal");
  modal.find("#content").empty();
}

/**
 * Sets up handlers for modal window.
 */
function setUpModalWindow() {
  var modal = $("#modal-window");
  // Bind preview button to show question preview
  $(".icon-preview").on("click", function(e) {
    openModal(modal);
    var params = {action: "question_preview", quid: $(this).data("quid")};
    modal.find("#content").html($("<iframe />").attr(
      {id: "question-preview", src: "dashboard?" + $.param(params)}));
  });
  // Bind click on background and on close button to close window
  modal.find("#background, .close-button").on("click", function(e) {
    closeModal(modal);
  });
}

/**
 * Sorts a column based on the clicked header cell.
 */
function sortTable(clickedHeader) {
  var columnIndex = clickedHeader.index();
  var tableBody = clickedHeader.closest(".assets-table").find("tbody");
  var sortAscending = true;
  // On click always sort ascending, unless it's already sorted ascending
  if (clickedHeader.hasClass("sort-asc")) {
    sortAscending = false;
  }
  // Remove any sorting classes from any column
  clickedHeader.parent().children().removeClass("sort-desc sort-asc");
  // Attach relevant sorting class
  clickedHeader.addClass(sortAscending ? "sort-asc" : "sort-desc");
  // Do the actual sorting
  tableBody.find("tr").sort(function(rowA, rowB) {
    var tdA = $(rowA).find("td").eq(columnIndex);
    var tdB = $(rowB).find("td").eq(columnIndex);
    var valueA, valueB;
    if (tdA.data("timestamp")) {
      valueA = tdA.data("timestamp");
      valueB = tdB.data("timestamp");
    } else {
      valueA = tdA.text();
      valueB = tdB.text();
    }
    if (valueA < valueB) {
      return sortAscending ? -1 : 1;
    } else if (valueA > valueB) {
      return sortAscending ? 1 : -1;
    } else {
      return 0;
    }
  }).appendTo(tableBody);
}

/**
 * Sets up table sorting and default sorting order.
 */
function setUpTableSorting() {
  // Sort table on header click
  $(".assets-table th").on("click", function(e) {
    sortTable($(this));
  });
  // Default: sort ascending on first column
  $(".assets-table th:first-child").each(function() {
    sortTable($(this));
  });
}

function setUpFiltering() {

  function showFilter(filterPopup) {
    filterPopup.show(200);
    // Handler: close filter on clicking outside filter
    $(document).on("click.filter", function(e) {
      if($(e.target).closest(filterPopup).length == 0) {
        closeFilter(filterPopup);
      }
    });
  }

  function closeFilter(filterPopup) {
    filterPopup.hide(200);
    $(document).off("click.filter");
  }

  /**
   * Adds <option>s to a <select>.
   *
   * @param {JQuery object} select the <select> element to add to.
   * @param {array} data an array of arrays, where the first element defines
   * the value of the <select> and the second the text.
   */
  function appendOptions(select, data) {
    $.each(data, function() {
      select.append($("<option/>").val(this[0]).text(this[1]))
    });
  }

  function setDefaultOption(select) {
    select.empty().append($("<option/>").val("").text("All"));
  }

  function fillSelect(select, data) {
    setDefaultOption(select);
    appendOptions(select, data);
  }

  function fillLessonsSelect(lessonsSelect, lessonsMap) {
    setDefaultOption(lessonsSelect);
    for (var key in lessonsMap) {
      if (lessonsMap.hasOwnProperty(key)) {
        appendOptions(lessonsSelect, lessonsMap[key]);
      }
    }
  }

  function resetForm(form, lessonsMap) {
    form[0].reset();
    onUnitFieldChange(form, lessonsMap);
  }

  function filterQuestions(form) {
    // Get values from filter form
    var descriptionFilter = form.find(".description").val().toLowerCase();
    var typeFilter = form.find(".type").val();
    var unitFilter = parseInt(form.find(".unit").val());
    var lessonFilter = parseInt(form.find(".lesson").val());
    var groupFilter = parseInt(form.find(".group").val());
    var isUnusedFilter = form.find(".unused").prop("checked");
    $("#question-table tbody tr").each(function() {
      // Get filter data for row
      var rowData = $(this).data("filter");
      // Make sure the row is first visible (unless it's the empty row)
      if (rowData) {
        $(this).show();
      } else {
        $(this).hide();
        return true;
      }
      // Filter checkbox unused
      if (isUnusedFilter && rowData.unused != 1) {
        $(this).hide();
        return true;
      }
      // Filter question type
      if (typeFilter != "" && typeFilter != rowData.type) {
        $(this).hide();
        return true;
      }
      // Filter unit/assessment
      if (!isNaN(unitFilter) && $.inArray(unitFilter, rowData.units) == -1) {
        $(this).hide();
        return true;
      }
      // Filter lesson
      if ((!isNaN(lessonFilter)) && (
          $.inArray(lessonFilter, rowData.lessons) == -1)) {
        $(this).hide();
        return true;
      }
      // Filter question group
      if ((!isNaN(groupFilter)) && (
          $.inArray(groupFilter, rowData.groups) == -1)) {
        $(this).hide();
        return true;
      }
      // Filter description
      if (rowData.description.toLowerCase().indexOf(descriptionFilter) == -1) {
        $(this).hide();
        return true;
      }
    });
    if ($("#question-table tbody tr:visible").size() == 0) {
      $("#question-table tbody tr.empty").show();
    }
  }

  function setUpQuestionFilterForm(filterData) {
    var questionFilterPopup = $("#question-filter-popup");
    var form = questionFilterPopup.find("form");

    // Position question-filter popup next to the question-filter button
    $("#question-filter").append(questionFilterPopup);

    // Fill in the filter with course specific filter information
    fillSelect(form.find(".type"), filterData.types);
    fillSelect(form.find(".unit"), filterData.units);
    fillSelect(form.find(".group"), filterData.groups);
    fillLessonsSelect(form.find(".lesson"), filterData.lessonsMap);
    return form;
  }

  function onUnitFieldChange(form, lessonsMap) {
    var lessonField = form.find(".lesson");
    lessonField.prop("disabled", false);
    var unit = parseInt(form.find(".unit").val());
    if (isNaN(unit)) {
      fillLessonsSelect(lessonField, lessonsMap);
    } else {
      form.find(".unused").prop("checked", false);
      if (lessonsMap.hasOwnProperty(unit) && lessonsMap[unit].length != 0) {
        fillSelect(lessonField, lessonsMap[unit]);
      } else {
        setDefaultOption(lessonField);
        lessonField.prop("disabled", true);
      }
    }
  }

  function setUpQuestionFilter() {
    //Only setUp question filter when container is present.
    if ($("#question-filter").size() == 0) {
      return;
    }

    var filterData = $("#question-table").data();
    var form = setUpQuestionFilterForm(filterData);
    var lessonsMap = filterData.lessonsMap;

    // Bind reset
    form.find(".reset").on("click", function(e) {
      resetForm(form, lessonsMap);
      filterQuestions(form);
    });

    // Adapt lesson dropdown when selecting a unit and uncheck unused checkbox
    var unitField = form.find(".unit");
    unitField.on("change", function(e) {
      onUnitFieldChange(form, lessonsMap);
    });

    // Uncheck unused checkbox if the lesson field has a value
    var unusedCheckbox = form.find(".unused");
    form.find(".lesson").on("change", function(e) {
      if (form.find(".lesson").val() != "") {
        unusedCheckbox.prop("checked", false);
      }
    });

    // Reset unit and lesson field when unused is checked
    unusedCheckbox.on("change", function(e) {
      unitField.val("");
      onUnitFieldChange(form, lessonsMap);
    });

    form.find("select, input[type='checkbox']").on("change", function(e) {
      filterQuestions(form);
    });

    form.find("input[type='text']").on("keyup", function(e) {
      filterQuestions(form);
    });

    form.on("submit", function(e) {
      e.preventDefault();
    });
  }

  function setUpFilterBindings() {
    // Bind click on a filter button to open/close its matching filter popup
    $(".filter-button").on("click", function(e) {
      e.stopPropagation();
      var filterPopup = $(this).next(".filter-popup");
      if (filterPopup.is(":visible")) {
        closeFilter(filterPopup);
      } else {
        showFilter(filterPopup);
        filterPopup.find("input:first").focus();
      }
    });

    // Bind click on a close button to close its matching filter popup
    $(".filter-popup .close-button").on("click", function(e) {
      closeFilter($(this).closest(".filter-popup"));
    });
  }

  setUpQuestionFilter();
  setUpFilterBindings();
}

function init() {
  setUpDraftStatus();
  setLocalTimes();
  setUpModalWindow();
  setUpTableSorting();
  setUpFiltering();
};

init();
