var SHOW_SCORES_LABEL = 'Assign scores to individual choices';
var HIDE_SCORES_LABEL = 'Return to choice picker view';
var HIDE_SCORES_WARNING_LABEL =
    'Return to choice-picker (Note: scores will change)';


/* Whether to show the numeric score or a radio/checkbox. */
var setScores = false;
var setScoresToggleButton;
/* Whether a single or multiple selection of choices is allowed. */
var singleSelection = true;


init();
