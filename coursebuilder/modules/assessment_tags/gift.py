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

"""Module for implementing GIFT format."""

__author__ = 'borislavr@google.com (Boris Roussev)'

from pyparsing import Combine
from pyparsing import Group
from pyparsing import LineEnd
from pyparsing import LineStart
from pyparsing import Literal
from pyparsing import nums
from pyparsing import OneOrMore
from pyparsing import Optional
from pyparsing import restOfLine
from pyparsing import SkipTo
from pyparsing import StringEnd
from pyparsing import Suppress
from pyparsing import Word
from pyparsing import ZeroOrMore


def sep(text):
    """Makes a suppressed separator."""
    return Suppress(Literal(text))


def strip_white_spaces(value):
    """Strips leading and trailing white spaces."""
    return value[0].strip()


def make_int(value):
    """Makes an int value lambda."""
    return int(value[0])


def make_float(value):
    """Makes an float value lambda."""
    return float(value[0])


def make_true(unused_value):
    """Makes a True boolean value lambda."""
    return True


def make_false(unused_value):
    """Makes a False boolean value lambda."""
    return False


class GiftParser(object):

    # separators, which have been suppressed
    double_colon = sep('::')
    colon = sep(':')
    span = sep('..')
    lcurly = sep('{')
    rcurly = sep('}')
    equals_sign = sep('=')
    tilda = sep('~')
    tilda_percent = sep('~%')
    percent = sep('%')
    arrow = sep('->')
    pound = sep('#')

    # integer signs
    plus = Literal('+')
    minus = Literal('-')

    boolTrue = (
        Literal('TRUE') |
        Literal('T')).setParseAction(make_true)

    boolFalse = (
        Literal('FALSE') |
        Literal('F')).setParseAction(make_false)

    boolean = boolTrue | boolFalse

    plus_or_minus = plus | minus

    number = Word(nums)

    integer = Combine(
        Optional(plus_or_minus) + number).setParseAction(make_int)

    unsigned_float = Combine(
        Word(nums) +
        Optional(Word('.', nums))).setParseAction(make_float)

    signed_float = Combine(
        Optional(plus_or_minus) +
        Word(nums) +
        Optional(Word('.', nums))).setParseAction(make_float)

    blanks = LineStart().leaveWhitespace()

    blank_line = blanks + LineEnd()

    comment = Suppress(Literal('//')) + restOfLine

    title = (double_colon +
             SkipTo(double_colon).setParseAction(
                 strip_white_spaces)('title') +
             double_colon)

    task = SkipTo(lcurly).setParseAction(strip_white_spaces)('task')

    head = Optional(title) + task

    # Multiple choice questions with one correct answer.
    # Sample:
    # // question: 1 name: Grants tomb
    # ::Grants tomb::Who is buried in Grant's tomb in New York City? {
    # =Grant
    # ~No one
    # #Was true for 12 years
    # ~Napoleon
    # #He was buried in France
    # ~Churchill
    # #He was buried in England
    # ~Mother Teresa
    # #She was buried in India
    # }

    mc_end_of_answer_separators = equals_sign | tilda | rcurly

    mc_correct_answer = (
        equals_sign +
        SkipTo(mc_end_of_answer_separators).setParseAction(
            strip_white_spaces)('correct'))

    mc_wrong_answer = (
        tilda +
        SkipTo(mc_end_of_answer_separators).setParseAction(
            strip_white_spaces)('wrong'))

    mc_wrong_answers_group = ZeroOrMore(mc_wrong_answer)

    mc_answers = (
        lcurly +
        mc_wrong_answers_group('wrong1') +
        mc_correct_answer +
        mc_wrong_answers_group('wrong2') +
        rcurly)('answers')

    mc_question = head + mc_answers

    # comments are ignored and not imported
    mc_question.ignore(comment)

    # Multiple choice questions with multiple right answers.
    # Sample
    # What two people are entombed in Grant's tomb? {
    # ~%-100%No one
    # ~%50%Grant
    # ~%50%Grant's wife
    # ~%-100%Grant's father
    # }

    mcma_end_of_answer_separators = tilda_percent | rcurly

    mcma_answer = (
        tilda_percent +
        integer('weight') +
        percent +
        SkipTo(mcma_end_of_answer_separators).setParseAction(
            strip_white_spaces)('answer'))

    mcma_answers = (
        lcurly +
        OneOrMore(mcma_answer)('answers') +
        rcurly)

    mcma_question = head + mcma_answers

    mcma_question.ignore(comment)

    # True-false questions.
    # Sample:
    # // question: 0 name: TrueStatement using {T} style
    # ::TrueStatement about Grant::Grant was buried in a tomb in NY.{T}
    #
    # // question: 0 name: FalseStatement using {FALSE} style
    # ::FalseStatement about sun::The sun rises in the West.{FALSE}

    tf_answer = lcurly + boolean.setResultsName('answer') + rcurly

    tf_question = head + tf_answer
    tf_question.ignore(comment)

    # Short answer questions.
    # Samples:
    # Who's buried in Grant's tomb?{=Grant =Ulysses S. Grant =Ulysses Grant}
    # Two plus two equals {=four =4}

    sa_separators = equals_sign | rcurly

    sa_answer = (
        equals_sign +
        SkipTo(sa_separators).setParseAction(strip_white_spaces))

    sa_answers = (
        lcurly +
        OneOrMore(sa_answer).setResultsName('answers') +
        rcurly)

    sa_question = head + sa_answers
    sa_question.ignore(comment)

    # Matching questions.
    # Sample:
    # Match the following countries with their corresponding capitals. {
    # =Canada -> Ottawa
    # =Italy  -> Rome
    # =Japan  -> Tokyo
    # =India  -> New Delhi
    # }

    match_separators = equals_sign | rcurly
    match_answer = Group(
        equals_sign +
        SkipTo(arrow).setParseAction(strip_white_spaces)('lhs') +
        arrow +
        SkipTo(match_separators).setParseAction(strip_white_spaces)('rhs'))
    match_answers = (
        lcurly +
        (match_answer + match_answer + OneOrMore(match_answer))('answers') +
        rcurly)
    match_question = head + match_answer
    match_question.ignore(comment)

    # Missing word questions.
    # Sample:
    # Moodle costs {~lots of money =nothing ~a small amount} to download.

    mw_answers = mc_answers
    prefix = SkipTo(lcurly).setResultsName('prefix')
    suffix = rcurly + SkipTo(StringEnd())
    mw_question = (
        prefix +
        mw_answers +
        suffix)

    # Numerical questions.
    # No support for multiple numerical answers.
    # Sample: When was Ulysses S. Grant born?{#1822:5}

    numerical_single_answer = (
        lcurly +
        pound +
        signed_float.setParseAction(make_float)('answer') +
        Optional(
            colon +
            unsigned_float.setParseAction(make_float)('error')) +
        rcurly)

    numerical_range_answer = (
        lcurly +
        pound +
        signed_float.setParseAction(make_float)('min') +
        span +
        signed_float.setParseAction(make_float)('max') +
        rcurly)

    numerical_answer = (
        numerical_single_answer |
        numerical_range_answer)

    numerical_question = head + numerical_answer
    numerical_question.ignore(comment)

    # Essay questions.
    # Write a short biography of Dag Hammarskjold. {}

    essay_answer = (lcurly + rcurly)('answer')

    essay_question = head + essay_answer
    essay_question.ignore(comment)

    # GIFT Grammar
    gift = head + (
        mc_answers |
        mcma_answers |
        tf_answer |
        sa_answers |
        match_answers |
        mw_answers |
        numerical_answer |
        essay_question)

    @classmethod
    def parse_question(cls, s):
        return cls.gift.parseString(s)

