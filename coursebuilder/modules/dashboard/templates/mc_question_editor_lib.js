var SHOW_SCORES_LABEL = 'Assign scores to individual choices';
var HIDE_SCORES_LABEL = 'Use default scoring';
var HIDE_SCORES_WARNING_LABEL =
    'Use default scoring (Note: scores will change)';

/* Whether to show the numeric score or a radio/checkbox. */
var setScores = false;
var setScoresToggleButton;
/* Whether a single or multiple selection of choices is allowed. */
var singleSelection = true;

function normalizeScores(scores) {
  if (singleSelection) {
    return normalizeScoresForSingleSelectionModel(scores);
  } else {
    return normalizeScoresForMultipleSelectionModel(scores);
  }
}

function isInNormalForm(scores) {
  var normScores = normalizeScores(scores);
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
 * all others are set to -1. This is so that the only way to score 1.0 is to
 * select all correct choices and no incorrect choices. Selecting even one
 * incorrect choice will always result in a score of zero.
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
    return score > 0 ? commonValue : -1;
  });
  var lastPosIdx = retVal.length - 1;
  while (retVal[lastPosIdx] == -1) {
    --lastPosIdx;
  }
  retVal[lastPosIdx] = finalValue;
  return retVal;
}

function getScores() {
  var scores = [];
  Y.all('div.mc-choice-score input[type=text]').each(function(input) {
    scores.push(input.get('value'));
  });
  return scores;
}

function updateScoreInputs() {
  hideAllScoreInputs();
  if (setScores) {
    Y.all('div.mc-choice-score input[type=text]').removeClass('hidden');
    return;
  }

  if (singleSelection) {
    Y.all('div.mc-choice-score input[type=radio]').removeClass('hidden');
  } else {
    Y.all('div.mc-choice-score input[type=checkbox]').removeClass('hidden');
  }

  // Update the values of the scores to be in normalized form
  var scores = normalizeScores(getScores());

  Y.all('div.mc-choice-score input[type=text]').each(function(input, idx) {
    input.set('value', scores[idx]);
  });
  Y.all('div.mc-choice-score input[type=radio]').each(function(input, idx) {
    input.set('checked', scores[idx] > 0);
  });
  Y.all('div.mc-choice-score input[type=checkbox]').each(function(input, idx) {
    input.set('checked', scores[idx] > 0);
  });
}

function mcUpdateToggleFeedbackButtons(mcQuestionEditorForm) {
  addToggleFeedbackButton(
      mcQuestionEditorForm.getFieldByName('defaultFeedback'));

  var choiceFields = mcQuestionEditorForm.getFieldByName('choices').subFields;
  for (var i = 0; i < choiceFields.length; i++) {
    var choiceField = choiceFields[i];
    addToggleFeedbackButton(choiceFields[i].getFieldByName('feedback'));
  }
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
function initState(mcQuestionEditorForm) {
  singleSelection = ! mcQuestionEditorForm
      .getFieldByName('multiple_selections').getValue();
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

function hideAllScoreInputs() {
  Y.all('div.mc-choice-score input').addClass('hidden')
}

function initAlternateScoreInputs() {
  // The value for the score is held in a <input type="text"> element.
  // However because IE does not allow dynamically changing the type of
  // an input element, we associate a checkbox and a radio button with each
  // text input, and we show the appropriate one depending on which selection
  // mode applies. Click handlers on the radio button and checkbox keep the
  // base text input's value in sync.
  Y.all('div.mc-choice-score input[type=text]').each(function(input) {
    if (input.getDOMNode().hasBeenAugmented) {
      return;
    }

    var radio = Y.Node.create('<input type="radio">');
    var checkbox = Y.Node.create('<input type="checkbox">');
    var parent = input.get('parentNode');
    parent.appendChild(radio);
    parent.appendChild(checkbox);

    radio.on('click', function() {
      Y.all('div.mc-choice-score input[type=text]').set('value', '0');
      input.set('value', '1');
      updateScoreInputs();
    });

    checkbox.on('click', function() {
      input.set('value', checkbox.get('checked') ? '1' : '0');
      updateScoreInputs();
    });

    input.getDOMNode().hasBeenAugmented = true;

    hideAllScoreInputs();
  });
}

function initMcQuestionEditor(mcQuestionEditorForm) {
  initState(mcQuestionEditorForm);
  initSetScoresToggleButton();
  initAlternateScoreInputs();
  updateScoreInputs();
  mcUpdateToggleFeedbackButtons(mcQuestionEditorForm);

  // Add click handler to the single/multiple selection widget
  Y.all('div.mc-selection input').on('click', function(e) {
    singleSelection = ! mcQuestionEditorForm
        .getFieldByName('multiple_selections').getValue();
    updateScoreInputs();
  });

  // Add change handler to the entire InputEx form
  mcQuestionEditorForm.getFieldByName('choices').on('updated', function() {
    initAlternateScoreInputs();
    updateScoreInputs();
    mcUpdateToggleFeedbackButtons(mcQuestionEditorForm);
    updateSetScoresToggleButtonLabel();
  });
  updateSetScoresToggleButtonLabel();
}
