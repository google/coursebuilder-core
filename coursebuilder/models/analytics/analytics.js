$(function() {
  var REFRESH_RATE_MS = 5000;
  var prefix = 'gcb-cancel-visualization-';
  var runningVisNames = $('[id^="' + prefix + '"]').map(function() {
    return $(this).attr('id').substring(prefix.length);
  }).toArray();

  function checkAnalyticsProgress() {
    if (runningVisNames.length) {
      $.ajax({
        method: 'GET',
        url: 'analytics/rest/status',
        traditional: true,
        data: {
          visualization: runningVisNames
        },
        dataType: 'text',
        success: function(text) {
          var wrapper = parseAjaxResponsePayload(text);
          if (wrapper.status == 200) {
            applyChange(wrapper.payload);
          }
          repeat();
        }
      })
    }
  }
  function applyChange(data) {
    // update state
    runningVisNames = $.grep(runningVisNames, function(item) {
      return data.finished.indexOf(item) === -1;
    });

    // render new state
    data.finished.forEach(function(name) {
      // change status message
      var button = $('#' + prefix + name);
      button.closest('.section').find('.status-message').text(
        "Job is finished."
      );

      // remove global status message
      $('#gcb_log_rest_source_' + name).hide()

      // change cancel button
      var reloader = $(
        '<a class="gcb-button gcb-icon-button">' +
        ' <span class="icon md-visibility"></span>' +
        ' <span>Display Results</span>' +
        '</a>');
      reloader.on('click', function() {
        window.location.reload();
      });
      button.replaceWith(reloader);
    });
  }
  function repeat() {
    setTimeout(checkAnalyticsProgress, REFRESH_RATE_MS);
  }
  repeat();
})
