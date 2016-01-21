function formatDate(timestamp) {
  return (new Date(parseFloat(timestamp)*1000)).toLocaleString();
}

$(function() {
  $('.local-datetime').each(function() {
    var element = $(this);
    var timestamp = element.data('timestamp');
    if (timestamp) {
      element.text(formatDate(timestamp));
    }
  })

  var POLL_INTERVAL_MILLISECONDS = 5000;
  function update_job_status() {
    $.ajax({
      method: 'get',
      url: JOB_STATUS_URL,
      dataType: 'text',
      success: function(text) {
        var running = JSON.parse(gcb.parseJsonResponse(text).payload).running;
        $('.running-state').toggle(running);
        $('.idle-state').toggle(!running);
        setTimeout(update_job_status, POLL_INTERVAL_MILLISECONDS)
      },
    })
  }

  update_job_status();
});
