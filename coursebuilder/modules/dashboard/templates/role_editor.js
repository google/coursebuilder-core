function showNoPermissionsMessage() {
  $("#formContainer > div > form > fieldset > .inputEx-Group > fieldset")
  .append("There are currently no permissions assigned nor registered.");
}

function setUpRoleEditorForm() {
  var all_hidden = true;
  $(".permission-module").each(function() {
    if($(this).find(".inputEx-ListField-childContainer > div").length == 0) {
      $(this).parent().hide();
    } else {
      all_hidden = false;
    }
  });

  if (all_hidden) {
    showNoPermissionsMessage();
  }
}

setUpRoleEditorForm();