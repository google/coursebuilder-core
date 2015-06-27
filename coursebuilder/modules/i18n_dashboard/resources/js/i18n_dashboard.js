var xsrfToken = $("table.i18n-progress-table").data("isTranslatableXsrfToken");

function onTranslatableCheckboxClicked(evt) {
  var target = $(evt.target);
  var isChecked = target.prop("checked");
  var request = JSON.stringify({
    "xsrf_token": xsrfToken,
    "payload": {
      "resource_key": target.closest("tr").data("resource-key"),
      "value": isChecked
    }
  });

  $.ajax({
    url: "rest/modules/i18n_dashboard/is_translatable",
    type: "POST",
    data: {"request": request},
    dataType: "text",
    success: onTranslatableCheckboxResponse
  });

  if (isChecked) {
    target.closest("tr").removeClass('not-translatable');
  } else {
    target.closest("tr").addClass('not-translatable');
  }
}

function onTranslatableCheckboxResponse(data) {
  data = parseAjaxResponse(data);
  if (data.status != 200) {
    cbShowAlert(data.message);
    return;
  }
}

function bind() {
  $("input.is-translatable").click(onTranslatableCheckboxClicked);
}

bind();
