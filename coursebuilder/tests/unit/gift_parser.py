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
        self.assertEqual(37, len(questions))
        for question in questions:
            r = gift.GiftParser.gift.parseString(question)
            assert r.task

    def _get_sample_questions(self):
        curr_dir = os.path.dirname(os.path.realpath(__file__))
        fn = 'gift_examples.txt'
        path = os.path.join(curr_dir, fn)
        return open(path, 'rb').read().split('\n\n')


class TestEssayAndNumericalQuestion(unittest.TestCase):
    """Tests for parsing Essay and Numerical questions."""

    def test_essay_question(self):
        answer = '{}'
        assert not gift.GiftParser.essay_answer.parseString(answer)
        s = 'Write a short biography of Dag Hammarskjold. {}'
        r = gift.GiftParser.essay_question.parseString(s)
        self.assertEqual(
            'Write a short biography of Dag Hammarskjold.', r.task)

    def test_numerical_answers(self):
        r = gift.GiftParser.numerical_answer.parseString('{#1.5:0.1}')
        self.assertEqual(1.5, r.answer)
        self.assertEqual(0.1, r.error)

        r = gift.GiftParser.numerical_answer.parseString('{#-25:2}')
        self.assertEqual(-25, r.answer)
        self.assertEqual(2, r.error)

        # test for question w.o. error margin
        r = gift.GiftParser.numerical_answer.parseString('{#2}')
        self.assertEqual(2, r.answer)

        # test range question
        s = 'What is the value of pi (to 3 decimal places)? {#3.141..3.142}.'
        r = gift.GiftParser.gift.parseString(s)
        self.assertEqual(3.141, r.min)
        self.assertEqual(3.142, r.max)


class TestMatchQuestion(unittest.TestCase):
    """Tests for parsing Match questions."""

    def test_answers(self):
        r = gift.GiftParser.match_answers.parseString(
            '{=a->1 = b->2 =c-> 3}')
        self.assertEqual(['a', 'b', 'c'], [x.lhs for x in r])
        self.assertEqual(['1', '2', '3'], [x.rhs for x in r])

        # there must be at least 3 pairs
        with self.assertRaises(ParseException):
            gift.GiftParser.match_answers.parseString('{=a->1 =b->2}')

    def test_question(self):
        s = """
            Match the following countries with their corresponding capitals. {
            =Canada -> Ottawa
            =Italy  -> Rome
            =Japan  -> Tokyo
            =India  -> New Delhi
            }"""
        r = gift.GiftParser.gift.parseString(s)
        t = 'Match the following countries with their corresponding capitals.'
        self.assertEqual(t, r.task)
        self.assertEqual(4, len(r.answers))


class TestMissingWordQuestion(unittest.TestCase):
    """Tests for parsing Missing Word questions."""

    def test_answers(self):
        r = gift.GiftParser.mw_answers.parseString('{=c ~w1 ~w2}')
        self.assertEqual('c', r.correct[0])

    def test_question(self):
        s = 'CourseBuilder costs {~lots of money =nothing ~little} to download.'
        r = gift.GiftParser.gift.parseString(s)
        self.assertEqual('CourseBuilder costs', r[0])
        self.assertEqual(3, len(r.answers))


class TestSaQuestion(unittest.TestCase):
    """Tests for parsing Short Answer questions."""

    def test_answer(self):
        r = gift.GiftParser.sa_answer.parseString('=a=')
        self.assertEqual('a', r[0])
        r = gift.GiftParser.sa_answer.parseString('=a }')
        self.assertEqual('a', r[0])

    def test_answers(self):
        s = '{=foo =bar}'
        r = gift.GiftParser.sa_answers.parseString(s)
        self.assertEqual(['foo', 'bar'], [r.answers[0], r.answers[1]])

    def test_question(self):
        s = 'Two plus two equals {=four =4}'
        r = gift.GiftParser.sa_question.parseString(s)
        self.assertEqual('Two plus two equals', r.task)
        self.assertEqual('four', r.answers[0])
        self.assertEqual('4', r.answers[1])
        assert gift.GiftParser.gift.parseString(s)


class TestTrueFalseQuestion(unittest.TestCase):
    """Tests for parsing True-False questions."""

    def test_answer(self):
        r = gift.GiftParser.tf_answer.parseString('{T}')
        self.assertEqual(True, r.answer)

        r = gift.GiftParser.tf_answer.parseString('{FALSE}')
        self.assertEqual(False, r.answer)

    def test_question(self):
        s = """
            // question: 0 name: TrueStatement using {T} style
            ::TrueStatement about Grant::
            Grant was buried in a tomb in New York City.{T}
        """
        r = gift.GiftParser.tf_question.parseString(s)
        self.assertEqual('TrueStatement about Grant', r.title)
        task = 'Grant was buried in a tomb in New York City.'
        self.assertEqual(task, r.task)
        self.assertEqual(True, r.answer)


class TestMcmaQuestion(unittest.TestCase):
    """Tests for parsing mul-choice questions with multiple correct answers."""

    def test_answer(self):
        r = gift.GiftParser.mcma_answer.parseString('~%50% a}')
        self.assertEqual(50, r.weight)
        self.assertEqual('a', r.answer)

        r = gift.GiftParser.mcma_answer.parseString('~%-100% a ~%')
        self.assertEqual(-100, r.weight)
        self.assertEqual('a', r.answer)

        # missing end of answer separator
        with self.assertRaises(ParseException):
            gift.GiftParser.mc_correct_answer.parseString('~%100%a')

    def test_answers(self):
        s = '{~%25%a1~%75%a2~%-100%a3}'
        r = gift.GiftParser.mcma_answers.parseString(s)
        self.assertEqual(6, len(r))

        s = '{~%25% a1~%75% a2 ~%-100% a3 }'
        r = gift.GiftParser.mcma_answers.parseString(s)
        self.assertEqual(6, len(r))

        s = '{~%25% a1~%75% a2 ~%-100% a3 }'
        r = gift.GiftParser.mcma_answers.parseString(s)

    def test_questions(self):
        question = """
            What two people are entombed in Grant's tomb? {
               ~%-100%No one
               ~%50%Grant
               ~%50%Grant's wife
               ~%-100%Grant's father
            }"""
        r = gift.GiftParser.mcma_question.parseString(question)
        task = 'What two people are entombed in Grant\'s tomb?'
        self.assertEqual(task, r.task)
        self.assertEqual(8, len(r.answers))


class TestHead(unittest.TestCase):
    """Tests for parsing question heads."""

    def test_title(self):
        r = gift.GiftParser.title.parseString('::Q1::')
        self.assertEqual('Q1', r.title)
        r = gift.GiftParser.title.parseString(':: Q1 ::')
        self.assertEqual('Q1', r.title)
        with self.assertRaises(ParseException):
            gift.GiftParser.title.parseString('Q1::')

    def test_title_n_task(self):
        r = gift.GiftParser.head.parseString('::Q1::Who?{')
        self.assertEqual('Q1', r.title)
        self.assertEqual('Who?', r.task)


class TestMcQuestion(unittest.TestCase):
    """Tests for parsing multiple-choice questions with one correct answer."""

    def test_answer(self):
        r = gift.GiftParser.mc_correct_answer.parseString('= c }')
        self.assertEqual('c', r.correct)

        r = gift.GiftParser.mc_wrong_answer.parseString('~w ~')
        self.assertEqual('w', r.wrong)

        # missing trailing separator
        with self.assertRaises(ParseException):
            gift.GiftParser.mc_correct_answer.parseString('=c')

    def test_answers(self):
        r = gift.GiftParser.mc_answers.parseString('{~w1 =c ~w2}')
        self.assertEqual('c', r.correct)

        r = gift.GiftParser.mc_answers.parseString('{=c ~w1 ~w2}')
        self.assertEqual('c', r.correct)

        r = gift.GiftParser.mc_answers.parseString('{=c ~w1 ab~w2}')
        self.assertEqual('c', r.correct)

        r = gift.GiftParser.mc_answers.parseString('{=c a ~w1 a~w2}')
        self.assertEqual('c a', r.correct)

        s = ("{ =yellow # right; good! ~red # wrong, "
             "it's yellow ~blue # wrong, it's yellow }")
        r = gift.GiftParser.mc_answers.parseString(s)
        self.assertEqual('yellow # right; good!', r.correct)

    def test_questions(self):
        s = '''
            // comment
            ::Q2:: What's between orange and green in the spectrum?
            { =yellow # right; good! ~red # wrong, it's yellow ~blue
            # wrong, it's yellow }
            '''
        r = gift.GiftParser.mc_question.parseString(s)
        self.assertEqual('Q2', r.title)
        self.assertEqual("What's between orange and green in the spectrum?",
                         r.task)
        self.assertEqual('yellow # right; good!', r.correct)
        self.assertEqual(3, len(r.answers))
        self.assertEqual(0, len(r.wrong1))
        self.assertEqual(2, len(r.wrong2))

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
        r = gift.GiftParser.mc_question.parseString(s)
        self.assertEqual('Question title', r.title)
        self.assertEqual('Question', r.task)
        self.assertEqual('A correct answer', r.correct)
        self.assertEqual(5, len(r.answers))
        self.assertEqual(4, len(r.wrong2))

    def test_question_short_form(self):
        s = ('Question{= A correct answer ~Wrong answer1 ~Wrong answer2 '
             '~Wrong answer3 ~Wrong answer4 }')
        r = gift.GiftParser.mc_question.parseString(s)
        self.assertEqual('Question', r.task)
        self.assertEqual('A correct answer', r.correct)
        self.assertEqual(5, len(r.answers))
        self.assertEqual(4, len(r.wrong2))

