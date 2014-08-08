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
  cbShowMsg(response.message);
  setTimeout(cbHideMsg, 5000);
}

/**
 * Toggle draft status on click on padlock icon.
 */
function setupDraftStatus() {
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
function setupModalWindow() {
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
function setupTableSorting() {
  // Sort table on header click
  $(".assets-table th").on("click", function(e) {
    sortTable($(this));
  });
  // Default: sort ascending on first column
  $(".assets-table th:first-child").each(function() {
    sortTable($(this));
  });
}

function init() {
  setupDraftStatus();
  setLocalTimes();
  setupModalWindow();
  setupTableSorting();
};

init();
