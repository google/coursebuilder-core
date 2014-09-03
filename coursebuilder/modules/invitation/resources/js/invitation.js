$(function() {
  var XSRF_TOKEN = $("#invitation-div").data("xsrf-token");
  // XSSI prefix. Must be kept in sync with models/transforms.py.
  var XSSI_PREFIX = ")]}'";

  function parseJson(s) {
    return JSON.parse(s.replace(XSSI_PREFIX, ''));
  }

  function onSendButtonClick() {
    var request = JSON.stringify({
      "xsrf_token": XSRF_TOKEN,
      "payload": {
        "emailList": $("#email-list").val()
      }
    });
    $.ajax({
      type: "POST",
      url: "rest/modules/invitation",
      data: {"request": request},
      dataType: "text",
      success: onAjaxPostSuccess,
    });
  }

  function onAjaxPostSuccess(data) {
    var data = parseJson(data);
    if (data.status != 200) {
      cbShowMsg(data.message);
    } else {
      cbShowMsgAutoHide(data.message);
    }
  }

  function init() {
    $("#send-button").click(onSendButtonClick);
  }

  init();
});
