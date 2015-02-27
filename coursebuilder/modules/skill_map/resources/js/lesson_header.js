var ARROW_DOWN_CLASS = 'md-keyboard-arrow-down';
var ARROW_UP_CLASS = 'md-keyboard-arrow-up';
var HIGHLIGHTED_CARD_CLASS = 'highlighted';
var SHADED_CARD_CLASS = 'shaded';
// Only log skill hover events where the hover lasts for this long.
var SKILL_HOVER_CUTOFF_MS = 1000;

var dependencyMap = null;
var skillHoverStart = 0;

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
        emitPanelOpenEvent(true);
      } else {
        openButton.removeClass(ARROW_UP_CLASS);
        openButton.addClass(ARROW_DOWN_CLASS);
        emitPanelOpenEvent(false);
      }
    });
  });
}
function bindSkillHover() {
  $('div.skill-panel div.skills-in-this-lesson .skill').hover(
      function() {
        // On enter handler
        var dependencyData = dependencyMap[$(this).data('skillId')];

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

        skillHoverStart = now();
      },
      function() {
        // On leave handler
        $('div.skill-panel .skill-card').removeClass(HIGHLIGHTED_CARD_CLASS);
        $('div.skill-panel .skill-card').removeClass(SHADED_CARD_CLASS);

        if (now() - skillHoverStart > SKILL_HOVER_CUTOFF_MS) {
          emitSkillHoverEvent($(this).data('skillId'));
        }
      });
}
function bindTooltips() {
  $('div.skill-panel .skills-in-this-lesson').tooltip({
    items: 'li.skill',
    content: function() {
      return (
          '<b>' + $(this).text().trim() + '</b>: ' +
          $(this).data('skillDescription').trim());
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
      return (
          '<b>' + $(this).find('.name').text().trim() + '</b>: ' +
          $(this).find('.content').text().trim());
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
  bindSkillHover();
  bindTooltips();
  detailsPanel.hide();
  openButton.addClass(ARROW_DOWN_CLASS);
  dependencyMap = $('div.skill-panel').data('dependencyMap');
}

if ($('div.skill-panel').length > 0) {
  init();
}
