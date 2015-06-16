/**
 * Shows skill card tooltip.
 * Duplicates part of SkillPanel.bindTooltips()
 */
$('.skill-panel .skill-card .description').each(function() {
  $(this).tooltip({
    items: '.skill-card',
    content: function () {
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
});
