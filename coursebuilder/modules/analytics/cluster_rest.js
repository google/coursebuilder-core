var typesInfo;
var dimTypes;
var progressDimRadioLabels = ['Not started', 'In progress', 'Completed'];


function createRadioElements(parent, labels, call_back) {
  var previousContainer = parent.find('#progress-buttons-container');
  if (previousContainer.length) {
    previousContainer.show();
  } else {
    var container = document.createElement('div');
    container.id = 'progress-buttons-container';
    for (var i = 0; i < labels.length; i++) {
      var radio = document.createElement('input');
      radio.type = 'radio';
      radio.value = i;
      radio.id = 'progress-button-' + i;
      radio.onclick = function() {call_back(this.value)};
      container.appendChild(radio);
      container.appendChild(document.createTextNode(labels[i]));
    };
    parent.append(container);
  }
}

/**
 * Changes the input elements on the screen to show the discrete options for a
 * progress dimension instead of a numerical range.
 */
function setProgressDimensionRange(fieldset) {
  // Only for units and lessons:
  //   0 == none of its sub-entities has been completed
  //   1 == some, but not all, of its sub-entities have been completed
  //   2 if all its sub-entities have been completed.
  function updateRange(value) {
    highDiv.find('input').val(value);
    lowDiv.find('input').val(value);
    // Toogle all other buttons (but just the buttons on this fielset.
    fieldset.find('input[type=radio]').prop('checked', false);
    fieldset.find('#progress-button-' + value).prop('checked', true);
  }
  var highDiv = fieldset.find('.dim-range-high').parent();
  var lowDiv = fieldset.find('.dim-range-low').parent();
  highDiv.hide();
  lowDiv.hide();
  createRadioElements(fieldset, progressDimRadioLabels, updateRange);
  highValue = parseInt(highDiv.find('input').val());
  if (highValue == parseInt(lowDiv.find('input').val()) &&
      highValue < progressDimRadioLabels.length) {
    fieldset.find('#progress-button-' + highValue).click();
  }
}


/**
 * Changes the input elements on the screen to show the option for a
 * non progress dimension.
 */
function setNonProgressDimensionRage(fieldset) {
  var highDiv = fieldset.find('.dim-range-high').parent();
  var lowDiv = fieldset.find('.dim-range-low').parent();
  highDiv.show();
  lowDiv.show();
  fieldset.find('#progress-buttons-container').hide();
}


/**
 * Changes the description of the range in a dimension depending if
 * it is a visit dimension or a score dimension.
 * The function is triggered every time a dimension is selected.
 */
function onDimensionChanged(selectElement) {
  var selectedVal = selectElement.val();
  var dimType = typesInfo[dimTypes[selectedVal]];
  var fieldset = selectElement.closest("fieldset");
  var higherValue = fieldset.find(".dim-range-high").parent().find('label');
  var lowerValue = fieldset.find(".dim-range-low").parent().find('label');
  a = fieldset
  if (dimType == 'unit_progress' || dimType == 'lesson_progress') {
    setProgressDimensionRange(fieldset);
    return;
  }
  setNonProgressDimensionRage(fieldset);
  if (dimType == 'unit_visit') {
    higherValue.text('Maximum number of visits to the page');
    lowerValue.text('Minimum number of visits to the page');
  } else {
    higherValue.text('Higher Score');
    lowerValue.text('Lower Score');
  }
}

function init() {
  typesInfo = cb_global.schema.properties.vector._inputex.types_info;
  dimTypes = cb_global.schema.properties.vector._inputex.dim_types;
  var dimensionDivs = $(".dim-name");
  //Initial setup
  dimensionDivs.find("select").each(
    function(index, element) {
      onDimensionChanged($(element));
    }
  );

  //Attach handlers
  $(".cluster-dim-container").on("change", ".dim-name select", function(e) {
    onDimensionChanged($(this));
  });
}

init();
