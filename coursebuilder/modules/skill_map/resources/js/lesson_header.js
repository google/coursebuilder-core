var ARROW_DOWN_CLASS = 'md-keyboard-arrow-down';
var ARROW_UP_CLASS = 'md-keyboard-arrow-up';
var HIGHLIGHTED_CARD_CLASS = 'highlighted';
var CLICKABLE_SKILL_CLASS = 'clickable';
var SHADED_CARD_CLASS = 'shaded';
var IS_INITIALIZED = 'initialized';

function now() {
  return new Date().getTime();
}

function SkillPanel(panelDiv) {
  this._panelDiv = panelDiv;
  this._dependencyMap = this._panelDiv.data('dependencyMap');
}
SkillPanel.prototype = {
  emitPanelOpenEvent: function(isOpened) {
    var data = {
      type: 'open',
      isOpened: isOpened
    };
    gcbAudit(gcbCanRecordStudentEvents, data, 'skill-panel', true)
  },

  emitSkillHoverEvent: function(skillId) {
    var data = {
      type: 'skill-hover',
      skillId: skillId
    };
    gcbAudit(gcbCanRecordStudentEvents, data, 'skill-panel', true)
  },

  bindOpenButton: function() {
    var that = this;
    var detailsPanel = this._panelDiv.find('div.skill-details');
    var openButton = this._panelDiv.find('div.open-control button');
    openButton.click(function() {
      detailsPanel.toggle(400, function() {
        if (detailsPanel.is(':visible')) {
          openButton.removeClass(ARROW_DOWN_CLASS);
          openButton.addClass(ARROW_UP_CLASS);
          that._panelDiv.find('ol.skill-display-root > li.skill')
              .addClass(CLICKABLE_SKILL_CLASS);
          that.emitPanelOpenEvent(true);
        } else {
          openButton.removeClass(ARROW_UP_CLASS);
          openButton.addClass(ARROW_DOWN_CLASS);
          that._panelDiv.find('ol.skill-display-root > li.skill')
              .removeClass(CLICKABLE_SKILL_CLASS);
          that.emitPanelOpenEvent(false);
        }
      });
    });
  },

  highlightCards: function(skillId) {
    var that = this;
    var dependencyData = this._dependencyMap[skillId];

    this._panelDiv.find('.skill-card').addClass(SHADED_CARD_CLASS);

    $.each(dependencyData.depends_on, function() {
      var skillId = this;
      that._panelDiv.find('ol.depends-on .skill-card')
          .filter(function() {
            return $(this).data('skillId') == skillId;
          })
          .removeClass(SHADED_CARD_CLASS)
          .addClass(HIGHLIGHTED_CARD_CLASS);
    });

    $.each(dependencyData.leads_to, function() {
      var skillId = this;
      that._panelDiv.find('ol.leads-to .skill-card')
          .filter(function() {
            return $(this).data('skillId') == skillId;
          })
          .removeClass(SHADED_CARD_CLASS)
          .addClass(HIGHLIGHTED_CARD_CLASS);
    });

    this.emitSkillHoverEvent(skillId);
  },

  resetCardHighlights: function() {
    this._panelDiv.find('ol.skill-display-root .skill').removeClass(HIGHLIGHTED_CARD_CLASS);
    this._panelDiv.find('ol.skill-display-root .skill').removeClass(SHADED_CARD_CLASS);
    this._panelDiv.find('.skill-card').removeClass(HIGHLIGHTED_CARD_CLASS);
    this._panelDiv.find('.skill-card').removeClass(SHADED_CARD_CLASS);
  },

  bindSkillClick: function() {
    var that = this;
    this._panelDiv.find('div.skills-in-this-lesson .skill').click(function() {
      if (! $(this).hasClass(CLICKABLE_SKILL_CLASS)) {
        return;
      }
      that._panelDiv.find('ol.skill-display-root .skill').addClass(SHADED_CARD_CLASS);
      $(this).removeClass(SHADED_CARD_CLASS).addClass(HIGHLIGHTED_CARD_CLASS);
      that.highlightCards($(this).data('skillId'));
    });
    $(window).click(function(evt) {
      if ($(evt.target).closest('.skill-panel ol.skill-display-root').length == 0) {
        that.resetCardHighlights();
      }
    });
  },

  bindTooltips: function() {
    this._panelDiv.find('.skills-in-this-lesson').tooltip({
      items: 'li.skill',
      content: function() {
        var description = $(this).data('skillDescription').trim();
        if (description) {
          var boldElement = $('<b>').text($(this).text().trim());
          var textElement = document.createTextNode(': ' + description);
          return $('<span>').append(boldElement).append(textElement);
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
    this._panelDiv.find('.skill-details .skill-card .description').tooltip({
      items: '.skill-card',
      content: function() {
        var content = $(this).find('.content').text().trim();
        if (content) {
          var name = $(this).find('.name').text().trim();
          var boldElement = $('<b>').text(name);
          var textElement = document.createTextNode(': ' + content);
          return $('<span>').append(boldElement).append(textElement);
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
  },

  init: function () {
    var detailsPanel = this._panelDiv.find('div.skill-details');
    var openButton = this._panelDiv.find('div.open-control button');

    this.bindOpenButton();
    this.bindSkillClick();
    this.bindTooltips();
    detailsPanel.hide();
    openButton.addClass(ARROW_DOWN_CLASS);

    this._panelDiv.data(IS_INITIALIZED, true);
  }
};

function init() {
  $('div.skill-panel').each(function() {
    var skillPanelDiv = $(this);
    if (! skillPanelDiv.data(IS_INITIALIZED)) {
      new SkillPanel($(this)).init();
    }
  });
}

init();
