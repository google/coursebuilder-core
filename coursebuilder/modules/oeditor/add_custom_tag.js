var tag = document.getElementsByName('tag')[0];
if (tag) {
  tag.onchange = function(event) {
    var value = cb_global.form.getValue();
    value.attributes = {};
    window.parent.frameProxy.setValue(value);

    var tagName = tag.options[tag.selectedIndex].value;
    window.location = getAddCustomTagUrl(cb_global, tagName);
  };
}
document.getElementById('cb-oeditor-form').action = 'javascript: void(0)';
