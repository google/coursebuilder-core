function parseJson(s) {
  var XSSI_PREFIX = ')]}\'';
  return JSON.parse(s.replace(XSSI_PREFIX, ''));
}

function onManualProgressClick(target) {
  var progressDiv = $(target.closest('.manual-progress'));
  var url = progressDiv.data('url');
  var key = progressDiv.data('key');
  var xsrfToken = progressDiv.data('xsrf-token');
  doPostManualProgress(url, key, xsrfToken);
}

function doPostManualProgress(url, key, xsrfToken) {
  $.ajax({
    type: 'POST',
    url: url,
    data: {'key': key, 'xsrf_token': xsrfToken},
    dataType: 'text',
    success: function(data) {
      onAjaxPostManualCompletion(data);
    },
  });
}

function onAjaxPostManualCompletion(data) {
  data = parseJson(data);
  if (data.status == 200) {
    cbShowMsgAutoHide(data.message);
  } else {
    cbShowMsg(data.message);
  }
}

$(function() {
  $('div.manual-progress button').click(function() {
    onManualProgressClick(this);
  });
});
