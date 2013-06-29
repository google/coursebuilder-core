/*
 * Holds JavaScript functionality specific to the unit/lesson editor.
 */

function ActivityImporter(Y, env, notify, errorMessageFormatter, confirm) {
  this.Y = Y;
  this.env = env;
  this.notify = notify;
  this.errorMessageFormatter = errorMessageFormatter;
  this.confirm = confirm
}
ActivityImporter.prototype.CONFIRM_MESSAGE =
    'This will convert your JavaScript activity\n' +
    'into Course Builder 1.5 questions.';
ActivityImporter.prototype.findLessonBodyRte = function() {
  var inputs = this.env.form.inputs;
  for (var i = 0; i < inputs.length; i++) {
    var input = inputs[i];
    if (input.options && input.options.name == 'objectives') {
      return input;
    }
  }
  throw 'Cannot find lesson body editor';
};
ActivityImporter.prototype.doImport = function() {
  var that = this;
  var key = this.Y.one('div.keyHolder').get('text');
  var activityText =
      this.Y.one('div.activityHolder > div > textarea').get('value');
  var request = {
    'key': key,
    'text': activityText,
    'xsrf_token': this.env.xsrf_token
  }
  this.Y.io('rest/course/lesson/activity', {
    method: 'put',
    data: {
      'request': JSON.stringify(request)
    },
    on: {
      complete: function(transactionId, response, args) {
        var json;
        if (response && response.responseText) {
          json = parseJson(response.responseText);
        } else {
          that.notify('The server did not respond. ' +
              'Please reload the page to try again.');
          return;
        }

        if (json.status != 200) {
          that.notify(that.errorMessageFormatter(json.status, json.message));
          return;
        }

        var payload = JSON.parse(json.payload);
        var importedActivity = payload.content;
        var rte = that.findLessonBodyRte();
        rte.setValue(rte.getValue() + '\n\n\n' + importedActivity);

        that.notify('Your activity has been imported into the lesson body.');
      }
    }
  });
};
/**
 * Place a button on the lesson editor page to perform an import.
 */
ActivityImporter.prototype.insertImportAssignmentButton = function() {
  var that = this;
  var button = this.Y.Node.create('<a href="javascript:void(0)">' +
      '<span>Import to lesson body...</span></a>');
  button.on('click', function(evt) {
    if (that.confirm(that.CONFIRM_MESSAGE)) {
      that.doImport();
    }
    evt.preventDefault();
  });
  this.Y.one('div.activityHolder').append(button);
}
