var typesInfo;
var dimTypes;

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
  if (dimType != 'unit_visit') {
    higherValue.text('Higher Score');
    lowerValue.text('Lower Score');
  } else {
    higherValue.text('Maximum number of visits to the page');
    lowerValue.text('Minimum number of visits to the page');
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
