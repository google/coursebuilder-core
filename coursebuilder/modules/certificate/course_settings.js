var isPeerAssessmentTable;

$(onReady);

function onReady() {
  if (cb_global.schema.properties.certificates) {
    // Only activate this functionality on the Settings > Course view
    init();
  }
}

function updateCriterionDivs(){
  $(".settings-list-item .assessment-dropdown select").each(function() {
    onAssignmentDropdownChanged($(this));
  });
}

function init() {
  isPeerAssessmentTable = cb_global.schema.properties.certificates.properties
      .certificate_criteria._inputex.is_peer_assessment_table;

  // Pre-run event handlers on existing and newly created records
  updateCriterionDivs();
  cb_global.form.inputsNames.certificates.inputsNames.certificate_criteria
    .on("updated", function(){
      updateCriterionDivs();
    });

  // Event handlers
  $(".settings-list").on("change", ".assessment-dropdown select", function(e) {
    onAssignmentDropdownChanged($(this));
  });

  cb_global.onSaveClick = onCourseSettingsSave;
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
    customCriteria.hide();
    passPercent.hide();
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
 * Validate the certificate criteria before submission.
 */
function onCourseSettingsSave() {
  var formValues = cb_global.form.getValue().certificates.certificate_criteria;
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
