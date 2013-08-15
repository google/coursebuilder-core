var tag = document.getElementsByName('tag')[0];
if (tag) {
  tag.onchange = function(event) {
    var value = cb_global.form.getValue();
    value.attributes = {};
    window.parent.frameProxy.setValue(value);

    var tagName = tag.options[tag.selectedIndex].value;
    window.location = getAddCustomTagUrl(cb_global, tagName);
  };

  // Remove excluded tags from the list
  var excludedCustomTags =
      window.parent.frameProxy.getContext().excludedCustomTags;
  var selectField = cb_global.form.inputs[0].inputs[0];
  for (var i = 0; i < excludedCustomTags.length; i++) {
    try {
      selectField.removeChoice({value: excludedCustomTags[i]});
    } catch (err) {
      if (window.console) {
        window.console.log('Failed to remove ' + excludedCustomTags[i] +
            ' from tag selector');
      }
    }
  }

  // When adding elements of a list, be sure to refresh the page height.
  Y.all('.inputEx-List-link').on('click', function() {
    window.parent.frameProxy.refresh();
    var links = Y.all('.inputEx-List-link');
    if (links.size() >= 2) {
      links.item(links.size() - 2).on('click', function() {
        window.parent.frameProxy.refresh();
      });
    }
  });
}
document.getElementById('cb-oeditor-form').action = 'javascript: void(0)';
