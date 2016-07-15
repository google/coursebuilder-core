(function() {
  /*  Depends on these global variables: JOB_STATUS_URL
   *
   *  If file picking is enabled, it depends on these global variables:
   *    DRIVE_ITEM_URL, ADD_REST_URL, ADD_REST_XSRF_TOKEN
   *    GOOGLE_CLIENT_ID, GOOGLE_API_KEY
   */

  // File Picking

  // I'm forcing the login screen to appear so you get a chance to choose your
  // google account before you choose a document.  Otherwise it would always
  // use the current user's account.  If this is annoying, change it.
  var SKIP_LOGIN = false;

  var DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive';

  var apisLoaded = $.Deferred();

  // TODO(nretallack): make this a library function
  function wrapIfExists(name, fun) {
    var old = window[name];
    if (old) {
      window[name] = function() {
        old.apply(window, arguments);
        fun.apply(window, arguments);
      }
    } else {
      window[name] = fun;
    }
  }

  function onGoogleApiLoaded() {
    var authLoaded = $.Deferred();
    var pickerLoaded = $.Deferred();
    gapi.load('auth2', {'callback': function() {
      gapi.auth2.init({
        client_id: GOOGLE_CLIENT_ID,
        scope: DRIVE_SCOPE,

        // TODO(nretallack): set to false when b/29221567 is resolved
        fetch_basic_profile: true,
      }).then(function() {
        authLoaded.resolve()
      });
    }});
    gapi.load('picker', {'callback': function() {
      pickerLoaded.resolve();
    }});

    $.when(authLoaded, pickerLoaded).then(function() {
      apisLoaded.resolve();
    })
  }

  // This function's name must match the onload parameter given to the Google
  // API script.  There can be only one, so if there is another we will wrap it.
  wrapIfExists('onGoogleApiLoaded', onGoogleApiLoaded);

  function startPicker() {
    apisLoaded.then(startAuth);
  }

  function startAuth() {
    if (SKIP_LOGIN && gapi.auth2.getAuthInstance().isSignedIn.get()) {
      createPicker();
    } else {
      gapi.auth2.getAuthInstance().signIn().then(createPicker);
    }
  }

  function createPicker() {
    new google.picker.PickerBuilder()
      .addView(google.picker.ViewId.SPREADSHEETS)
      .addView(google.picker.ViewId.DOCUMENTS)
      .setOAuthToken(
          gapi.auth2.getAuthInstance().currentUser.get().getAuthResponse()
          .access_token)
      .setDeveloperKey(GOOGLE_API_KEY)
      .setCallback(pickerCallback)
      .build()
      .setVisible(true);
  }

  function pickerCallback(data) {
    if (data[google.picker.Response.ACTION] != google.picker.Action.PICKED) {
      return;
    }

    var file_id = data[google.picker.Response.DOCUMENTS][0][
        google.picker.Document.ID];
    gapi.auth2.getAuthInstance().currentUser.get().grantOfflineAccess(
        {'redirect_uri': 'postmessage'}).then(
      function(authResult){
        var code = authResult['code'];
        if (!code) {
          cbShowMsg('Failed to authenticate.');
          return;
        }
        shareDriveItem(file_id, code);
      }
    );
  }

  // Public for testing purposes
  window.shareDriveItem = function(file_id, code) {
    cbShowMsg('Sharing the file with your service account...');
    $.ajax({
      method: 'POST',
      url: ADD_REST_URL,
      data: {
        code: code,
        file_id: file_id
      },
      headers: {
        'CSRF-Token': ADD_REST_XSRF_TOKEN,
      },
      dataType: 'text',
      success: function(text) {
        var payload = JSON.parse(gcb.parseJsonResponse(text).payload);
        if (payload.status == 'success') {
          window.location = DRIVE_ITEM_URL + '?key=' + file_id;
        } else {
          cbShowMsg(payload.message);
        }
      },
      error: function() {
        cbShowMsg('Unknown server error.');
      }
    });
  }

  $(function() {
    $('#picker-button').on('click', startPicker);
  });

  // Date formatting

  function formatDate(timestamp) {
    return (new Date(parseFloat(timestamp)*1000)).toLocaleString();
  }

  $(function() {
    $('.local-datetime').each(function() {
      var element = $(this);
      var timestamp = element.data('timestamp');
      if (timestamp) {
        element.text(formatDate(timestamp));
      }
    })
  });

  // Job Status Check

  var POLL_INTERVAL_MILLISECONDS = 5000;
  function update_job_status() {
    $.ajax({
      method: 'get',
      url: JOB_STATUS_URL,
      dataType: 'text',
      success: function(text) {
        var running = JSON.parse(gcb.parseJsonResponse(text).payload).running;
        $('.running-state').toggle(running);
        $('.idle-state').toggle(!running);
        setTimeout(update_job_status, POLL_INTERVAL_MILLISECONDS);
      },
    })
  }

  $(function() {
    update_job_status();
  });
})();
