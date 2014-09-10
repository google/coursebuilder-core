$(function() {
  // Hide the other invitation inputs when the "Enable Invitations checkbox"
  // is unchecked.

  var checkbox = $("div.invitation-enable > input[type=\"checkbox\"]");

  function updateInvitationFields() {
    if (checkbox.prop("checked")) {
      $(".invitation-data").parent().show();
    } else {
      $(".invitation-data").parent().hide();
    }
  }

  function init() {
    checkbox.click(updateInvitationFields);
    updateInvitationFields();
  }

  init();
});
