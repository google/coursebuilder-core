$(function() {
  function showMenu() {
    $("#gcb-nav-y").addClass("shown");
    $(document.body).addClass('hide-overflow');
  }
  function hideMenu() {
    $("#gcb-nav-y").removeClass("shown");
    $(document.body).removeClass('hide-overflow');
  }
  function toggleMenu() {
    if ($("#gcb-nav-y").hasClass("shown")) {
      hideMenu();
    } else {
      showMenu();
    }
  }
  $("#gcb-nav-y").click(function(evt) {
    if (evt.target.id == "gcb-nav-y") {
      toggleMenu();
    }
  });
  $(document.body).on("touchstart", function(eventt) {
    if (! $.contains($("#gcb-nav-y").get(0), event.target)) {
      hideMenu();
    }
  });
});
