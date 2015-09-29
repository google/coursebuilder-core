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


import logging

from pyparsing import alphanums
from pyparsing import Combine
from pyparsing import LineEnd
from pyparsing import Literal
from pyparsing import nums
from pyparsing import OneOrMore
from pyparsing import Optional
from pyparsing import ParseException
from pyparsing import restOfLine
from pyparsing import SkipTo
from pyparsing import Suppress
from pyparsing import Word


class ParseError(Exception):
    """Exception raised to show that a validation failed."""


def to_dict(item):
    if isinstance(item, list):
        return [to_dict(x) for x in item]
    elif isinstance(item, tuple):
        if isinstance(item[0], tuple):
            return dict([(x[0], to_dict(x[1])) for x in item])
        else:
            return {item[0]: to_dict(item[1])}
    else:
        return item


def sep(separator):
    """Makes a suppressed separator."""
    return Suppress(Literal(separator))


def strip_spaces(value):
    """Strips leading and trailing white spaces."""
    return value[0].strip()


def make_int(value):
    """Makes an int value lambda."""
    return int(value[0])


def make_true(unused_value):
    """Makes a True boolean value lambda."""
    return True


def make_false(unused_value):
    """Makes a False boolean value lambda."""
    return False


def make_float(tokens):
    """Makes a float value lambda."""
    return float(tokens[0])


def batch(tokens, size=3):
    return zip(*[iter(tokens)] * size)


def set_multi_answer_question(toks, question_type):
    choices = next(
        x[1] for x in toks if isinstance(x, tuple) and x[0] == 'choices')
    return ('question', (
        ('type', question_type),
        ('title', toks.title),
        ('task', toks.task),
        ('choices', choices)))


# multi choice question parse actions
def set_multi_choice_answer(toks):
    weight = 100 if toks.sign == '=' else toks.weight
    return (
        ('sign', toks.sign),
        ('score', weight),
        ('text', toks.answer),
        ('feedback', toks.feedback))


def set_multi_choice_answers(toks):
    return ('choices', toks.asList())


def set_multi_choice_question(toks):
    return set_multi_answer_question(toks, 'multi_choice')


# short answer question parse actions
set_short_answer = set_multi_choice_answer
set_short_answers = set_multi_choice_answers


def set_short_answer_question(toks):
    return set_multi_answer_question(toks, 'short_answer')


# true false question parse actions
def set_true_false_question(toks):
    return ('question', (
        ('type', 'true_false'),
        ('title', toks.title),
        ('task', toks.task),
        ('choices', [
            (('text', toks.answer), ('feedback', toks.feedback))])))


# match answer question parse actions
def set_match_answer(toks):
    return (
        ('lhs', toks.lhs),
        ('rhs', toks.rhs),
        ('feedback', toks.feedback))


def set_match_answers(toks):
    return ('choices', toks.asList())


def set_match_answer_question(toks):
    return set_multi_answer_question(toks, 'match_answer')


# missing word question parse actions
def set_missing_word_question(toks):
    choices = next(
        x[1] for x in toks if isinstance(x, tuple) and x[0] == 'choices')
    return ('question', (
        ('type', 'missing_word'),
        ('prefix', toks.prefix),
        ('choices', choices),
        ('suffix', toks.suffix)))


# numeric question parse actions
def set_numeric_question(toks):
    return ('question', (
        ('type', 'numeric'),
        ('title', toks.title),
        ('task', toks.task),
        ('choices', [(
            ('text', toks.answer),
            ('error', toks.error),
            ('min', toks.min),
            ('max', toks.max),
            ('feedback', toks.feedback))])))


def set_essay_question(toks):
    return ('question', (
        ('type', 'essay'),
        ('title', toks.title),
        ('task', toks.task)))


def set_questions(toks):
    return ('questions', toks)


class GiftParser(object):
    """Parser for GIFT format questions."""

    # separators, which have been suppressed
    double_colon = sep('::')

    colon = sep(':')

    span = sep('..')

    left_curly = sep('{')

    right_curly = sep('}')

    equals = sep('=')

    tilda = sep('~')

    percent = sep('%')

    arrow = sep('->')

    pound = sep('#')

    dbl_fwd_slash = sep('//')

    # integer signs
    plus = Literal('+')
    minus = Literal('-')

    bool_true = (
        Literal('TRUE') |
        Literal('T')).setParseAction(make_true)

    bool_false = (
        Literal('FALSE') |
        Literal('F')).setParseAction(make_false)

    boolean = bool_true | bool_false

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

    blank_lines = Suppress(LineEnd() + OneOrMore(LineEnd()))

    comment = dbl_fwd_slash + restOfLine

    title = (double_colon +
             SkipTo(double_colon).setParseAction(
                 strip_spaces)('title') +
             double_colon)

    task = SkipTo(left_curly).setParseAction(
        strip_spaces)('task')

    # Multiple choice questions with one correct answer.
    #
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
    # #She was buried in India }
    #
    # Multiple choice questions with multiple right answers.
    #
    # What two people are entombed in Grant's tomb? {
    # ~%-100%No one
    # ~%50%Grant
    # ~%50%Grant's wife
    # ~%-100%Grant's father}

    eof_multi_choice_answer = equals | tilda | right_curly

    ext_eof_multi_choice_answer = pound | eof_multi_choice_answer

    # '# hello world ~'
    multi_choice_feedback = Combine(
        pound +
        SkipTo(eof_multi_choice_answer).setParseAction(strip_spaces))

    # 'answer #'
    multi_choice_answer_text = SkipTo(
        ext_eof_multi_choice_answer).setParseAction(strip_spaces)

    weight = Combine(percent + integer + percent).setParseAction(make_int)

    multi_choice_answer = (
        (Literal('=')('sign') |
         Literal('~')('sign') + Optional(weight, default=0)('weight')) +
        multi_choice_answer_text('answer') +
        Optional(multi_choice_feedback, default='')('feedback')
    ).setParseAction(set_multi_choice_answer)

    multi_choice_answers = OneOrMore(multi_choice_answer)

    multi_choice_question = (
        Optional(title, default='') +
        task +
        left_curly +
        multi_choice_answers.setParseAction(set_multi_choice_answers) +
        right_curly
    ).setParseAction(set_multi_choice_question)

    multi_choice_question.ignore(comment)

    # True-false questions.
    # Sample:
    # // question: 0 name: TrueStatement using {T} style
    # ::TrueStatement about Grant::Grant was buried in a tomb in NY.{T}
    #
    # // question: 0 name: FalseStatement using {FALSE} style
    # ::FalseStatement about sun::The sun rises in the West.{FALSE}

    true_false_feedback = Combine(
        pound +
        SkipTo(right_curly).setParseAction(strip_spaces))

    true_false_answer = (
        left_curly +
        boolean('answer') +
        Optional(true_false_feedback, default='')('feedback') +
        right_curly)

    true_false_question = (
        Optional(title, default='') +
        task +
        true_false_answer
    ).setParseAction(set_true_false_question)

    true_false_question.ignore(comment)

    # Short answer questions.
    # Samples:
    # Who's buried in Grant's tomb?{=Grant =Ulysses S. Grant =Ulysses Grant}
    # Two plus two equals {=four =4}

    eof_short_answer_answer = equals | right_curly

    ext_eof_short_answer = pound | eof_short_answer_answer

    short_answer_feedback = Combine(
        pound +
        SkipTo(eof_short_answer_answer).setParseAction(strip_spaces))

    short_answer_text = SkipTo(ext_eof_short_answer).setParseAction(
        strip_spaces)

    short_answer = (
        equals +
        short_answer_text('answer') +
        Optional(short_answer_feedback, default='')('feedback')
    ).setParseAction(set_short_answer)

    short_answers = (
        OneOrMore(short_answer) +
        right_curly +
        LineEnd())

    short_answer_question = (
        Optional(title, default='') +
        task +
        left_curly +
        short_answers.setParseAction(set_short_answers)
    ).setParseAction(set_short_answer_question)

    short_answer_question.ignore(comment)

    # Matching questions.
    # Sample:
    # Match the following countries with their corresponding capitals. {
    # =Canada -> Ottawa
    # =Italy  -> Rome
    # =Japan  -> Tokyo
    # =India  -> New Delhi
    # }

    eof_match_answer = equals | right_curly

    ext_eof_match_answer = pound | equals | right_curly

    match_feedback = Combine(
        pound +
        SkipTo(eof_match_answer).setParseAction(strip_spaces))

    lhs = SkipTo(arrow).setParseAction(strip_spaces)

    match_answer = (
        equals +
        lhs('lhs') +
        arrow +
        SkipTo(ext_eof_match_answer)('rhs') +
        Optional(match_feedback, default='')('feedback')
    ).setParseAction(set_match_answer)

    match_answers = (
        left_curly +
        match_answer + match_answer + OneOrMore(match_answer) +
        right_curly)

    match_question = (
        Optional(title, default='') +
        task +
        match_answers.setParseAction(set_match_answers)
    ).setParseAction(set_match_answer_question)

    match_question.ignore(comment)

    # Missing word questions.
    #
    # CB costs {~lots of money =nothing ~a small amount} to download.

    missing_word_answers = multi_choice_answers

    prefix = SkipTo(left_curly)

    suffix = Combine(OneOrMore(Word(alphanums)))

    missing_word_question = (
        prefix('prefix') +
        left_curly +
        missing_word_answers.setParseAction(set_multi_choice_answers) +
        right_curly +
        suffix('suffix')
    ).setParseAction(set_missing_word_question)

    # Numeric questions.
    # No support for multiple numeric answers.
    # Sample: When was Ulysses S. Grant born?{#1822:5}

    numeric_single_answer = (
        left_curly +
        pound +
        signed_float.setParseAction(make_float)('answer') +
        Optional(
            colon +
            unsigned_float.setParseAction(make_float)('error')) +
        Optional(match_feedback, default='')('feedback') +
        right_curly)

    numeric_range_answer = (
        left_curly +
        pound +
        signed_float.setParseAction(make_float)('min') +
        span +
        signed_float.setParseAction(make_float)('max') +
        right_curly)

    numeric_answer = (
        numeric_range_answer |
        numeric_single_answer)

    numeric_question = (
        Optional(title, default='') +
        task +
        numeric_answer
    ).setParseAction(set_numeric_question)

    numeric_question.ignore(comment)

    # Essay questions.
    # Write a short biography of Dag Hammarskjold. {}

    essay_answer = left_curly + right_curly

    essay_question = (
        Optional(title, default='') +
        task +
        essay_answer
    ).setParseAction(set_essay_question)

    essay_question.ignore(comment)

    question = (
        essay_question |
        match_question |
        numeric_question |
        missing_word_question |
        multi_choice_question |
        true_false_question |
        short_answer_question)

    bnf = OneOrMore(question)

    @classmethod
    def parse(cls, text):
        if not text:
            raise ValueError('Questions field can\'t be blank.')
        try:
            return cls.bnf.parseString(text)
        except ParseException as e:
            logging.exception('Invalid GIFT syntax: %s', text)
            raise ParseError(e.msg)

    @classmethod
    def parse_questions(cls, text):
        """Parses a list new-line separated GIFT questions to."""
        tree = cls.parse(text)
        return [GiftAdapter().convert_to_question(node) for node in tree]


class GiftAdapter(object):
    """Converts a GIFT-formatted question to a CB question dict."""

    QUESTION_TYPES = ['multi_choice', 'true_false', 'short_answer', 'numeric']

    def normalize_score(self, score):
        return score / 100.0

    def convert_to_question(self, result):
        src = to_dict(result[1])
        question = self.build_question(src)
        if question['type'] == 'multi_choice':
            question['type'] = self.determine_question_type(question)
        return self.add_choices(question)

    def build_question(self, src):
        """Builds a question dictionary from a ParseResult object."""
        if src['type'] not in self.QUESTION_TYPES:
            raise ValueError(
                'Unsupported question type: %s' % src['type'].replace(
                    '_', ' '))
        question = {}
        question['type'] = src['type']
        question['question'] = src['task']
        question['description'] = src['title'] or question['question']
        question['choices'] = src['choices']
        return question

    def add_choices(self, question):
        if question['type'] == 'true_false':
            return self.add_true_false_choices(question)
        elif question['type'] == 'multi_choice':
            return self.add_multi_choice_answers(question)
        elif question['type'] == 'short_answer':
            return self.add_short_answer_choices(question)
        elif question['type'] == 'numeric':
            question['type'] = 'short_answer'
            return self.add_numeric_choices(question)
        else:
            raise ParseError(
                'Unsupported question type: %s' % question['type'].replace(
                    '_', ' '))

    def add_true_false_choices(self, question):
        question['type'] = 'multi_choice'
        question['multiple_selections'] = False
        choice = question['choices'][0]
        question['choices'] = []
        question['choices'].append({
            'text': 'True',
            'score': 1.0 if choice['text'] else 0.0,
            'feedback': choice['feedback']})
        question['choices'].append({
            'text': 'False',
            'score': 1.0 if not choice['text'] else 0.0,
            'feedback': choice['feedback']})
        return question

    def add_numeric_choices(self, question):
        question['rows'] = '1'
        question['columns'] = '100'
        question['graders'] = []
        for x in question.pop('choices'):
            question['graders'].append({
                'score': 1.0,
                'response': x['text'],
                'feedback': x['feedback'],
                'matcher': 'numeric'
            })
        return question

    def add_short_answer_choices(self, question):
        question['rows'] = '1'
        question['columns'] = '100'
        question['graders'] = []
        for x in question.pop('choices'):
            question['graders'].append({
                'score': self.normalize_score(x['score']),
                'response': x['text'],
                'feedback': x['feedback'],
                'matcher': 'case_insensitive'
            })
        return question

    def add_multi_choice_answers(self, question):
        # {'text': 'c', 'score': 1.0, 'feedback': 'fb', 'sign': '='} ..}]}
        question['choices'] = [dict(x) for x in question['choices']]
        self.validate_multi_choice(question)
        question['multiple_selections'] = self.is_multiple_selection(question)
        for x in question['choices']:
            x['score'] = self.normalize_score(x['score'])
            del x['sign']
        return question

    def determine_question_type(self, question_dict):
        signs = [x['sign'] for x in question_dict['choices']]
        if all(x == '=' for x in signs):
            return 'short_answer'
        else:
            return 'multi_choice'

    def validate_multi_choice(self, question_dict):
        signs = [x['sign'] for x in question_dict['choices']]
        if len(signs) < 2:
            msg_template = 'Multi-choice question with one choice: %s'
            logging.error(msg_template, question_dict)
            raise ParseError(msg_template % question_dict)
        scores = [x['score'] for x in question_dict['choices']]
        total = sum(scores)
        if total != 100:
            msg_template = "Choices' weights do not add up to 100: %s"
            logging.error(msg_template, question_dict)
            raise ParseError(msg_template % question_dict)
        if signs.count('=') > 1:
            msg_template = ('Multi-choice single-select question with more '
                            'than one correct choice: %s')
            logging.error(msg_template, question_dict)
            raise ParseError(msg_template % question_dict)

    def is_multiple_selection(self, question_dict):
        signs = [x['sign'] for x in question_dict['choices']]
        if signs.count('=') == 1:
            return False
        if all(x == '~' for x in signs):
            return True
        # {=c1 =c2 ~c3} is invalid
        raise ParseError('Unexpected choice types: %s' % question_dict)

