var ESC_KEY = 27;

$(function() {
  // Fill in local times by using timestamp attribute
  $(".assets-table tbody .timestamp").each(function() {
    if ($(this).data("timestamp")) {
      $(this).html((new Date(
        parseFloat($(this).data("timestamp"))*1000)).toLocaleString());
    }
  });
  // Attach handlers
  $(".assets-table th").on("click", function(e) {
    sortTable($(this));
  });
  var modal = $("#modal-window");
  // Bind preview button to show question preview
  $(".preview-button").on("click", function(e) {
    openModal(modal);
    var params = {action: "question_preview", quid: $(this).data("quid")};
    modal.find("#content").html($("<iframe />").attr(
      {id: "question-preview", src: "dashboard?" + $.param(params)}));
  });
  // Bind click on background and on close button to close window
  modal.find("#background, .close-button").on("click", function(e) {
    closeModal(modal);
  });
  // Default: sort ascending on first column
  $(".assets-table th:first-child").each(function() {
    sortTable($(this));
  });
});

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