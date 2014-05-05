$(function() {
  $("#gcb-nav-y").click(function(evt) {
    $("#gcb-nav-y").addClass("shown");
    if (evt.target.tagName != "A") {
      return false;
    }
    return true;
  });
  $(document.body).click(function() {
    $("#gcb-nav-y").removeClass("shown");
  });
});
