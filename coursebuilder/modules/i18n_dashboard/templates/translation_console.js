var VERB_NEW = 1;
var VERB_CHANGED = 2;
var VERB_CURRENT = 3;

var VERB_NEW_CLASS = "verb-new";
var VERB_CHANGED_CLASS = "verb-changed";
var VERB_CURRENT_CLASS = "verb-current";
var EDITED_CLASS = "edited";

var NOT_STARTED_TRANSLATION = 0;
var VALID_TRANSLATION = 1;
var INVALID_TRANSLATION = 2;

function getVerbClassName(verb) {
  switch (verb) {
    case VERB_NEW:
     // new source value added, no mapping to target exists
      return VERB_NEW_CLASS;
    case VERB_CHANGED:
      // source value changed, mapping to target likely invalid
      return VERB_CHANGED_CLASS;
    case VERB_CURRENT:
      // source value is mapped to valid target value
      return VERB_CURRENT_CLASS;
    default: return "";
  }
}

/**
 * Iterate over the items of the InputEx form.
 *
 * @param env The cb_global object
 * @param action A function which is passed the sections and items of the form
 */
function iterateFormItems(env, action) {
  $.each(env.form.inputsNames.sections.subFields, function(i, section) {
    $.each(section.inputsNames.data.subFields, function(j, item) {
      action(j, section, item);
    })
  });
}

function getSectionByName(env, name){
  var section = null;
  $.each(env.form.inputsNames.sections.subFields, function(i, s){
    if (s.inputsNames.name.getValue() == name) {
      section = s;
      return false;
    }
  });
  return section;
}

function markAsEdited(item) {
  item.changed.setValue(true);
  $(item.changed.el).closest("fieldset")
      .removeClass().addClass(EDITED_CLASS);
}

function insertValidateButton() {
  var button = new Y.inputEx.widget.Button({
    type: "submit-link",
    value: "Validate",
    className: "inputEx-Button inputEx-Button-Submit-Link gcb-pull-left",
    onClick: onClickValidate
  });
  button.render($("div.inputEx-Form-buttonBar")[0]);

  // Button rendering will append the button at the end of the div, so we
  // move it to the second position after it's been created.
  $("div.inputEx-Form-buttonBar > a:first-child").after(button.el);
  cb_global.form.buttons.splice(1, 0, button);
}

function onClickValidate() {
  disableAllControlButtons(cb_global.form);
  var request = {
    key: cb_global.save_args.key,
    xsrf_token:  cb_global.xsrf_token,
    payload: JSON.stringify(cb_global.form.getValue()),
    validate: true
  }
  Y.io(cb_global.save_url, {
    method: "PUT",
    data: {"request": JSON.stringify(request)},
    on: {
      complete: onValidateComplete
    }
  });
  return false;
}

function onValidateComplete(transactionId, response, args) {
  enableAllControlButtons(cb_global.form);
  if (response.status != 200) {
    cbShowMsg("Server error, please try again.");
    return;
  }

  response = parseJson(response.responseText);
  if (response.status != 200) {
    cbShowMsg(response.message);
  }

  var payload = JSON.parse(response.payload || "{}");
  for (var name in payload) {
    if (payload.hasOwnProperty(name)) {
      var section = getSectionByName(cb_global, name);
      addValidationFeedbackTo(section.divEl.firstChild, payload[name]);
    }
  }
}

function addValidationFeedbackTo(fieldsetEl, feedback) {
  $("div.validation-feedback", fieldsetEl).remove();
  var feedbackDiv = $("<div/>").addClass("validation-feedback");
  if (feedback.status == VALID_TRANSLATION) {
    feedbackDiv.addClass("valid");
  } else {
    feedbackDiv.addClass("invalid");
  }
  feedbackDiv.append($("<div/>").addClass("icon"));
  feedbackDiv.append($("<div/>").addClass("errm").text(feedback.errm));

  $(fieldsetEl).append(feedbackDiv);
}

function markValidationFeedbackStale(sectionField) {
  $("div.validation-feedback", sectionField.divEl)
      .removeClass()
      .addClass("validation-feedback stale");
}

function resizeTogether() {
  $("div.active > div > textarea").each(function() {
    var height = $(this).height();

    if (height !== this._gcbLastHeight) {
      $(this).closest("fieldset").find("div.disabled > div > textarea").height(height);
    }
    this._gcbLastHeight = height;
  });
}

$(function() {
  iterateFormItems(cb_global, function(index, sectionField, itemField) {
    var verb = itemField.inputsNames.verb.getValue();
    $(itemField.divEl.firstChild).addClass(getVerbClassName(verb));

    var caption = $("<p class=\"caption\">chunk " + (index + 1) + "</p>");
    $(itemField.divEl.firstChild).append(caption);
  });

  $(".disabled textarea").prop("disabled", true);

  // Insert the status indicators into the DOM
  $(".translation-item fieldset fieldset")
      .append($("<div class=\"status\"></div>"));

  // Set up the accept buttons to appear when there is changed content
  iterateFormItems(cb_global, function(index, sectionField, itemField) {
    var button = $("<button class=\"accept inputEx-Button\">Accept</button>");
    button.click(function() {
      markAsEdited(itemField.inputsNames);
      return false;
    });
    $(itemField.divEl.firstChild).append(button);
  });

  $(".translation-console > fieldset > div:last-child").before($(
      "<div class=\"translation-header\">" +
      "  <div>Source (<span class=\"source-locale\"></span>)</div>" +
      "  <div>Translation (<span class=\"target-locale\"></span>)</div>" +
      "</div>"));
  var formValue = cb_global.form.getValue();
  $(".translation-header .source-locale").text(formValue['source_locale']);
  $(".translation-header .target-locale").text(formValue['target_locale']);

  iterateFormItems(cb_global, function(index, sectionField, itemField) {
    $(itemField.inputsNames.target_value.el).on("input change", function() {
      // Listen on "change" for older browser support
      markAsEdited(itemField.inputsNames);
      markValidationFeedbackStale(sectionField);
    });
  });

  cb_global.onSaveComplete = function() {
    iterateFormItems(cb_global, function(index, sectionField, itemField) {
      var item = itemField.inputsNames;
      if (item.changed.getValue()) {
        item.verb.setValue(VERB_CURRENT);
        $(item.changed.el).closest('fieldset')
            .removeClass().addClass(VERB_CURRENT_CLASS);
      }
      item.changed.setValue(false);
    });
    cb_global.lastSavedFormValue = cb_global.form.getValue();
  };

  insertValidateButton();
  setInterval(resizeTogether, 10);
});
