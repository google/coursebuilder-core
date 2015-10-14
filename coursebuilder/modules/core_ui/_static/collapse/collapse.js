/* Collapse Component */

/**
  * Call this whenever you add a new collapsible, or alter the contents of an
  * existing one.  This calculates its height so it can be hidden.
  */
function updateCollapse() {
  $('.gcb-collapse__content').each(function() {
    var content = $(this);
    content.css('margin-top', -content.height());
  });
}

function setUpCollapse() {
  $(document.body).on('click', '.gcb-collapse__button', function() {
    var button = $(this);
    var collapse = button.parents('.gcb-collapse:first');
    var accordion = collapse.parents('.gcb-accordion:first');
    if (collapse.hasClass('gcb-collapse--disabled')) {
      return;
    }
    if (!collapse.is('.gcb-collapse--opened')) {
      accordion.find('.gcb-collapse').removeClass('gcb-collapse--opened');
    }
    collapse.toggleClass('gcb-collapse--opened');
  });
  $(function() {
    updateCollapse();
  });
}

$(function(){
  setUpCollapse();
});
