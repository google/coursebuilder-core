var XSSI_PREFIX = ")]}'";

function parseJson(s) {
  return JSON.parse(s.replace(XSSI_PREFIX, ""));
}

$(function(){
  $('div[data-delete-url]').each(function(index, element){
    var groupName = $(element).data('group-name');
    var button = $('<button id="delete-' + groupName + '" ' +
        'class="gcb-list__icon gcb-delete-student-group ' +
        'delete-button gcb-list__icon--rowhover material-icons">' +
        'delete</button>')
    var deleteUrl = $(element).data('delete-url');
    button.click(function(){
      if (confirm('You are about to delete this group.  Really proceed?')) {
        $.ajax({
          url: deleteUrl,
          method: 'DELETE',
          error: function(response) {
            // Here, we are re-using the OEditor style delete handler, so
            // we need to cope with a CB-encoded response style.
            if (response.status == 200) {
              var payload = parseJson(response.responseText);
              if (payload.status == 200 && payload.message == "Deleted.") {
                location.reload();
              } else {
                cbShowMsgAutoHide('Deletion failed: ' + payload.message);
              }
            } else {
              cbShowMsgAutoHide('Deletion failed: ' + response.responseText)
            }
          },
          success: function() {
            location.reload();
          }
        });
      }
    });
    $(element).append(button)
  });
});
