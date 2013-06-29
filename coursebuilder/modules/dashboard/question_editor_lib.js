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

  this.button = divNode.create('<button></button>');
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

function normalizeScores(scores) {
  if (singleSelection) {
    return normalizeScoresForSingleSelectionModel(scores);
  } else {
    return normalizeScoresForMultipleSelectionModel(scores);
  }
}

function isInNormalForm(scores) {
  normScores = normalizeScores(scores);
  return Y.Array.reduce(scores, true, function(prevVal, score, idx) {
    return prevVal && score == normScores[idx];
  });
}

/*
 * The largest score is normalized to 1, and all the others are set to 0.
 */
function normalizeScoresForSingleSelectionModel(scores) {
  if (scores.length == 0) {
    return [];
  }
  var maxItem = Y.Array.reduce(scores, [0, scores[0]],
      function(prevVal, score, index) {
        if (score > prevVal[1]) {
          return [index, score];
        } else {
          return prevVal;
        }
      }
  );
  var retVal = Y.Array.map(scores, function(score) {
    return 0;
  });
  retVal[maxItem[0]] = 1;
  return retVal;
}

/*
 * All the scores which are over zero are given a common weight which sums to 1;
 * all others are set to 0.
 */
function normalizeScoresForMultipleSelectionModel(scores) {
  var posCount = Y.Array.reduce(scores, 0, function(prevVal, score) {
    return score > 0 ? prevVal + 1 : prevVal;
  });
  if (posCount == 0) {
    return Y.Array.map(scores, function(score) {
      return 0;
    });
  }
  var commonValue = Math.floor(100/posCount)/100;
  // There may be rounding error, so fudge the final value so the sum is 1
  var finalValue = Math.floor(100.5 - 100 * commonValue * (posCount - 1))/100;
  var retVal = Y.Array.map(scores, function(score) {
    return score > 0 ? commonValue : 0;
  });
  var lastPosIdx = retVal.length - 1;
  while (retVal[lastPosIdx] == 0) {
    --lastPosIdx;
  }
  retVal[lastPosIdx] = finalValue;
  return retVal;
}

function getScores() {
  var scores = [];
  Y.all('div.mc-choice-score input').each(function(input) {
    scores.push(input.get('value'));
  });
  return scores;
}

function updateScoreInputs() {
  if (setScores) {
    Y.all('div.mc-choice-score input').setAttribute('type', 'text');
    return;
  }

  //Update the type of input tags shown
  if (singleSelection) {
    Y.all('div.mc-choice-score input').setAttribute('type', 'radio');
  } else {
    Y.all('div.mc-choice-score input').setAttribute('type', 'checkbox');
  }

  // Update the values of the scores to be in normaluized form
  scores = normalizeScores(getScores());
  Y.all('div.mc-choice-score input').each(function(input, idx) {
    input.set('value', scores[idx]);
    input.set('checked', scores[idx] > 0);
  });
}

function updateToggleFeedbackButtons() {
  Y.all('div.mc-choice').each(function(choiceDiv) {
    if (!choiceDiv.hasToggleButton) {
      addToggleFeedbackButtonToChoiceDiv(choiceDiv);
      choiceDiv.hasToggleButton = true;
    }
  });
}

function addToggleFeedbackButtonToChoiceDiv(choiceDiv) {
  var feedbackDiv = choiceDiv.one('> fieldset > div + div + div');
  feedbackDiv.setStyle('display', 'none');

  var toggleFeedbackDiv = Y.Node.create('<div class="toggle-feedback"></div>');
  new ToggleButton(toggleFeedbackDiv, 'Show feedback', 'Hide feedback',
      function() {
        feedbackDiv.setStyle('display', 'block');
      },
      function() {
        feedbackDiv.setStyle('display', 'none');
      }
  );
  choiceDiv.appendChild(toggleFeedbackDiv);
}

function bindRadioButtonClickHandlers() {
  Y.all('div.mc-choice-score input').each(function(input) {
    if (!input.hasClickHandler) {
      input.on('click', function(ev) {
        if (setScores) {
          return;
        } else if (singleSelection) {
          ev.target.set('value', '1');
          // Unset all the other radio buttons
          Y.all('div.mc-choice-score input').each(function(input) {
            if (input != ev.target) {
              input.set('value', '0');
              input.set('checked', false);
            }
          });
        } else { // multiple selection
          ev.target.set('value', ev.target.get('value') > 0 ? '0' : '1');
        }
      });
      input.hasClickHandler = true;
    }
  });
}

function updateSetScoresToggleButtonLabel() {
  if (isInNormalForm(getScores())) {
    setScoresToggleButton.setLabels(SHOW_SCORES_LABEL, HIDE_SCORES_LABEL);
  } else {
    setScoresToggleButton.setLabels(SHOW_SCORES_LABEL,
        HIDE_SCORES_WARNING_LABEL);
  }
}

/**
 * The state of the UI is controlled by two parameters: singleSelection and
 * setScores. This initializes them using data already stored in the form.
 */
function initState() {
  singleSelection = (Y.all('div.mc-selection input:checked').get('value') ==
      'false');
  setScores = !isInNormalForm(getScores());
}

/**
 * Add a toggle button to the UI which toggles between letting the user set
 * scores directly and a choice-picker view.
 */
function initSetScoresToggleButton() {
  var setScoresDiv = Y.Node.create('<div class="set-scores-toggle"></div>');
  setScoresToggleButton = new ToggleButton(
      setScoresDiv,
      SHOW_SCORES_LABEL,
      HIDE_SCORES_LABEL,
      function() {
        setScores = true;
        updateScoreInputs();
      },
      function() {
        setScores = false;
        updateScoreInputs();
      }
  );
  setScoresToggleButton.setStateA(!setScores);
  Y.one('div.mc-selection').get('parentNode').appendChild(setScoresDiv);
}

function init() {
  initState();
  initSetScoresToggleButton();
  updateScoreInputs();
  updateToggleFeedbackButtons();
  bindRadioButtonClickHandlers();

  // Add click handler to the single/multiple selection widget
  Y.all('div.mc-selection input').on('click', function(e) {
    singleSelection = ('false' == e.target.get('value'));
    updateScoreInputs();
  });

  // Add change handler to the entire InputEx form
  cb_global.form.getFieldByName('choices').on('updated', function() {
    updateScoreInputs();
    updateToggleFeedbackButtons();
    bindRadioButtonClickHandlers();
    updateSetScoresToggleButtonLabel();
  });
}
