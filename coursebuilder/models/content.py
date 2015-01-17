# Copyright 2013 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Common classes and methods for processing text content."""

__author__ = 'Pavel Simakov (psimakov@google.com)'


from pyparsing import alphas
from pyparsing import Combine
from pyparsing import Each
from pyparsing import Group
from pyparsing import Literal
from pyparsing import nums
from pyparsing import Optional
from pyparsing import QuotedString
from pyparsing import Regex
from pyparsing import Suppress
from pyparsing import Word
from pyparsing import ZeroOrMore

from tools import verify


def sep(text):
    """Makes a separator."""
    return Suppress(Literal(text))


def key(name):
    """Makes grammar expression for a key."""
    return (
        Literal(name) ^
        (sep('\'') + Literal(name) + sep('\'')) ^
        (sep('"') + Literal(name) + sep('"')))


def list_of(term):
    """Makes a delimited list of terms."""
    return (
        Optional(
            term +
            ZeroOrMore(Suppress(Literal(',')) + term) +
            Optional(Suppress(Literal(',')))
        )
    )


def chunks(l, n):
    """Partitions the list l into disjoint sub-lists of length n."""
    if len(l) % n != 0:
        raise Exception('List length is not a multiple on %s', n)
    return [l[i:i+n] for i in range(0, len(l), n)]


def make_dict(unused_s, unused_l, toks):
    """Makes a dict from the list using even items as keys, odd as values."""
    result = {}
    key_value_pairs = chunks(toks, 2)
    for key_value_pair in key_value_pairs:
        result[key_value_pair[0]] = key_value_pair[1]
    return result


def make_list(unused_s, unused_l, toks):
    """Makes a list out of a token tuple holding a list."""
    result = []
    for item in toks:
        result.append(item.asList())
    return result


def make_bool(value):
    """Makes a boolean value lambda."""
    def make_value():
        return verify.Term(verify.BOOLEAN, value)
    return make_value


def make_int(value):
    """Makes an int value lambda."""
    return int(value[0])


def make_float(value):
    """Makes an float value lambda."""
    return float(value[0])


class AssessmentParser13(object):
    """Grammar and parser for the assessment."""

    string = (
        QuotedString('\'', escChar='\\', multiline=True) ^
        QuotedString('"', escChar='\\', multiline=True))

    boolean = (
        Literal('true').setParseAction(make_bool(True)) ^
        Literal('false').setParseAction(make_bool(False)))

    float = Combine(
        Word(nums) + Optional(Literal('.') + Word(nums))
    ).setParseAction(make_float)

    integer = Word(nums).setParseAction(make_int)

    choice_decl = (
        string ^
        Combine(
            sep('correct(') + string + sep(')')
        ).setParseAction(lambda x: verify.Term(verify.CORRECT, x[0]))
    )

    regex = (
        Regex('/(.*)/i') ^
        Combine(
            sep('regex(') +
            QuotedString('"', escChar='\\') +
            sep(')')
        ).setParseAction(lambda x: verify.Term(verify.REGEX, x[0]))
    )

    question_decl = (
        sep('{') +
        Each(
            Optional(
                key('questionHTML') + sep(':') +
                string + Optional(sep(','))) +
            Optional(
                key('lesson') + sep(':') +
                string + Optional(sep(','))) +
            Optional(
                key('correctAnswerString') + sep(':') +
                string + Optional(sep(','))) +
            Optional(
                key('correctAnswerRegex') + sep(':') +
                regex + Optional(sep(','))) +
            Optional(
                key('correctAnswerNumeric') + sep(':') +
                float + Optional(sep(','))) +
            Optional(
                key('choiceScores') + sep(':') +
                sep('[') +
                Group(list_of(float)).setParseAction(make_list) +
                sep(']') +
                Optional(sep(','))) +
            Optional(
                key('weight') + sep(':') + integer + Optional(sep(','))) +
            Optional(
                key('multiLine') + sep(':') +
                boolean + Optional(sep(','))) +
            Optional(
                key('choices') + sep(':') +
                sep('[') +
                Group(list_of(choice_decl)).setParseAction(make_list) +
                sep(']') +
                Optional(sep(',')))
        ) +
        sep('}')).setParseAction(make_dict)

    assessment_grammar = (
        sep('assessment') +
        sep('=') +
        sep('{') +
        Each(
            Optional(
                key('assessmentName') + sep(':') +
                string + Optional(sep(','))) +
            Optional(
                key('preamble') + sep(':') +
                string + Optional(sep(','))) +
            Optional(
                key('checkAnswers') + sep(':') +
                boolean + Optional(sep(','))) +
            Optional(
                key('questionsList') + sep(':') +
                sep('[') +
                Group(list_of(question_decl)).setParseAction(make_list) +
                sep(']') +
                Optional(sep(',')))
        ) +
        sep('}') +
        Optional(sep(';'))).setParseAction(make_dict)

    @classmethod
    def parse_string(cls, content):
        return cls.assessment_grammar.parseString(content)

    @classmethod
    def parse_string_in_scope(cls, content, scope, root_name):
        """Parses assessment text following grammar."""
        if 'assessment' != root_name:
            raise Exception('Unsupported schema: %s', root_name)

        # we need to extract the results as a dictionary; so we remove the
        # outer array holding it
        ast = cls.parse_string(content).asList()
        if len(ast) == 1:
            ast = ast[0]

        return dict(
            scope.items() +
            {'__builtins__': {}}.items() +
            {root_name: ast}.items())


class ActivityParser13(object):
    """Grammar and parser for the activity."""

    variable = Word(alphas)
    integer = Word(nums).setParseAction(make_int)
    string = (
        QuotedString('\'', escChar='\\', multiline=True) ^
        QuotedString('"', escChar='\\', multiline=True))
    boolean = (
        Literal('true').setParseAction(make_bool(True)) ^
        Literal('false').setParseAction(make_bool(False)))

    regex = (
        Regex('/(.*)/i') ^
        Combine(
            sep('regex(') +
            QuotedString('"', escChar='\\') +
            sep(')')
        ).setParseAction(lambda x: verify.Term(verify.REGEX, x[0]))
    )

    choice_decl = Group(
        sep('[') +
        string + sep(',') +
        boolean + sep(',') +
        string +
        sep(']')
    )

    choices_decl = Group(
        sep('[') +
        Optional(list_of(choice_decl)) +
        sep(']')
    ).setParseAction(make_list)

    multiple_choice_decl = (
        key('questionType') + sep(':') + key('multiple choice') +
        Optional(sep(','))
    )

    multiple_choice = (
        sep('{') +
        multiple_choice_decl +
        Each(
            Optional(
                key('questionHTML') + sep(':') +
                string + Optional(sep(','))) +
            Optional(
                key('choices') + sep(':') +
                choices_decl + Optional(sep(',')))
        ) +
        sep('}')
    ).setParseAction(make_dict)

    free_text_decl = (
        key('questionType') + sep(':') + key('freetext') +
        Optional(sep(','))
    )

    free_text = (
        sep('{') +
        free_text_decl +
        Each(
            Optional(
                key('questionHTML') + sep(':') +
                string + Optional(sep(','))) +
            Optional(
                key('correctAnswerRegex') + sep(':') +
                regex + Optional(sep(','))) +
            Optional(
                key('correctAnswerOutput') + sep(':') +
                string + Optional(sep(','))) +
            Optional(
                key('incorrectAnswerOutput') + sep(':') +
                string + Optional(sep(','))) +
            Optional(
                key('showAnswerPrompt') + sep(':') +
                string + Optional(sep(','))) +
            Optional(
                key('showAnswerOutput') + sep(':') +
                string + Optional(sep(','))) +
            Optional(
                key('outputHeight') + sep(':') +
                string + Optional(sep(',')))
        ) +
        sep('}')
    ).setParseAction(make_dict)

    question_list_decl = (
        sep('{') +
        Each(
            Optional(
                key('questionHTML') + sep(':') +
                string + Optional(sep(','))) +
            Optional(
                key('choices') + sep(':') +
                sep('[') +
                Group(list_of(string)).setParseAction(make_list) +
                sep(']') +
                Optional(sep(','))) +
            Optional(
                key('correctIndex') + sep(':') +
                (integer ^ (
                    sep('[') +
                    Group(list_of(integer)).setParseAction(make_list) +
                    sep(']'))) +
                Optional(sep(','))) +
            Optional(
                key('multiSelect') + sep(':') +
                boolean + Optional(sep(','))),
        ) +
        sep('}')).setParseAction(make_dict)

    questions_list_decl = Group(
        sep('[') +
        Optional(list_of(question_list_decl)) +
        sep(']')
    ).setParseAction(make_list)

    multiple_choice_group_decl = (
        key('questionType') + sep(':') + key('multiple choice group') +
        Optional(sep(','))
    )

    multiple_choice_group = (
        sep('{') +
        multiple_choice_group_decl +
        Each(
            Optional(
                key('questionGroupHTML') + sep(':') +
                string + Optional(sep(','))) +
            Optional(
                key('allCorrectMinCount') + sep(':') +
                integer + Optional(sep(','))) +
            Optional(
                key('allCorrectOutput') + sep(':') +
                string + Optional(sep(','))) +
            Optional(
                key('someIncorrectOutput') + sep(':') +
                string + Optional(sep(','))) +
            Optional(
                key('questionsList') + sep(':') +
                questions_list_decl + Optional(sep(',')))
        ) +
        sep('}')
    ).setParseAction(make_dict)

    activity_grammar = (
        sep('activity') +
        sep('=') +
        sep('[') +
        Optional(list_of(
            string ^ multiple_choice ^ free_text ^ multiple_choice_group)) +
        sep(']') +
        Optional(sep(';')))

    @classmethod
    def parse_string(cls, content):
        return cls.activity_grammar.parseString(content)

    @classmethod
    def parse_string_in_scope(cls, content, scope, root_name):
        """Parses activity text following grammar."""
        if 'activity' != root_name:
            raise Exception('Unsupported schema: %s', root_name)
        return dict(
            scope.items() +
            {'__builtins__': {}}.items() +
            {root_name: cls.parse_string(content).asList()}.items())


# here we register all the parser
SUPPORTED_PARSERS = {
    'activity': ActivityParser13, 'assessment': AssessmentParser13}


def verify_activity(activity_text):
    """Parses and semantically verifies activity."""
    activity = ActivityParser13.parse_string_in_scope(
        activity_text, verify.Activity().scope, 'activity')
    assert activity
    verifier = verify.Verifier()
    verifier.verify_activity_instance(activity, 'test')


def verify_assessment(assessment_text):
    """Parses and semantically verifies assessment."""
    assessment = AssessmentParser13.parse_string_in_scope(
        assessment_text, verify.Assessment().scope, 'assessment')
    assert assessment
    verifier = verify.Verifier()
    verifier.verify_assessment_instance(assessment, 'test')


def parse_string_in_scope(content, scope, root_name):
    parser = SUPPORTED_PARSERS.get(root_name)
    if not parser:
        raise Exception('Unsupported schema: %s', root_name)
    return parser.parse_string_in_scope(content, scope, root_name)


def test_activity_multiple_choice_group():
    """Test activity parsing."""
    activity_text = (
        """activity = [
  '<p>This is text.</p>',
  {
      questionType: 'multiple choice group',
      questionGroupHTML: '<p>This is text.</p>',
      allCorrectMinCount: 55,
      allCorrectOutput: '<p>This is text.</p>',
      someIncorrectOutput: '<p>This is text.</p>',
      questionsList: [
          {questionHTML: '<p>This is text.</p>'},
          {correctIndex: [1, 2, 3]},
          {questionHTML: '<p>This is text.</p>',
              correctIndex: 0, multiSelect: false,
              choices: ['foo', 'bar'],},
      ]
  },

  {
      "questionType": 'multiple choice group',
      questionGroupHTML:
          '<p>This section will test you on colors and numbers.</p>',
      questionsList: [
          {questionHTML: 'Pick all <i>odd</i> numbers:',
              choices: ['1', '2', '3', '4', '5'], correctIndex: [0, 2, 4]},
          {questionHTML: 'Pick one <i>even</i> number:',
               choices: ['1', '2', '3', '4', '5'], correctIndex: [1, 3],
               multiSelect: false},
          {questionHTML: 'What color is the sky?',
               choices: ['#00FF00', '#00FF00', '#0000FF'], correctIndex: 2}
      ],
      allCorrectMinCount: 2,
      allCorrectOutput: 'Great job! You know the material well.',
      someIncorrectOutput: 'You must answer at least two questions correctly.'
  }
];
""")
    verify_activity(activity_text)


def test_activity_multiple_choice():
    """Test activity parsing."""
    activity_text = (
        """activity = [
  '<p>This is text.</p>',
  {
      questionType: 'multiple choice',
      questionHTML: '<p>This is text.</p>',
      choices: [
          ['<p>This is text.</p>', false, '<p>This is text.</p>'],
          ['<p>This is text.</p>', true, '<p>This is text.</p>'],
      ]
  }
  ];
""")
    verify_activity(activity_text)


def test_activity_free_text():
    """Test activity parsing."""
    activity_text = (
        """activity = [
  '<p>This is text.</p>',
  {
      'questionType': 'freetext',
      questionHTML: '<p>This is text.</p>',
      showAnswerPrompt: '<p>This is text.</p>',
      showAnswerOutput: '<p>This is text.</p>',
      correctAnswerRegex: regex("/4|four/i"),
      correctAnswerOutput: '<p>This is text.</p>',
      incorrectAnswerOutput: '<p>This is text.</p>',
  },
  {
      questionType: 'freetext',
      questionHTML: '<p>What color is the snow?</p>',
      correctAnswerRegex: regex("/white/i"),
      correctAnswerOutput: 'Correct!',
      incorrectAnswerOutput: 'Try again.',
      showAnswerOutput: 'Our search expert says: white!' },
  ];
""")
    verify_activity(activity_text)


def test_assessment():
    """Test assessment parsing."""
    # pylint: disable=anomalous-backslash-in-string
    assessment_text = (
        """assessment = {
  assessmentName: '12345',
  preamble: '<p>This is text.</p>',
  checkAnswers: false,
  questionsList: [

    {questionHTML: '<p>This is text.</p>',
     choices:
       ["A and B", "D and B", correct("A and C"), "C and D", "I don't know"]
    },

   {questionHTML: '<p>This is text.</p>',
     choiceScores: [0, 0.5, 1.0],
     weight: 3,
     choices: [correct("True"), "False", "I don't know"]
    },

    {questionHTML: '<p>This is text.</p>',
     correctAnswerString: 'sunrise',
     correctAnswerNumeric: 7.9
    },

    {questionHTML: '<p>This is text.</p>',
     correctAnswerNumeric: 7,
     correctAnswerRegex: regex("/354\s*[+]\s*651/")
    }
  ],

  };
""")
    # pylint: enable=anomalous-backslash-in-string
    verify_assessment(assessment_text)


def test_activity_ast():
    """Test a mix of various activities using legacy and new parser."""
    activity_text = (
        """activity = [

  '<p>This is just some <i>HTML</i> text!</p>',

  { questionType: 'multiple choice',
    questionHTML: '<p>What letter am I thinking about now?</p>',
    choices: [
          ['A', false, '"A" is wrong, try again.'],
          ['B', true, '"B" is correct!'],
          ['C', false, '"C" is wrong, try again.'],
          ['D', false, '"D" is wrong, try again.']
    ]
  },

  { questionType: 'freetext',
    questionHTML: '<p>What color is the snow?</p>',
    correctAnswerRegex: regex("/white/i"),
    correctAnswerOutput: 'Correct!',
    incorrectAnswerOutput: 'Try again.',
    showAnswerOutput: 'Our search expert says: white!' },

  { questionType: 'multiple choice group',
    questionGroupHTML:
        '<p>This section will test you on colors and numbers.</p>',
    allCorrectMinCount: 2,
    questionsList: [
          {questionHTML: 'Pick all <i>odd</i> numbers:',
           choices: ['1', '2', '3', '4', '5'], correctIndex: [0, 2, 4]},
          {questionHTML: 'Pick one <i>even</i> number:',
           choices: ['1', '2', '3', '4', '5'], correctIndex: [1, 3],
           multiSelect: false},
          {questionHTML: 'What color is the sky?',
           choices: ['#00FF00', '#00FF00', '#0000FF'], correctIndex: 2}
    ],
    allCorrectOutput: 'Great job! You know the material well.',
    someIncorrectOutput: 'You must answer at least two questions correctly.'
  }

];
""")

    verify_activity(activity_text)

    scope = verify.Activity().scope
    current_ast = ActivityParser13.parse_string_in_scope(
        activity_text, scope, 'activity')
    expected_ast = verify.legacy_eval_python_expression_for_test(
        activity_text, scope, 'activity')

    same = (
        len(current_ast.get('activity')) == 4 and
        current_ast.get('activity') == expected_ast.get('activity') and
        current_ast == expected_ast)
    if not same:
        import pprint
        pprint.pprint(current_ast.get('activity'))
        pprint.pprint(expected_ast.get('activity'))
    assert same


def test_assessment_ast():
    """Test a mix of various activities using legacy and new parser."""
    # pylint: disable=anomalous-backslash-in-string
    assessment_text = (
        """assessment = {
  preamble: '<p>This is text.</p>',
  questionsList: [
    {'questionHTML': '<p>This is text.</p>',
     choices:
         ["A and B", "D and B", correct("A and C"), "C and D", "I don't know"]
    },
    {"questionHTML": '<p>This is text.</p>',
     choices: [correct("True"), "False", "I don't know"],
     choiceScores: [0, 0.5, 1.0],
     weight: 3
    },
    {questionHTML: '<p>This is text.</p>',
     correctAnswerString: 'sunrise'
    },
    {questionHTML: '<p>This is text.</p>',
     correctAnswerRegex: regex("/354\s*[+]\s*651/")
    }
  ],
  assessmentName: 'Pre',
  checkAnswers: false
}
""")
    # pylint: enable=anomalous-backslash-in-string

    verify_assessment(assessment_text)

    scope = verify.Assessment().scope
    current_ast = AssessmentParser13.parse_string_in_scope(
        assessment_text, scope, 'assessment')
    expected_ast = verify.legacy_eval_python_expression_for_test(
        assessment_text, scope, 'assessment')
    same = (
        len(current_ast.get('assessment')) == 4 and
        len(current_ast.get('assessment').get('questionsList')) == 4 and
        current_ast.get('assessment') == expected_ast.get('assessment') and
        current_ast == expected_ast)
    if not same:
        import pprint
        pprint.pprint(current_ast.get('assessment'))
        pprint.pprint(expected_ast.get('assessment'))
    assert same


def test_list_of():
    """Test delimited list."""
    grammar = Optional(
        Literal('[') +
        Optional(list_of(Literal('a') ^ Literal('b'))) +
        Literal(']'))

    assert str(['[', ']']) == str(grammar.parseString('[]'))
    assert str(['[', 'a', ']']) == str(grammar.parseString('[a]'))
    assert str(['[', 'b', ']']) == str(grammar.parseString('[b]'))
    assert str(['[', 'a', ']']) == str(grammar.parseString('[a,]'))
    assert str(['[', 'b', ']']) == str(grammar.parseString('[b,]'))
    assert str(['[', 'a', 'a', 'a', 'a', ']']) == str(
        grammar.parseString('[a,    a, a,       a]'))
    assert str(['[', 'a', 'a', 'a', 'a', ']']) == str(
        grammar.parseString('[a,a,a,a]'))
    assert str(['[', 'a', 'a', 'a', 'a', ']']) == str(
        grammar.parseString('[a,a,a,a,]'))
    assert str(['[', 'a', 'b', 'a', 'b', ']']) == str(
        grammar.parseString('[a,b,a,b]'))
    assert str(['[', 'b', 'a', 'b', 'a', ']']) == str(
        grammar.parseString('[b,a,b,a]'))
    assert str(['[', 'b', 'b', 'b', 'b', ']']) == str(
        grammar.parseString('[b,b,b,b]'))

    assert not grammar.parseString('')
    assert not grammar.parseString('[c]')
    assert not grammar.parseString('[a,c,b]')


def run_all_unit_tests():
    """Run all unit tests."""
    original = verify.parse_content
    try:
        verify.parse_content = parse_string_in_scope

        test_list_of()

        test_activity_multiple_choice()
        test_activity_free_text()
        test_activity_multiple_choice_group()
        test_activity_ast()

        test_assessment()
        test_assessment_ast()

        # test existing verifier using parsing instead of exec/compile
        verify.test_sample_assets()
    finally:
        verify.parse_content = original


if __name__ == '__main__':
    run_all_unit_tests()
