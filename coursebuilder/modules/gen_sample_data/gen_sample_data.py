# Copyright 2016 Google Inc. All Rights Reserved.
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

"""Generates sample data for a course and its users."""

__author__ = ['Timothy Johnson (tujohnson@google.com)']

import os
import random

from common import safe_dom
from common import users
from common import utils as common_utils
from controllers import utils
from models import analytics
from models import courses
from models import custom_modules
from models import event_transforms
from models import models
from models import transforms
from models.models import EventEntity
from models.models import Student
from modules.dashboard import dashboard

from google.appengine.ext.testbed import datastore_stub_util

MODULE_NAME = 'gen_sample_data'
MODULE_TITLE = 'Generate Sample Data'


def register_analytic():
    """This isn't exactly an analytic, but we register that way to be included
    with the other analytics sub-tabs on the Dashboard."""
    name = 'sample_data'
    title = 'Generate Sample Data'
    sample_data = analytics.Visualization(name, title,
                                          os.path.join('modules',
                                                       'gen_sample_data',
                                                       'templates',
                                                       'sample_data.html'))
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'analytics', name, title, action='analytics_sample_data',
        contents=analytics.TabRenderer([sample_data]))


# Generates a random string from an ID between 1 and 10**16, inclusive
def _generate_id_num():
    return random.randint(1, 10**16)


class GenerateSampleQuizHandler(utils.BaseHandler):
    """Generates a new assessment for the currently active course."""

    NUM_QUESTIONS = 10
    NUM_ANSWERS = 10
    SAMPLE_QUIZ_PATH = 'generate-quiz'
    QUESTION_PREFIX = 'gen_sample: '

    # TODO(tujohnson): Re-use existing questions sometimes (future CL)
    # TODO(tujohnson): Also generate multiple-choice questions (future CL)
    def post(self):
        questions = [self._generate_question_data(i + 1)
                     for i in xrange(self.NUM_QUESTIONS)]

        self._create_assessment(questions)
        self.redirect(self.request.referer)

    def _create_assessment(self, questions):
        question_id_list = []
        for question in questions:
            question_id_list.append(self._add_question(question))

        questions_data_list = []
        for i in xrange(len(questions)):
            questions_data_list.append(
                str(safe_dom.Element(
                    'question',
                    quid=str(question_id_list[i]),
                    instanceid=common_utils.generate_instance_id())))

        questions_data = '\n'.join(questions_data_list)

        course = self.get_course()
        self._add_assessment(course, 'Next Assessment', questions_data)


    def _generate_question_data(self, question_num):
        question_name = '%sQuestion: %s' % (self.QUESTION_PREFIX, question_num)
        return self._generate_question_data_internal(question_num,
                                                     question_name)

    def _generate_question_data_internal(self, question_num, question_name):
        answer = str(random.randint(1, self.NUM_ANSWERS))
        question_data = {}

        # If a question is supposed to look automatically generated, we
        # tag the beginning of it with the prefix defined by the class.
        question_data['question'] = question_name
        question_data['rows'] = 1
        question_data['columns'] = 100
        question_data['defaultFeedback'] = ''
        question_data['graders'] = [{
            'matcher': 'case_insensitive',
            'feedback': '',
            'score': '1.0',
            'response': answer,
        }]
        question_data['type'] = 1
        question_data['description'] = 'Question ' + str(question_num)
        question_data['version'] = '1.5'
        question_data['hint'] = ''
        question_data_string = transforms.dumps(question_data)
        return question_data_string

    def _add_assessment(self, course, title, questions_data):
        assessment = course.add_assessment()
        assessment.title = title
        assessment.availability = courses.AVAILABILITY_AVAILABLE
        assessment.html_content = questions_data
        course.save()

    def _add_question(self, question_data):
        # Let the datastore choose the ID for entities that we create
        to_store = models.QuestionEntity(data=question_data)
        question_id = to_store.put().id()
        return str(question_id)


class GenerateSampleStudentsHandler(utils.BaseHandler):
    """Generates a new set of students for the currently active course"""

    NUM_STUDENTS = 10
    SAMPLE_STUDENTS_PATH = 'generate-students'
    EMAIL_PREFIX = 'gen_sample_student_'

    def post(self):
        student_emails = self._generate_emails(self.EMAIL_PREFIX)
        self._generate_students(student_emails)

        # Redirect back to original page
        self.redirect(self.request.referer)

    def _generate_emails(self, prefix):
        return ['%s%s@example.com' % (prefix, _generate_id_num())
                for i in xrange(self.NUM_STUDENTS)]

    def _generate_students(self, student_emails):
        course = self.get_course()
        for email in student_emails:
            user_id = datastore_stub_util.SynthesizeUserId(email)
            student = Student(name='Student%s' % user_id, key_name=user_id,
                              email=email, user_id=user_id, is_enrolled=True)
            Student.put(student)

            # Record our new student visiting the home page for our course,
            # then registering
            user = users.User(email=email, _user_id=user_id)
            host = os.environ['HTTP_HOST']
            self.visit_page(user, 'http://%s/%s' %
                            (host, course.title))
            self.visit_page(user, 'http://%s/%s'
                            '/course#registration_confirmation' %
                            (host, course.title))

    def visit_page(self, user, pageURL):
        source = 'enter-page'
        data = {}
        data['user_agent'] = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit'
                              '/537.36 (KHTML, like Gecko) Chrome'
                              '/51.0.2704.106 Safari/537.36')
        data['loc'] = {'page_locale': 'en_US', 'locale': 'en_US',
                       'region':'null', 'language': 'en-US,en;q=0.8',
                       'country': 'ZZ', 'city': 'null'}
        data['location'] = pageURL
        data_str = transforms.dumps(data)
        EventEntity.record(source, user, data_str)


class GenerateSampleScoresHandler(utils.BaseHandler):
    """Generates answers for automatically generated students.

    Students are determined to be automatically generated if their email begins
    with gen_sample_student_. For these students, we generate one new answer
    that receives full credit with probability CORRECT_PROB. Otherwise, we
    generate the answer -, which we assume to be incorrect.
    """

    # TODO(tujohnson): We may want to have varying probabilities for different
    # students.
    CORRECT_PROB = 0.5
    SAMPLE_SCORES_PATH = 'generate-scores'

    def post(self):
        # Sort questions into a dictionary based on their unit number
        questions_by_usage_id = event_transforms.get_questions_by_usage_id(
            self.app_context)

        sorted_questions_by_unit = self._rearrange_dict_by_field(
            questions_by_usage_id, 'unit')

        # Only use Students we generated.
        students = common_utils.iter_all(models.Student.all().filter(
            'email >', 'gen_sample_student_').filter(
                'email <', 'gen_sample_student`'))
        source = 'submit-assessment'

        for student in students:
            user = users.User(email=student.email, _user_id=student.user_id)
            assessment_data = self._generate_answers(student,
                                                    sorted_questions_by_unit)
            for data in assessment_data:
                EventEntity.record(source, user, transforms.dumps({
                    'values': data, 'location': 'AnswerHandler'}))

        self.redirect(self.request.referer)

    # Returns a list of answers for all assessments, in the required data format
    def _generate_answers(self, student, sorted_questions_by_unit):
        course = self.get_course()
        answers = []
        for unit in course.get_units():
            if (unit.is_assessment() and
                unit.unit_id in sorted_questions_by_unit):
                answers.append(self._generate_answers_one_assessment(
                    student, unit, sorted_questions_by_unit[unit.unit_id]))
        return answers

    def _generate_answers_one_assessment(self, student, assessment, questions):
        answersEntity = assessment.workflow.get_grader()
        answer = {}

        # Generate the correct answer with the defined constant probability
        # Otherwise leave the answer blank so that it will be marked incorrect
        for question_id in questions:
            rand_val = random.random()
            if rand_val < self.CORRECT_PROB:
                answer[question_id] = {'response':
                    questions[question_id]['graders'][0]['response']}
            else:
                answer[question_id] = {'response': '-'}

        answer['answers'] = {}
        for question_id in questions:
            answer['answers'][question_id] = answer[question_id]['response']

        answer['quids'] = {}
        for question_id in questions:
            answer['quids'][question_id] = questions[question_id]['id']

        answer['totalWeight'] = sum([questions[question_id]['weight']
                                        for question_id in questions])
        answer['containedTypes'] = {}
        for question_id in questions:
            answer['containedTypes'][question_id] = 'SaQuestion'

        answer['individualScores'] = {}
        for question_id in questions:
            if questions[question_id]['graders'][0]['response'] == \
                answer[question_id]['response']:
                answer['individualScores'][question_id] = 1
            else:
                answer['individualScores'][question_id] = 0

        answer['rawScore'] = sum([answer['individualScores'][question_id]
                                  for question_id in questions])
        answer['percentScore'] = answer['rawScore'] / answer['totalWeight']
        answer['percentScore'] = int(answer['percentScore'] * 100)
        answer['version'] = '1.5'
        return answer

    def _rearrange_dict_by_field(self, old_dict, sorted_field):
        """Rearranges and filters a dictionary of questions.

        Takes a dictionary of entries of the form
        {id1 : { 'val1': _, 'val2': _ }, id2 : { 'val1': _, 'val2': _ }, ...}
        and rearranges it so that items that match for the chosen field are
        placed.

        When we arrange by unit number, the output will be:
        { <unit_num_1> : <dictionary of questions from unit_num_1>,
          <unit_num_2> : <dictionary of questions from unit_num_2>, ...}
        We also include only the questions whose text begins with the correct
        prefix marking it as an automatically generated questions.
        """

        # First we need to get the set of ID's for automatically generated
        # questions, and their graders.
        question_entities = common_utils.iter_all(models.QuestionEntity.all())
        grader_dict = {}
        auto_generated_ids = set()
        for question_entity in question_entities:
            question_data = transforms.loads(question_entity.data)
            question_id = str(question_entity.key().id())
            text = question_data['question']
            if text.startswith(GenerateSampleQuizHandler.QUESTION_PREFIX):
                auto_generated_ids.add(question_id)
                grader_dict[question_id] = question_data['graders']

        sorted_dict = {}
        for instance_id in old_dict:
            old_entry = old_dict[instance_id]
            question_id = old_entry['id']
            if question_id in auto_generated_ids:
                sort_val = old_entry[sorted_field]
                if sort_val in sorted_dict:
                    sorted_dict[sort_val][instance_id] = old_dict[instance_id]
                else:
                    sorted_dict[sort_val] = {instance_id:
                                             old_dict[instance_id]}
                grader = grader_dict[question_id]
                sorted_dict[sort_val][instance_id]['graders'] = grader

        return sorted_dict


custom_module = None

def register_module():
    """Registers this module in the registry."""

    def on_module_enabled():
        register_analytic()

    global_routes = []
    namespaced_routes = [
        ('/' + GenerateSampleQuizHandler.SAMPLE_QUIZ_PATH,
         GenerateSampleQuizHandler),
        ('/' + GenerateSampleStudentsHandler.SAMPLE_STUDENTS_PATH,
         GenerateSampleStudentsHandler),
        ('/' + GenerateSampleScoresHandler.SAMPLE_SCORES_PATH,
         GenerateSampleScoresHandler)]

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        MODULE_TITLE,
        'Generate sample data',
        global_routes,
        namespaced_routes,
        notify_module_enabled=on_module_enabled)
    return custom_module
