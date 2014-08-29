var isPeerAssessmentTable;

$(function() {
  if (cb_global.schema.properties.course) {
    // Only activate this functionality on the Settings > Course view
    init();
  }
});


function init() {
  var criterionDivs = $(".settings-list-item");

  //Initial setup
  criterionDivs.find(".assessment-dropdown select").each(
    function(index, element) {
      onAssignmentDropdownChanged($(element));
    }
  );
  criterionDivs.find(".custom-criteria select").each(function(index, element) {
    onCustomCriteriaDropdownChanged($(element));
  });

  //Attach handlers
  $(".settings-list").on("change", ".assessment-dropdown select", function(e) {
    onAssignmentDropdownChanged($(this));
  });

  $(".settings-list").on("change", ".custom-criteria select", function(e) {
    onCustomCriteriaDropdownChanged($(this));
  });
  cb_global.onSaveClick = onCourseSettingsSave;

  isPeerAssessmentTable = cb_global.schema.properties.course.properties
      .certificate_criteria._inputex.is_peer_assessment_table;
}

/**
 * Update the form for a individual criterion when the assessment chooser
 * select changes. If a machine-graded assessment is chosen, show a passing
 * score entry. If a peer-graded assessment is shown, hide the passing score
 * entry but show policy text. If the custom criterion option is selected,
 * show the chooser for custom criteria.
 */
function onAssignmentDropdownChanged(selectElement) {
  var fieldset = selectElement.closest("fieldset");
  var customCriteria = fieldset.find(".custom-criteria").parent();
  var passPercent = fieldset.find(".pass-percent").parent();
  if (selectElement.val() == "default") {
    customCriteria.show();
    passPercent.show();
    selectElement.next("div.inputEx-description").hide();
  } else if (selectElement.val() == "") {
    customCriteria.show();
    passPercent.find("input").val("");
    passPercent.hide();
    selectElement.next("div.inputEx-description").hide();
  } else {
    customCriteria.find("select").val("");
    customCriteria.hide();
    //Check if peer graded
    var assessmentId = selectElement.find("option:selected").attr("value");
    if (isPeerAssessmentTable[assessmentId]) {
      passPercent.find("input").val("");
      passPercent.hide();
      selectElement.next("div.inputEx-description").show();
    } else {
      passPercent.show();
      selectElement.next("div.inputEx-description").hide();
    }
  }
}

/**
 * Handle selection of a custom criterion method.
 */
function onCustomCriteriaDropdownChanged(selectElement) {
  var fieldset = selectElement.closest("fieldset")
  var assessmentDropdown = fieldset.find(".assessment-dropdown select");
  if (selectElement.val() == "") {
    onAssignmentDropdownChanged(assessmentDropdown.find("select"))
  } else {
    var passPercent = fieldset.find(".pass-percent");
    passPercent.find("input").val("");
    passPercent.parent().hide();
    assessmentDropdown.val("");
  }
}

/**
 * Validate the certificate criteria before submission.
 */
function onCourseSettingsSave() {
  var formValues = cb_global.form.getValue()["course"]["certificate_criteria"];
  for (var i = 0; i < formValues.length; ++i) {
    var assessmentId = formValues[i]["assessment_id"];
    if (assessmentId === "default") {
      cbShowMsg("The criterion requirement field is required.");
      return false;
    } else if (assessmentId === "") {
      // Custom criterion selected
      if (formValues[i]["custom_criteria"] === "") {
        cbShowMsg("The custom criterion field is required.");
        return false;
      }
    } else {
      var percent = formValues[i]["pass_percent"]
      if (isPeerAssessmentTable[assessmentId]) {
        // Peer graded assessment
        if (percent !== "") {
          cbShowMsg("A peer graded assessment can't have a passing " +
          "percentage defined.");
          return false;
        }
      } else {
        // Human graded assessment
        if (percent === "") {
          cbShowMsg("The passing percentage field is required for " +
          "human graded assessments.");
          return false;
        }
        if (! $.isNumeric(percent) || percent < 0 || percent > 100) {
          cbShowMsg("The pass percentage for a criterion " +
            "should be a value between 0 and 100.");
          return false;
        }
      }
    }
  }
  return true;
}