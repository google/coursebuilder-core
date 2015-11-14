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

if (!window.requestAnimationFrame) {
  window.requestAnimationFrame = window.setTimeout;
}

function toggleCollapse(collapse, open) {
  var ANIMATION_MS = 200;

  if (collapse.data('gcb-collapse-timeout')) {
    clearTimeout(collapse.data('gcb-collapse-timeout'));
  }

  // Display the element one frame before the animation begins
  // Can't use $.show() here because it will realize the element may already
  // be visible, but one frame later it won't be and we need to prevent that.
  requestAnimationFrame(function() {
    var content = collapse.find('.gcb-collapse__content');
    content.css({display: 'block'});

    requestAnimationFrame(function() {
      collapse.toggleClass('gcb-collapse--opened', open);

      if (!open) {
        collapse.addClass('gcb-collapse--closing');

        collapse.data('gcb-collapse-timeout', setTimeout(function() {
          collapse.removeClass('gcb-collapse--closing');
          content.css({display: 'none'});
        }, ANIMATION_MS));
      }
    });
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

    if (collapse.hasClass('gcb-collapse--opened')) {
      // close it
      toggleCollapse(collapse, false);
    } else {
      // open it and close another
      var otherCollapse = accordion.find('.gcb-collapse.gcb-collapse--opened');
      if (otherCollapse.length) {
        toggleCollapse(otherCollapse, false);
      }
      toggleCollapse(collapse, true);
    }
  });
  updateCollapse();
}

$(function(){
  setUpCollapse();
});
