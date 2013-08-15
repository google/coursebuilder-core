{
  "multiple_choice_activity": [{
    "questionType": "multiple choice",
    "choices": [
      ["A", true, "Correct."],
      ["B", false, "Incorrect"],
      ["C", false, "Incorrect"],
      ["D", false, "Incorrect"]
    ]
  }],

  "multiple_choice_group_activity": [{
    "questionType": "multiple choice group",
    "questionsList": [
      {
        "choices": ["A", "B", "C"],
        "correctIndex": 0
      },
      {
        "choices": ["Yes", "No"],
        "correctIndex": 1
      }
    ]
  }],

  "free_text_activity": [{
    "questionType": "freetext",
    "correctAnswerRegex": /42/i,
    "correctAnswerOutput": "Correct!",
    "incorrectAnswerOutput": "Wrong!",
    "showAnswerOutput": "The correct answer is 42 (of course)."
  }],

  "mixed_assessment": {
    "preamble": "This is an assessment.",
    "checkAnswers": true,
    "questionsList": [
      {
        "questionHTML": "Multiple choice question.",
        "choices": [correct("A"), "B", "C", "D"],
        "lesson": "1.1"
      },
      {
        "questionHTML": "String question.",
        "correctAnswerString": "Rectus",
        "lesson": "1.1"
      },
      {
        "questionHTML": "Regex question.",
        "correctAnswerRegex": /match/i,
        "lesson": "1.1"
      },
      {
        "questionHTML": "Numeric question.",
        "correctAnswerNumeric": 42,
        "lesson": "1.1"
      }
    ]
  },
}
