function parseJson(s) {
  var XSSI_PREFIX = ")]}'";
  return JSON.parse(s.replace(XSSI_PREFIX, ""));
}

function onSubmitButtonClick(key, xsrfToken, button) {
  var formData = $("#" + key).serializeArray();
  var request = JSON.stringify({
    "xsrf_token": xsrfToken,
    "key": key,
    "payload": {
      "form_data": formData
    }
  });

  $.ajax({
    type: "POST",
    url: "rest/modules/questionnaire",
    data: {"request": request},
    dataType: "text",
    success: function(data) {
      onAjaxPostFormData(data, button);
    }
  });
  gcbTagEventAudit({key: key, form_data: formData}, "questionnaire");
}

function onAjaxPostFormData(data, button) {
  var data = parseJson(data);
  if (data.status == 200) {
    cbShowMsgAutoHide(data.message);
    $(button).parent().find("div.post-message").removeClass("hidden");
  } else {
    cbShowMsg(data.message);
  }
}

function ajaxGetFormData(xsrfToken, key) {
  $.ajax({
    type: "GET",
    url: "rest/modules/questionnaire",
    data: {"xsrf_token": xsrfToken, "key": key},
    dataType: "text",
    success: function(data) {
      onAjaxGetFormData(data, key);
    }
  });
}

function onAjaxGetFormData(data, key) {
  var data = parseJson(data);
  if (data.status == 200) {
    var payload = JSON.parse(data.payload || "{}");
    setFormData(payload.form_data || {}, key);
  }
  else {
    cbShowMsg(data.message);
    return;
  }
}

function setFormData(data, key) {
  for (var i=0; i < data.length; i++) {
    var name = data[i].name;
    var value = data[i].value;
    var elt = $("#" + key).find("[name='" + name + "']");
    var tagName = elt.prop("tagName");
    var type = elt.attr("type");

    if (tagName == "SELECT"  && elt.attr("multiple")) {
      elt.find("> option").each(function() {
        if ($(this).val() == value) {
          this.selected = true;
        }
      });
    }
    else if (tagName == "TEXTAREA" || tagName == "SELECT") {
      elt.val(value);
    }
    else {
      switch(type) {
        case "checkbox":
          elt.filter("[value='" + value + "']").prop("checked", true);
          break;
        case "radio":
          elt.filter("[value='" + value + "']").prop("checked", true);
          break;
        default:
          elt.val(value);
          break;
      }
    }
  }
}

function disableForm(button, key) {
  $("#" + key).find("input,select,textarea").prop("disabled", true);
  $(button).prop("disabled", true);
}

function init() {
  $("div.gcb-questionnaire > button.questionnaire-button").each(function(i, button) {
    button = $(button);
    var xsrfToken = button.data("xsrf-token");
    var key = button.data("form-id");
    var disabled = button.data("disabled");
    var registered = button.data("registered");

    if (! registered) {
      cbShowMsg("Only registered students can submit answers.");
      disableForm(button, key);
    } else {
      ajaxGetFormData(xsrfToken, key);
      if (disabled) {
        disableForm(button, key);
      } else {
        button.click(function() {
          onSubmitButtonClick(key, xsrfToken, button);
          return false;
        });
      }
    }
  });
}

init();
