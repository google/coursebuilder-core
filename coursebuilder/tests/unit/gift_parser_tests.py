# coding: utf-8
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

"""Runs all unit tests for GIFT."""

__author__ = 'Boris Roussev (borislavr@google.com)'

import os
import unittest
from pyparsing import ParseException
from modules.assessment_tags import gift


class SampleQuestionsTest(unittest.TestCase):
    """Tests a large bank of GIFT questions.

    Moodle version: 2.7.2+
    https://github.com/moodle/moodle/blob/master/question/format/gift/
    """

    def test_sample_questions(self):
        questions = self._get_sample_questions()
        self.assertEqual(28, len(questions))
        for question in questions:
            result = gift.GiftParser.parse(question)[0]
            question = gift.to_dict(result)
            assert 'question' in question

    def _get_sample_questions(self):
        curr_dir = os.path.dirname(os.path.realpath(__file__))
        fn = 'gift_examples.txt'
        path = os.path.join(curr_dir, fn)
        return open(path, 'rb').read().split('\n\n')


class TestEssayAndNumericQuestion(unittest.TestCase):
    """Tests for parsing Essay and Numeric questions."""

    def test_essay_answer(self):
        answer = '{}'
        result = gift.GiftParser.essay_answer.parseString(answer)
        assert not result

    def test_essay_question(self):
        task = 'Write a short biography of Dag Hammarskjold.'
        text = '%s {}' % task
        result = gift.GiftParser.essay_question.parseString(text)[0]
        question = gift.to_dict(result[1])
        self.assertEqual(task, question['task'])

    def test_numeric_single_answer(self):
        result = gift.GiftParser.numeric_answer.parseString('{#1.5:0.1}')
        self.assertEqual(1.5, result.answer)
        self.assertEqual(0.1, result.error)

        result = gift.GiftParser.numeric_answer.parseString('{#-25:2}')
        self.assertEqual(-25, result.answer)
        self.assertEqual(2, result.error)

    def test_numeric_range_answer(self):
        # test for question w.o. error margin
        result = gift.GiftParser.numeric_answer.parseString('{#2}')
        self.assertEqual(2, result.answer)

        # test range question
        s = 'What is the value of pi (to 3 decimal places)? {#3.141..3.142}.'
        result = gift.GiftParser.numeric_question.parseString(s)[0]
        question = gift.to_dict(result[1])
        self.assertEqual(3.141, question['choices'][0]['min'])
        self.assertEqual(3.142, question['choices'][0]['max'])


class TestMatchQuestion(unittest.TestCase):
    """Tests for parsing Match questions."""

    def test_answers(self):
        result = gift.GiftParser.match_answers.parseString(
            '{=a->1 = b->2 =c->3}')
        answers = gift.to_dict(result[0])
        self.assertEqual(
            ['a', 'b', 'c'],
            [x['lhs'] for x in answers['choices']])
        self.assertEqual(
            ['1', '2', '3'],
            [x['rhs'] for x in answers['choices']])

    def test_min_number_of_matches(self):
        # there must be at least 3 pairs
        with self.assertRaises(ParseException):
            gift.GiftParser.match_answers.parseString('{=a->1 =b->2}')

    def test_question(self):
        task = ('Match the following countries with their '
                'corresponding capitals.')
        text = """
            %s {
            =Canada -> Ottawa
            =Italy  -> Rome
            =Japan  -> Tokyo
            =India  -> New Delhi
            }""" % task
        result = gift.GiftParser.match_question.parseString(text)[0]
        question = gift.to_dict(result[1])
        self.assertEqual(task, question['task'])
        # assert there are four matching clauses
        self.assertEqual(4, len(question['choices']))


class TestMissingWordQuestion(unittest.TestCase):
    """Tests for parsing Missing Word questions."""

    def test_answers(self):
        s = '=c ~w1 ~w2}'
        result = gift.GiftParser.missing_word_answers.parseString(s)
        answers = gift.to_dict(result[0][1])
        self.assertEqual('c', answers[0]['text'])
        self.assertEqual(100, answers[0]['score'])

    def test_question(self):
        s = 'CourseBuilder costs {~lots of money =nothing ~little} to download.'
        result = gift.GiftParser.missing_word_question.parseString(s)
        question = gift.to_dict(result[0][1])
        self.assertEqual('CourseBuilder costs ', question['prefix'])
        self.assertEqual(3, len(question['choices']))


class TestShortAnswerQuestion(unittest.TestCase):
    """Tests for parsing Short Answer questions."""

    def test_answer(self):
        result = gift.GiftParser.short_answer.parseString('=a=')[0]
        self.assertEqual('a', gift.to_dict(result)['text'])
        result = gift.GiftParser.short_answer.parseString('=a }')[0]
        self.assertEqual('a', gift.to_dict(result)['text'])

    def test_answers(self):
        s = '=foo =bar}'
        result = gift.GiftParser.short_answers.parseString(s)
        choices = gift.to_dict(result[0])
        self.assertEqual('foo', choices['choices'][0]['text'])
        self.assertEqual('bar', choices['choices'][1]['text'])

    def test_question(self):
        s = 'Two plus two equals { =four =4}'
        result = gift.GiftParser.short_answer_question.parseString(s)[0]
        question = gift.to_dict(result[1])
        self.assertEqual('Two plus two equals', question['task'])
        self.assertEqual('four', question['choices'][0]['text'])
        self.assertEqual('4', question['choices'][1]['text'])


class TestTrueFalseQuestion(unittest.TestCase):
    """Tests for parsing True-False questions."""

    def test_answer(self):
        r = gift.GiftParser.true_false_answer.parseString('{T}')
        self.assertEqual(True, r.answer)

        r = gift.GiftParser.true_false_answer.parseString('{FALSE}')
        self.assertEqual(False, r.answer)

    def test_question(self):
        s = """
            // question: 0 name: TrueStatement using {T} style
            ::TrueStatement about Grant::
            Grant was buried in a tomb in New York City.{T}
        """
        result = gift.GiftParser.true_false_question.parseString(s)[0]
        question = gift.to_dict(result[1])
        self.assertEqual('TrueStatement about Grant', question['title'])
        task = 'Grant was buried in a tomb in New York City.'
        self.assertEqual(task, question['task'])
        self.assertEqual(True, question['choices'][0]['text'])


class TestMultiChoiceMultipleSelectionQuestion(unittest.TestCase):
    """Tests for parsing mul-choice questions with multiple correct answers."""

    def test_answer(self):
        result = gift.GiftParser.multi_choice_answer.parseString('~%50% a}')[0]
        answer = gift.to_dict(result)
        self.assertEqual(50, answer['score'])
        self.assertEqual('a', answer['text'])

        result = gift.GiftParser.multi_choice_answer.parseString(
            '~%-100% a ~%')[0]
        answer = gift.to_dict(result)
        self.assertEqual(-100, answer['score'])
        self.assertEqual('a', answer['text'])

        # missing end of answer separator
        with self.assertRaises(ParseException):
            gift.GiftParser.multi_choice_answer.parseString('~%100%a')

    def test_answers_spaces_and_separators(self):
        tests = [
            '~%25%a1~%75%a2~%-100%a3}',
            '~%25% a1~%75% a2 ~%-100% a3 }',
            '~%25% a1~%75% a2 ~%-100% a3 }']
        for s in tests:
            result = gift.GiftParser.multi_choice_answers.parseString(s)[0]
            choices = gift.to_dict(result[1])
            self.assertEqual(3, len(choices))

    def test_questions(self):
        task = 'What two people are entombed in Grant\'s tomb?'
        question = """
            %s {
               ~%-100%No one
               ~%50%Grant
               ~%50%Grant's wife
               ~%-100%Grant's father
            }""" % task
        result = gift.GiftParser.multi_choice_question.parseString(question)[0]
        question = gift.to_dict(result)['question']
        self.assertEqual(task, question['task'])
        self.assertEqual(4, len(question['choices']))


class TestHead(unittest.TestCase):
    """Tests for parsing question heads."""

    def test_title(self):
        result = gift.GiftParser.title.parseString('::Q1::')
        self.assertEqual('Q1', result.title)
        result = gift.GiftParser.title.parseString(':: Q1 ::')
        self.assertEqual('Q1', result.title)
        with self.assertRaises(ParseException):
            gift.GiftParser.title.parseString('Q1::')

    def test_title_n_task(self):
        r = gift.GiftParser.task.parseString('Who?{')
        self.assertEqual('Who?', r.task)


class TestMultiChoiceQuestion(unittest.TestCase):
    """Tests for parsing multiple-choice questions with one correct answer."""

    def test_answer(self):
        result = gift.GiftParser.multi_choice_answer.parseString('= c }')[0]
        answer = gift.to_dict(result)
        self.assertEqual('c', answer['text'])

        result = gift.GiftParser.multi_choice_answer.parseString('~w ~')[0]
        answer = gift.to_dict(result)
        self.assertEqual('w', answer['text'])

        # test missing trailing separator
        with self.assertRaises(ParseException):
            gift.GiftParser.multi_choice_answer.parseString('=c')

    def test_scores_spaces_and_separators(self):
        result = gift.GiftParser.multi_choice_answers.parseString(
            '~w1 =c ~w2}')[0]
        answers = gift.to_dict(result)
        self.assertEqual([0, 100, 0], [x['score'] for x in answers['choices']])

        result = gift.GiftParser.multi_choice_answers.parseString(
            '=c ~w1 ab~w2}')[0]
        answers = gift.to_dict(result)
        self.assertEqual([100, 0, 0], [x['score'] for x in answers['choices']])
        self.assertEqual('w1 ab', answers['choices'][1]['text'])

        s = (' =yellow # right; good! ~red # wrong, '
             'it\'s yellow ~blue # wrong, it\'s yellow }')
        result = gift.GiftParser.multi_choice_answers.parseString(s)[0]
        answers = gift.to_dict(result)
        self.assertEqual('yellow', answers['choices'][0]['text'])
        self.assertEqual(
            'right; good!', answers['choices'][0]['feedback'])

    def test_questions(self):
        s = '''
            // comment
            ::Q2:: What's between orange and green in the spectrum?
            { =yellow # right; good! ~red # wrong, it's yellow ~blue
            # wrong, it's yellow }
            '''
        result = gift.GiftParser.multi_choice_question.parseString(s)[0]
        question = gift.to_dict(result)['question']
        self.assertEqual('Q2', question['title'])
        self.assertEqual(
            "What's between orange and green in the spectrum?",
            question['task'])
        self.assertEqual(3, len(question['choices']))

    def test_question_long_form(self):
        s = '''
            //Comment line
            ::Question title
            :: Question {
            =A correct answer
            ~Wrong answer1
            #A response to wrong answer1
            ~Wrong answer2
            #A response to wrong answer2
            ~Wrong answer3
            #A response to wrong answer3
            ~Wrong answer4
            #A response to wrong answer4
            }'''
        result = gift.GiftParser.multi_choice_question.parseString(s)[0]
        question = gift.to_dict(result)['question']
        self.assertEqual('Question title', question['title'])
        self.assertEqual('Question', question['task'])
        self.assertEqual(5, len(question['choices']))
        self.assertEqual(
            [100, 0, 0, 0, 0],
            [x['score'] for x in question['choices']])

    def test_question_short_form(self):
        s = ('Question{= A correct answer ~Wrong answer1 ~Wrong answer2 '
             '~Wrong answer3 ~Wrong answer4 }')
        result = gift.GiftParser.multi_choice_question.parseString(s)[0]
        question = gift.to_dict(result)['question']
        self.assertEqual('Question', question['task'])
        self.assertEqual(5, len(question['choices']))
        self.assertEqual(
            [100, 0, 0, 0, 0],
            [x['score'] for x in question['choices']])


class TestCreateManyGiftQuestion(unittest.TestCase):
    """Tests for parsing and converting ``a list of GIFT questions."""

    def test_create_many(self):
        gift_text = """
::t1:: q1? {~%30% c1 #fb1 ~%70% c2 ~c3 # fb3}

::t2:: q2? {=c1 #c1fb ~w1a #w1afb ~w1b # w1bfb}

::t3:: q4? {T}

::t4:: q4? {F #fb}

::t5:: Who's buried in Grant's tomb?{=Grant =Ulysses S. Grant =Ulysses Grant}

::t6:: Two plus two equals {=four =4}

::t7:: When was Ulysses S. Grant born?{#1822:5}
"""
        questions = gift.GiftParser.parse_questions(gift_text)
        assert all(questions)
        self.assertEqual(
            ['multi_choice'] * 4 + ['short_answer'] * 3,
            [x['type'] for x in questions])

