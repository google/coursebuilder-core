var ARROW_DOWN_CLASS = 'md-keyboard-arrow-down';
var ARROW_UP_CLASS = 'md-keyboard-arrow-up';
var HIGHLIGHTED_CARD_CLASS = 'highlighted';
var CLICKABLE_SKILL_CLASS = 'clickable';
var SHADED_CARD_CLASS = 'shaded';

var dependencyMap = null;

function now() {
  return new Date().getTime();
}
function emitPanelOpenEvent(isOpened) {
  var data = {
    type: 'open',
    isOpened: isOpened
  };
  gcbAudit(gcbCanPostEvents, data, 'skill-panel', true)
}
function emitSkillHoverEvent(skillId) {
  var data = {
    type: 'skill-hover',
    skillId: skillId
  };
  gcbAudit(gcbCanPostEvents, data, 'skill-panel', true)
}
function bindOpenButton() {
  var detailsPanel = $('div.skill-panel div.skill-details');
  var openButton = $('div.skill-panel div.open-control button');
  openButton.click(function() {
    detailsPanel.toggle(400, function() {
      if (detailsPanel.is(':visible')) {
        openButton.removeClass(ARROW_DOWN_CLASS);
        openButton.addClass(ARROW_UP_CLASS);
        $('div.skill-panel ol.skill-display-root > li.skill')
            .addClass(CLICKABLE_SKILL_CLASS);
        emitPanelOpenEvent(true);
      } else {
        openButton.removeClass(ARROW_UP_CLASS);
        openButton.addClass(ARROW_DOWN_CLASS);
        $('div.skill-panel ol.skill-display-root > li.skill')
            .removeClass(CLICKABLE_SKILL_CLASS);
        emitPanelOpenEvent(false);
      }
    });
  });
}
function highlightCards(skillId) {
  var dependencyData = dependencyMap[skillId];

  $('div.skill-panel .skill-card').addClass(SHADED_CARD_CLASS);

  $.each(dependencyData.depends_on, function() {
    var skillId = this;
    $('div.skill-panel ol.depends-on .skill-card')
        .filter(function() {
          return $(this).data('skillId') == skillId;
        })
        .removeClass(SHADED_CARD_CLASS)
        .addClass(HIGHLIGHTED_CARD_CLASS);
  });

  $.each(dependencyData.leads_to, function() {
    var skillId = this;
    $('div.skill-panel ol.leads-to .skill-card')
        .filter(function() {
          return $(this).data('skillId') == skillId;
        })
        .removeClass(SHADED_CARD_CLASS)
        .addClass(HIGHLIGHTED_CARD_CLASS);
  });

  emitSkillHoverEvent(skillId);
}
function resetCardHighlights() {
  $('ol.skill-display-root .skill').removeClass(HIGHLIGHTED_CARD_CLASS);
  $('ol.skill-display-root .skill').removeClass(SHADED_CARD_CLASS);
  $('div.skill-panel .skill-card').removeClass(HIGHLIGHTED_CARD_CLASS);
  $('div.skill-panel .skill-card').removeClass(SHADED_CARD_CLASS);
}
function bindSkillClick() {
  $('div.skill-panel div.skills-in-this-lesson .skill').click(function() {
    if (! $(this).hasClass(CLICKABLE_SKILL_CLASS)) {
      return;
    }
    $('ol.skill-display-root .skill').addClass(SHADED_CARD_CLASS);
    $(this).removeClass(SHADED_CARD_CLASS).addClass(HIGHLIGHTED_CARD_CLASS);
    highlightCards($(this).data('skillId'));
  });
  $(window).click(function(evt) {
    if ($(evt.target).closest('.skill-panel ol.skill-display-root').length == 0) {
      resetCardHighlights();
    }
  });
}
function bindTooltips() {
  $('div.skill-panel .skills-in-this-lesson').tooltip({
    items: 'li.skill',
    content: function() {
      var description = $(this).data('skillDescription').trim();
      if (description) {
        return ('<b>' + $(this).text().trim() + '</b>: ' + description);
      } else {
        return null;
      }
    },
    position: {
      my: 'center top',
      at: 'center bottom+10'
    },
    tooltipClass: 'skill-panel-tooltip'
  });
  $('div.skill-panel .skill-details .skill-card .description').tooltip({
    items: '.skill-card',
    content: function() {
      var content = $(this).find('.content').text().trim();
      if (content) {
        return (
            '<b>' + $(this).find('.name').text().trim() + '</b>: ' + content);
      } else {
        return null;
      }
    },
    position: {
      my: 'center top',
      at: 'center bottom-40'
    },
    tooltipClass: 'skill-panel-tooltip'
  });
}
function init() {
  var detailsPanel = $('div.skill-panel div.skill-details');
  var openButton = $('div.skill-panel div.open-control button');

  bindOpenButton();
  bindSkillClick();
  bindTooltips();
  detailsPanel.hide();
  openButton.addClass(ARROW_DOWN_CLASS);
  dependencyMap = $('div.skill-panel').data('dependencyMap');
}

if ($('div.skill-panel').length > 0) {
  init();
}
