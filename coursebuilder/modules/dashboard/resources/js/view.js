//XSSI prefix. Must be kept in sync with models/transforms.py.
var XSSI_PREFIX = ")]}'";
var ESC_KEY = 27;

/**
 * Parses JSON string that starts with an XSSI prefix.
 */
function parseJson(s) {
  return JSON.parse(s.replace(XSSI_PREFIX, ""));
}

/* These functions are reused in various pages */
window.parseAjaxResponse = parseJson;
window.parseAjaxResponsePayload = function(text) {
  var wrapper = parseAjaxResponse(text);
  wrapper.payload = JSON.parse(wrapper.payload);
  return wrapper;
}

function setDraftStatus(padlock, isDraft) {
  if (isDraft) {
    padlock.removeClass("public").addClass("private");
  } else {
    padlock.removeClass("private").addClass("public");
  }
}

function setDraftStatusCallback(data, padlock) {
  var response = parseJson(data);
  var isDraft = padlock.hasClass("private")
  if (response.status != 200){
    cbShowAlert("Error: " + response.message);
    setDraftStatus(padlock, ! isDraft);
    return;
  }
  var payload = parseJson(response.payload);
  if (payload["is_draft"] != isDraft) {
    cbShowAlert("The page contains inconsistent data. Please refesh.");
    setDraftStatus(padlock, payload["is_draft"]);
    return;
  }
  cbShowMsgAutoHide(response.message);
}

function onDraftStatusClick() {
  var padlock = $(this);
  var setDraft = $(this).hasClass("public");
  // Optimistically update icon and revert if server confirmation not received
  setDraftStatus(padlock, setDraft);
  $.post(
    "dashboard",
    {
      action: "set_draft_status_" + $(this).data("component-type"),
      key: $(this).data("key"),
      type: $(this).data("component-type"),
      set_draft: setDraft ? 1 : 0,
      xsrf_token: $(this).parents(".xsrf-token-holder").data(
        "status-xsrf-token-" + $(this).data("component-type"))
    },
    function(data) {
      setDraftStatusCallback(data, padlock);
    },
    "text"
  );
}

function onCloneQuestionClick(event) {
  event.preventDefault();
  $.post(
    "dashboard",
    {
      action: "clone_question",
      key: $(this).data("key"),
      xsrf_token: $("#question-table").data("clone-question-token"),
    },
    function(data) {
      // On successful POST, reload page to show new clone.
      document.location.reload();
    }
  );
}

function openModal() {
  // Bind Esc press to close window
  $(document).on("keyup.modal", function(e) {
    if (e.keyCode == ESC_KEY) {
        closeModal();
    }
  });
  $("#modal-window").show();
}

function closeModal() {
  $("#modal-window, #modal-container > div").hide();
  //Remove Esc binding
  $(document).off("keyup.modal");
}

function insertSorted(parentElement, newChild) {
  var inserted = false;
  parentElement.children().each(function() {
    if($(this).text() > newChild.text()) {
      newChild.insertBefore($(this));
      inserted = true;
      return false;
    }
  });
  if (!inserted) {
    parentElement.append(newChild);
  }
}

function updateQuestionLocations(questionRow, groupRow) {
  var qLocationsList = questionRow.find("td.locations ul");
  groupRow.find("td.locations ul li").each(function() {
    var groupLocation = $(this);
    var added = false;
    qLocationsList.find("li").each(function() {
      if ($(this).data("id") == groupLocation.data("id")) {
        var count = parseInt($(this).data("count")) + parseInt(
          groupLocation.data("count"));
        $(this).data("count", count);
        $(this).find(".count").text(" (" + count.toString() + ")");
        added = true;
        return false; //break
      }
    })
    if (! added) {
      qLocationsList.append(groupLocation);
    }
  });
}

function addToGroupCallback(data) {
  var response = parseJson(data);
  if (response.status != 200) {
    cbShowAlert("Error: " + response.message);
  } else {
    cbShowMsgAutoHide(response.message);
    var payload = parseJson(response.payload);
    var questionRow = $(
      "#question-table tr[data-quid='" + payload["question-id"] + "']");
    var groupRow = $(
      "#question-group-table tr[data-qgid='" + payload["group-id"] + "']");
    // Add group description to question's list of groups
    insertSorted(
      questionRow.find("td.groups ul"),
      $("<li/>").text(groupRow.find("td.description").text())
    );
    updateSortTable($("#question-table th").eq(1));
    // Add question description to group's list of questions
    insertSorted(
      groupRow.find("td.questions ul"),
      $("<li/>").text(questionRow.find("td.description").text())
    );
    updateSortTable($("#question-group-table th").eq(1));
    // Add the group's locations to the question's locations
    updateQuestionLocations(questionRow, groupRow);
    updateSortTable($("#question-table th").eq(2));
  }
  closeModal();
  $("#add-to-group .submit").prop("disabled", false);
}

/**
 * Click handler that sorts a column based on the clicked column header.
 */
function sortTableByClick() {
  var sortAscending = true;
  // On click always sort ascending, unless it's already sorted ascending
  if ($(this).hasClass("sort-asc")) {
    sortAscending = false;
  }
  sortTable($(this), sortAscending)
}

function sortTable(columnHeader, sortAscending) {
  var tableBody = columnHeader.closest(".assets-table").find("tbody");
  var columnIndex = columnHeader.index();
  // Remove any sorting classes from any column
  columnHeader.parent().children().removeClass("sort-desc sort-asc");
  // Attach relevant sorting class
  columnHeader.addClass(sortAscending ? "sort-asc" : "sort-desc");
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
 * Resorts a table according to the sorting class of the supplied column header.
 */
function updateSortTable(columnHeader) {
  if (columnHeader.hasClass("sort-asc")) {
    sortTable(columnHeader, true);
  } else if (columnHeader.hasClass("sort-desc")) {
    sortTable(columnHeader, false);
  }
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

/**
 * Toggle draft status on click on padlock icon.
 */
function setUpDraftStatus() {
  $(".icon-draft-status:not(.inactive)").on("click", onDraftStatusClick);
}

function setUpCloneQuestion() {
  $(".clone-question").on("click", onCloneQuestionClick);
}

/**
 * Fills in local times using data-timestamp attribute.
 */
function setUpLocalTimes() {
  $(".assets-table tbody .timestamp").each(function() {
    if ($(this).data("timestamp")) {
      $(this).html((new Date(
        parseFloat($(this).data("timestamp"))*1000)).toLocaleString());
    }
  });
}

/**
 * Sets up handlers for modal window.
 */
function setUpModalWindow() {
  // Bind click on background and on close button to close window
  $("#modal-background, #modal-window .close-button").on("click", function(e) {
    closeModal();
  });
  $("#modal-container > div").hide();
}

function setUpQuestionPreview() {
  // Bind preview button to show question preview
  $("table.assets-table .preview-question").on("click", function(e) {
    openModal();
    var params = {
        action: "question_preview",
        quid: $(this).closest("tr").data("quid")
    };
    $("#modal-body").html($("<iframe />").attr(
      {src: "dashboard?" + $.param(params)})).show();
  });
}

function setUpQuestionGroupPreview() {
  // Bind preview button to show question preview
  $("table.assets-table .preview-question-group").on("click", function(e) {
    openModal();
    var params = {
        action: "question_group_preview",
        qgid: $(this).closest("tr").data("qgid")
    };
    $("#modal-body").html($("<iframe />").attr(
      {src: "dashboard?" + $.param(params)})).show();
  });
}

function setUpAddToGroup() {

  function addBindings() {
    $(".add-question-to-group").on("click", function(e) {
      openModal();
      var popup = $("#add-to-group");
      var row = $(this).closest("tr");
      popup.find(".description").text(row.find(".description").text());
      popup.find(".question").val(row.data("quid"));
      popup.show();
    });

    $("#add-to-group .submit").on("click", function(e) {
      e.preventDefault();
      $("#add-to-group .submit").prop("disabled", true);
      $.post(
        "dashboard",
        {
          action: "add_to_question_group",
          group_id: $("#add-to-group .group").val(),
          weight: $("#add-to-group .weight").val(),
          question_id: $("#add-to-group .question").val(),
          xsrf_token: $("#question-table").data("qg-xsrf-token")
        },
        addToGroupCallback,
        "text"
      );
    });
  }

  if($("#question-table").size() == 1) {
    // Populate question groups dropdown
    appendOptions(
      $("#add-to-group .group"), $("#question-table").data("groups"));
    addBindings();
  }
};

/**
 * Sets up table sorting and default sorting order.
 */
function setUpTableSorting() {
  // Sort table on header click
  var headers = $(".assets-table th:not(.gcb-list__cell--icon)")
  headers.on("click", sortTableByClick);
  headers.each(function(){
    $(this).append('<i class="material-icons gcb-list__sort-indicator"></i>')
  })
  // Default: sort ascending on first column
  sortTable($(headers[0]), true);
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
      // Make sure the row is first visible
      $(this).show();
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
      $("#question-table tfoot").show();
    } else {
      $("#question-table tfoot").hide();
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

/**
 * Returns a list with 10 different colors. To be used with Google
 * Visualizations graphs.
 * The colors have been taken from the dc library charts, see examples in
 * Analytics > Questions tab.
 */
getGVColorPallet = function () {
  return ['#6baed6', '#fd8d3c', '#74c476', '#9e9ac8',
          '#3182bd', '#e6550d', '#31a354', '#756bb1',
          '#929292', '#636363',]
}

function init() {
  setUpDraftStatus();
  setUpCloneQuestion();
  setUpLocalTimes();
  setUpModalWindow();
  setUpQuestionPreview();
  setUpQuestionGroupPreview();
  setUpAddToGroup();
  setUpTableSorting();
  setUpFiltering();
};

init();
