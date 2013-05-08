var tag = document.getElementsByName('tag')[0];
if (tag) {
  tag.onchange = function(event) {
    var value = cb_global.form.getValue();
    value.attributes = {};
    window.parent.frameProxy.setValue(value);

    var tag_name = tag.options[tag.selectedIndex].value;
    window.location.search = '?action=add_custom_tag&tag_name=' + escape(tag_name);
  };
}