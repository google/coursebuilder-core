
/**
 * A class which represents a button which can toggle between two states ("a"
 * and "b") on a click.
 * @param {YUI Node} divNode the node which the button will be inserted in
 * @param {string} aText the text which will be shown when the button is in "a"
 *     state (the default)
 * @param {string} bText the text which will be shown when the button is in "b"
 *     state
 * @param {function} aCallback zero-arg function called when the button is
 *     clicked in "a" state
 * @param {function} bCallback zero-arg function called when the button is
 *     clicked in "b" state
 */
function ToggleButton(divNode, aText, bText, aCallback, bCallback) {
  var that = this;
  this.isStateA = true;
  this.aText = aText;
  this.bText = bText;
  this.aCallback = aCallback;
  this.bCallback = bCallback;

  this.button = divNode.create('<button class="gcb-button"></button>');
  this.button.set('text', aText);
  this.button.on('click', function(ev) {
    ev.preventDefault();
    if (that.isStateA) {
      that.button.set('text', that.bText);
      that.aCallback();
    } else {
      that.button.set('text', that.aText);
      that.bCallback();
    }
    that.isStateA = !that.isStateA;
  });
  divNode.appendChild(this.button);
}

ToggleButton.prototype = {
  setLabels: function (aText, bText) {
    this.aText = aText;
    this.bText = bText;
    this.button.set('text', this.isStateA ? this.aText : this.bText);
  },
  setStateA: function(state) {
    this.isStateA = state;
    this.button.set('text', this.isStateA ? this.aText : this.bText);
  }
};

function addToggleFeedbackButton(feedbackField) {
  var feedbackDiv = Y.one(feedbackField.divEl);
  if (feedbackDiv.next('.toggle-feedback')) {
    return;
  }

  var toggleFeedbackDiv = Y.Node.create('<div class="toggle-feedback"></div>');
  var button = new ToggleButton(toggleFeedbackDiv,
      'Add feedback',
      'Delete feedback',
      function() {
        feedbackDiv.setStyle('display', 'block');
      },
      function() {
        feedbackField.setValue('');
        feedbackDiv.setStyle('display', 'none');
      }
  );
  feedbackDiv.insert(toggleFeedbackDiv, 'after');

  if (feedbackField.getValue() == '') {
    feedbackDiv.setStyle('display', 'none');
    button.setStateA(true);
  } else {
    button.setStateA(false);
  }
}
