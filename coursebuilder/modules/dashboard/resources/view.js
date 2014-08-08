$(function() {
  // Attach handlers
  $(".assets-table th").on("click", function(e) {
    sortTable($(this));
  });
  // Default: sort ascending on first column
  $(".assets-table th:first-child").each(function() {
    sortTable($(this));
  });
});

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
    var valueA = $(rowA).find("td").eq(columnIndex).text();
    var valueB = $(rowB).find("td").eq(columnIndex).text();
    if (valueA < valueB) {
      return sortAscending ? -1 : 1;
    } else if (valueA > valueB) {
      return sortAscending ? 1 : -1;
    } else {
      return 0;
    }
  }).appendTo(tableBody);
}