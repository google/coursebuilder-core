var VERB_NEW_CLASS = "verb-new";
var VERB_CHANGED_CLASS = "verb-changed";
var VERB_CURRENT_CLASS = "verb-current";
var EDITED_CLASS = "edited";

function getVerbClassName(verb) {
  switch (verb) {
    case "1":
     // new source value added, no mapping to target exists
      return VERB_NEW_CLASS;
    case "2":
      // source value changed, mapping to target likely invalid
      return VERB_CHANGED_CLASS;
    case "3":
      // source value is mapped to valid target value
      return VERB_CURRENT_CLASS;
    default: return "";
  }
}

/**
 * Iterate over the items of the InputEx form.
 *
 * @param env The cb_global object
 * @param action A function which is passed the members of the item
 */
function iterateFormItems(env, action) {
  $.each(env.form.inputsNames.sections.subFields, function(i, section) {
    $.each(section.inputsNames.data.subFields, function(j, item) {
      action(item.inputsNames);
    })
  });
}

function markAsEdited(item) {
  item.changed.setValue(true);
  $(item.changed.el).closest("fieldset")
      .removeClass().addClass(EDITED_CLASS);
}

$(function() {
  $("input[name=\"verb\"]").each(function() {
    $(this).closest("fieldset").addClass(getVerbClassName($(this).val()));
  });

  $(".disabled textarea").prop("disabled", true);

  // Insert the status indicators into the DOM
  $(".translation-item fieldset fieldset")
      .append($("<div class=\"status\"></div>"));

  // Set up the accept buttons to appear when there is changed content
  iterateFormItems(cb_global, function(item) {
    var button = $("<button class=\"accept inputEx-Button\">Accept</button>");
    button.click(function() {
      markAsEdited(item);
      return false;
    });
    $(item.changed.el.parentNode.parentNode).append(button);
  });

  $(".translation-console > fieldset > div:last-child").before($(
      "<div class=\"translation-header\">" +
      "  <div>Source (<span class=\"source-locale\"></span>)</div>" +
      "  <div>Translation (<span class=\"target-locale\"></span>)</div>" +
      "</div>"));
  var formValue = cb_global.form.getValue();
  $(".translation-header .source-locale").text(formValue['source_locale']);
  $(".translation-header .target-locale").text(formValue['target_locale']);

  iterateFormItems(cb_global, function(item) {
    $(item.target_value.el).on("input change", function() {
      // Listen on "change" for older browser support
      markAsEdited(item);
    });
  });

  cb_global.onSaveComplete = function() {
    iterateFormItems(cb_global, function(item) {
      if (item.changed.getValue()) {
        $(item.changed.el).closest('fieldset')
            .removeClass().addClass(VERB_CURRENT_CLASS);
      }
      item.changed.setValue(false);
    });
    cb_global.lastSavedFormValue = cb_global.form.getValue();
  };
});