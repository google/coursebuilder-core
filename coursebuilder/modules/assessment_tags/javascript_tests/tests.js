describe('assessment tags', function() {
  var LOGGING_LOCATION = 'http://localhost:8080/unit?unit=1&lesson=2';
  var MESSAGES = {
    correct: 'Correct.',
    incorrect: 'Incorrect.',
    partiallyCorrect: 'Partially Correct.',
    correctAnswer: 'Yes, the answer is correct.',
    incorrectAnswer: 'No, the answer is incorrect.',
    partiallyCorrectAnswer: 'The answer is partially correct.',
    yourScoreIs: 'Your score is: ',
    correctAnswerHeading: 'Correct Answer:',
    targetedFeedbackHeading: 'Targeted Feedback:',
    feedbackHeading: 'Feedback:'
  };
  /**
   * Extract the outerHTML value from the first element in a set of matched
   * elements (analogous to jQuery.html()).
   */
  function getOuterHTML(jqueryElementList) {
    return jqueryElementList[0].outerHTML;
  }
  beforeEach(function() {
    jasmine.getFixtures().fixturesPath = 'base/';
    loadFixtures(
        'modules/assessment_tags/javascript_tests/fixture.html');
  });
  describe('standard rounding function', function() {
    it('rounds to closest number with 2 decimal place precision', function() {
      expect(roundToTwoDecimalPlaces(3.14159265)).toBe(3.14);
      expect(roundToTwoDecimalPlaces(1.001)).toBe(1);
      expect(roundToTwoDecimalPlaces(1.009)).toBe(1.01);
      expect(roundToTwoDecimalPlaces(-1.001)).toBe(-1);
      expect(roundToTwoDecimalPlaces(-1.009)).toBe(-1.01);
      expect(roundToTwoDecimalPlaces(100000.001)).toBe(100000);
      expect(roundToTwoDecimalPlaces(100000.009)).toBe(100000.01);
      expect(roundToTwoDecimalPlaces(0.005)).toBe(0.01);
      expect(roundToTwoDecimalPlaces(0.0049999)).toBe(0);
    });
  });
  describe('base question methods', function() {
    var bq;
    beforeEach(function() {
      bq = new BaseQuestion($('#mc-0'), {}, MESSAGES, null);
      bq.data = {};
    });
    describe('the message about the score', function() {
      it('calls scores close to 1 correct', function() {
        var message = bq.getMessageAboutScore(0.991);
        expect(message.text()).toBe(MESSAGES.correctAnswer);
        expect(message).toHaveClass('correct');
      });
      it('calls scores between 0 and 1 partially correct', function() {
        var message = bq.getMessageAboutScore(0.5);
        expect(message.text()).toBe(MESSAGES.partiallyCorrectAnswer);
        expect(message).toHaveClass('partially-correct');
      });
      it('calls scores close to 0 incorrect', function() {
        var message = bq.getMessageAboutScore(0.009);
        expect(message.text()).toBe(MESSAGES.incorrectAnswer);
        expect(message).toHaveClass('incorrect');
      });
    });
    describe('the weight', function() {
      it('reads a number from this.data.weight', function() {
        bq.data.weight = 14;
        expect(bq.getWeight()).toBe(14);
      });
      it('defaults to 1', function() {
        bq.data.weight = undefined;
        expect(bq.getWeight()).toBe(1);
        bq.data.weight = null;
        expect(bq.getWeight()).toBe(1);
        bq.data.weight = 'mongoose';
        expect(bq.getWeight()).toBe(1);
      });
    });
  });
  describe('multiple choice questions', function() {
    describe('single selection', function() {
      var el;
      beforeEach(function() {
        el = $('#mc-0');
        // Select the first out of two possible choices
        $('#mc-0-0').prop('checked', true);
      });
      it('can grade the question', function() {
        var questionData = {'mc-0': {
          choices: [
            {score: '1', feedback: 'yes'},
            {score: '0', feedback: 'no'}],
            defaultFeedback: 'this is feedback'}};
        var mc = new McQuestion(el, questionData, MESSAGES);
        var grade = mc.grade();
        expect(grade.score).toBe(1);
        expect(getOuterHTML(grade.feedback)).toBe(
            '<div>' +
            '<h3 class="feedback-header">Targeted Feedback:</h3>' +
            '<ul><li>yes</li></ul>' +
            '<h3 class="feedback-header">Feedback:</h3>' +
            '<div>this is feedback</div>' +
            '</div>');
      });
      it('can omit feedback if none provided', function() {
        var questionData = {'mc-0': {choices: [{score: '1'}, {score: '0'}]}};
        var mc = new McQuestion(el, questionData, MESSAGES);
        var grade = mc.grade();
        expect(grade.score).toBe(1);
        expect(getOuterHTML(grade.feedback)).toBe('<div></div>');
      });
      it('can give HTML formatted feedback', function() {
        var questionData = {'mc-0': {choices: [
            {score: '1', feedback: '<b>yes</b>'},
            {score: '0', feedback: '<u>no</u>'}]}};
        var mc = new McQuestion(el, questionData, MESSAGES);
        var grade = mc.grade();
        expect(grade.score).toBe(1);
        expect(getOuterHTML(grade.feedback)).toBe(
            '<div>' +
            '<h3 class="feedback-header">Targeted Feedback:</h3>' +
            '<ul><li><b>yes</b></li></ul></div>');
      });
      it('can show the correct answer', function() {
        // Test a question with showAnswerWhenIncorrect = false
        var questionData = {
          'mc-0': {
            showAnswerWhenIncorrect: false,
            choices: [
              {text: 'correct answer', score: '1', feedback: '<b>yes</b>'},
              {text: 'incorrect answer', score: '0', feedback: '<u>no</u>'}]}};
        var mc = new McQuestion(el, questionData, MESSAGES);

        // Correct answer
        $('#mc-0-0').prop('checked', true);
        var grade = mc.grade();
        expect(getOuterHTML(grade.feedback)).toBe(
            '<div>' +
            '<h3 class="feedback-header">Targeted Feedback:</h3>' +
            '<ul><li><b>yes</b></li></ul></div>');

        // Incorrect answer
        $('#mc-0-1').prop('checked', true);
        var grade = mc.grade();
        expect(getOuterHTML(grade.feedback)).toBe(
            '<div>' +
            '<h3 class="feedback-header">Targeted Feedback:</h3>' +
            '<ul><li><u>no</u></li></ul></div>');

        // Then test a question with showAnswerWhenIncorrect = true
        questionData['mc-0'].showAnswerWhenIncorrect = true;
        mc = new McQuestion(el, questionData, MESSAGES);

        // Correct answer
        $('#mc-0-0').prop('checked', true);
        var grade = mc.grade();
        expect(getOuterHTML(grade.feedback)).toBe(
            '<div>' +
            '<h3 class="feedback-header">' +
            '<span class="correct">Correct.</span>' +
            '</h3>' +
            '<h3 class="feedback-header">Targeted Feedback:</h3>' +
            '<ul><li><b>yes</b></li></ul></div>');

        // Incorrect answer - with correct answer shown
        $('#mc-0-1').prop('checked', true);
        var grade = mc.grade();
        expect(getOuterHTML(grade.feedback)).toBe(
            '<div>' +
            '<h3 class="feedback-header">' +
            '<span class="incorrect">Incorrect.</span>' +
            '<span class="correct-answer-heading">Correct Answer:</span>' +
            '</h3>' +
            '<ul class="correct-choices"><li>correct answer</li></ul>' +
            '<h3 class="feedback-header">Targeted Feedback:</h3>' +
            '<ul><li><u>no</u></li></ul></div>');
      });

      describe('permutation of choices', function() {
        var mockRandomCallCount;
        var mockRandomData;
        var mockRandom = function() {
          return mockRandomData[mockRandomCallCount++ % mockRandomData.length];
        };

        beforeEach(function() {
          mockRandomCallCount = 0;
          mockRandomData = [0.9];
        });
        it('makes identity permutations', function() {
          expect(getIdentityPermutation(1)).toEqual([0]);
          expect(getIdentityPermutation(2)).toEqual([0, 1]);
          expect(getIdentityPermutation(3)).toEqual([0, 1, 2]);
          expect(getIdentityPermutation(4)).toEqual([0, 1, 2, 3]);
          expect(getIdentityPermutation(5)).toEqual([0, 1, 2, 3, 4]);
        });
        it('makes random permutations', function() {
          function frac(i, n) {
            return (i + 0.5) / n;
          }
          // Trivial permutation
          expect(getRandomPermutation(1, mockRandom)).toEqual([0]);
          // Always choose the top
          mockRandomData = [0.9, 0.9, 0.9, 0.9];
          mockRandomCallCount = 0;
          expect(getRandomPermutation(4, mockRandom)).toEqual([3, 2, 1, 0]);
          // Always choose the bottom
          mockRandomData = [0, 0, 0, 0];
          mockRandomCallCount = 0;
          expect(getRandomPermutation(4, mockRandom)).toEqual([0, 1, 2, 3]);
          // Mix of top, middle, and bottom
          mockRandomData = [
              frac(3, 4) /* the top of [0,1,2,3], ie 3 */,
              frac(1, 3) /* the middle of [0,1,2], ie 1 */,
              frac(0, 2) /* the bottom of [0, 2] ie 0 */,
              frac(0, 1)] /* whatever's left ie 2 */;
          mockRandomCallCount = 0;
          expect(getRandomPermutation(4, mockRandom)).toEqual([3, 1, 0, 2]);
        });
        it('permutes the choices when flag set', function() {
          var questionData = {
            'mc-0': {
              permuteChoices: true,
              choices: [{score: '1'}, {score: '0'}]
          }};
          var mc = new McQuestion(el, questionData, MESSAGES, null, null,
              mockRandom);
          var displayedIndexes = mc.el.find('div.qt-choices > div > input')
              .map(function() { return $(this).data('index') }).get();
          expect(displayedIndexes).toEqual([1, 0]);
        });
        it('does not permute the choices when flag unset', function() {
          var questionData = {
            'mc-0': {
              permuteChoices: false,
              choices: [{score: '1'}, {score: '0'}]
          }};
          var mc = new McQuestion(el, questionData, MESSAGES, null, null,
              mockRandom);
          var displayedIndexes = mc.el.find('div.qt-choices > div > input')
              .map(function() { return $(this).data('index') }).get();
          expect(displayedIndexes).toEqual([0, 1]);
        });
        it('returns the selected choice and the permutation', function() {
          var questionData = {
            'mc-0': {
              permuteChoices: true,
              choices: [{score: '1'}, {score: '0'}]
          }};
          var mc = new McQuestion(el, questionData, MESSAGES, null, null,
              mockRandom);

          // Select the first radio button and expect the second choice to be
          // recorded (together with the flip permutation)
          mc.choicesDivs.find('> input').eq(0).prop('checked', true);
          expect(mc.getStudentAnswer())
              .toEqual({responses: [false, true], permutation: [1, 0]});
        });
        it('can be set to display the original permutation', function() {
          var questionData = {
            'mc-0': {
              permuteChoices: true,
              choices: [{score: '1'}, {score: '0'}]
          }};
          var mc = new McQuestion(el, questionData, MESSAGES, null, null,
              mockRandom);

          var answer = {responses: [false, true], permutation: [1, 0]};
          mc.setStudentAnswer(answer);
          var firstInput = mc.el.find('div.qt-choices input').eq(0);
          expect(firstInput.data('index')).toEqual(1);
          expect(firstInput.prop('checked')).toEqual(true);
          // also confirm round trip
          expect(mc.getStudentAnswer()).toEqual(answer);
        });
        it('displays the original permutation (when mode unset)', function() {
          var questionData = {
            'mc-0': {
              permuteChoices: false, // set mode to "no permutations"
              choices: [{score: '1'}, {score: '0'}]
          }};
          var mc = new McQuestion(el, questionData, MESSAGES, null, null,
              mockRandom);

          // provide an answer with a permutation and confirm the question is
          // coerced to accept it and display it correctly
          var answer = {responses: [false, true], permutation: [1, 0]};
          mc.setStudentAnswer(answer);
          var firstInput = mc.el.find('div.qt-choices input').eq(0);
          expect(firstInput.data('index')).toEqual(1);
          expect(firstInput.prop('checked')).toEqual(true);
          // also confirm round trip
          expect(mc.getStudentAnswer()).toEqual(answer);
        });
        it('can convert an unpermuted answer to a permuted one', function() {
          var questionData = {
            'mc-0': {
              permuteChoices: true, // mode expects permutations
              choices: [{score: '1'}, {score: '0'}]
          }};
          var mc = new McQuestion(el, questionData, MESSAGES, null, null,
              mockRandom);

          // provide an answer which came from an unpermuted version of the
          // question
          var answer = [true, false];
          mc.setStudentAnswer(answer);
          var firstInput = mc.el.find('div.qt-choices input').eq(0);
          expect(firstInput.data('index')).toEqual(0);
          expect(firstInput.prop('checked')).toEqual(true);
          // also confirm promoted to response plus trivial permutation
          expect(mc.getStudentAnswer())
              .toEqual({responses: [true, false], permutation: [0, 1]});
        });
      });
      it('doesn\'t give negative scores', function() {
        var questionData = {'mc-0': {choices: [{score: '-1'}, {score: '-5'}]}};
        var mc = new McQuestion(el, questionData, MESSAGES);
        var grade = mc.grade();
        expect(grade.score).toBe(0);
      });
      it('doesn\'t give scores over 1', function() {
        var questionData = {'mc-0': {choices: [{score: '5'}, {score: '0'}]}};
        var mc = new McQuestion(el, questionData, MESSAGES);
        var grade = mc.grade();
        expect(grade.score).toBe(1);
      });
      it('sends event logging', function() {
        var auditDict;
        var eventPayloads = JSON.parse(
            readFixtures('tests/unit/common/event_payloads.json'));
        var questionData = {
          'mc-0': {
            quid: 'mc-0-quid',
            choices: [
              {score: '1', feedback: 'yes'},
              {score: '0', feedback: 'no'}]}};
        var mc = new McQuestion(el, questionData, MESSAGES, function(arg) {
          auditDict = arg;
          auditDict.location = LOGGING_LOCATION;
        });
        mc.onCheckAnswer();
        expect(auditDict).toEqual(eventPayloads.multiple_choice_15.event_data);
      });
    });
    describe('multiple selection', function() {
      var SAMPLE_QUESTION_DATA = {
        'mc-1': {
          choices: [
            {score: '0.2', feedback: 'good'},
            {score: '0.7', feedback: 'better'},
            {score: '0.1', feedback: 'bad'}
          ]
        }
      };
      var el;
      function expectValues(prop, values) {
        expect($('#mc-1-0').prop(prop)).toBe(values[0]);
        expect($('#mc-1-1').prop(prop)).toBe(values[1]);
        expect($('#mc-1-2').prop(prop)).toBe(values[2]);
      }
      beforeEach(function() {
        el = $('#mc-1');
        // Select the first two out of three possible choices
        $('#mc-1-0').prop('checked', true);
        $('#mc-1-1').prop('checked', true);
      });
      it('it aggregates the scores/feedback from selected choices', function() {
        var mc = new McQuestion(el, SAMPLE_QUESTION_DATA, MESSAGES);
        var grade = mc.grade();
        expect(grade.score).toBe(0.9);
        expect(getOuterHTML(grade.feedback)).toBe(
            '<div>' +
            '<h3 class="feedback-header">Targeted Feedback:</h3>' +
            '<ul><li>good</li><li>better</li></ul></div>');
      });
      it('can grade all-or-nothing', function() {
        function expectScoreForSelection(score, selection) {
          $('#mc-1 input[type="checkbox"]').each(function(index, checkbox) {
            checkbox.checked = selection[index];
          });
          expect(mc.grade().score).toBe(score);
        }
        var questionData = {
          'mc-1': {
            allOrNothingGrading: true,
            choices: [
              {text: 'correct answer 1', score: '0.5'},
              {text: 'correct answer 2', score: '0.5'},
              {text: 'incorrect answer 1', score: '-1.0'}]}};

        // Expect all-or-nothing grading
        var mc = new McQuestion(el, questionData, MESSAGES);
        expectScoreForSelection(0.0, [false, false, false]);
        expectScoreForSelection(0.0, [false, false, true]);
        expectScoreForSelection(0.0, [false, true, false]);
        expectScoreForSelection(0.0, [false, true, true]);
        expectScoreForSelection(0.0, [true, false, false]);
        expectScoreForSelection(0.0, [true, false, true]);
        expectScoreForSelection(1.0, [true, true, false]); /* correct */
        expectScoreForSelection(0.0, [true, true, true]);

        // Expect partial credit available
        questionData['mc-1'].allOrNothingGrading = false;
        mc = new McQuestion(el, questionData, MESSAGES);
        expectScoreForSelection(0.0, [false, false, false]);
        expectScoreForSelection(0.0, [false, false, true]);
        expectScoreForSelection(0.5, [false, true, false]); /* partial credit */
        expectScoreForSelection(0.0, [false, true, true]);
        expectScoreForSelection(0.5, [true, false, false]); /* partial credit */
        expectScoreForSelection(0.0, [true, false, true]);
        expectScoreForSelection(1.0, [true, true, false]); /* correct */
        expectScoreForSelection(0.0, [true, true, true]);
      });
      it('can show the correct answer(s)', function() {
        // Test a question with showAnswerWhenIncorrect = false
        var questionData = {
          'mc-1': {
            showAnswerWhenIncorrect: false,
            choices: [
              {text: 'correct answer 1', score: '0.5'},
              {text: 'correct answer 2', score: '0.5'},
              {text: 'incorrect answer', score: '0.0'}]}};
        var mc = new McQuestion(el, questionData, MESSAGES);

        // Correct answer
        $('#mc-1-0').prop('checked', true);
        $('#mc-1-1').prop('checked', true);
        $('#mc-1-2').prop('checked', false);
        var grade = mc.grade();
        expect(getOuterHTML(grade.feedback)).toBe('<div></div>');

        // Incorrect answer
        $('#mc-1-0').prop('checked', false);
        $('#mc-1-1').prop('checked', false);
        $('#mc-1-2').prop('checked', true);
        var grade = mc.grade();
        expect(getOuterHTML(grade.feedback)).toBe('<div></div>');

        // Then test a question with showAnswerWhenIncorrect = true
        questionData['mc-1'].showAnswerWhenIncorrect = true;
        mc = new McQuestion(el, questionData, MESSAGES);

        // Correct answer
        $('#mc-1-0').prop('checked', true);
        $('#mc-1-1').prop('checked', true);
        $('#mc-1-2').prop('checked', false);
        var grade = mc.grade();
        expect(getOuterHTML(grade.feedback)).toBe(
            '<div>' +
            '<h3 class="feedback-header">' +
            '<span class="correct">Correct.</span>' +
            '</h3>' +
            '</div>');

        // Partially correct answer - with correct answer shown
        $('#mc-1-0').prop('checked', true);
        $('#mc-1-1').prop('checked', false);
        $('#mc-1-2').prop('checked', false);
        var grade = mc.grade();
        expect(getOuterHTML(grade.feedback)).toBe(
            '<div>' +
            '<h3 class="feedback-header">' +
            '<span class="partially-correct">Partially Correct.</span>' +
            '<span class="correct-answer-heading">Correct Answer:</span>' +
            '</h3>' +
            '<ul class="correct-choices">' +
            '<li>correct answer 1</li><li>correct answer 2</li>' +
            '</ul>' +
            '</div>');

        // Incorrect answer - with correct answer shown
        $('#mc-1-0').prop('checked', false);
        $('#mc-1-1').prop('checked', false);
        $('#mc-1-2').prop('checked', true);
        var grade = mc.grade();
        expect(getOuterHTML(grade.feedback)).toBe(
            '<div>' +
            '<h3 class="feedback-header">' +
            '<span class="incorrect">Incorrect.</span>' +
            '<span class="correct-answer-heading">Correct Answer:</span>' +
            '</h3>' +
            '<ul class="correct-choices">' +
            '<li>correct answer 1</li><li>correct answer 2</li>' +
            '</ul>' +
            '</div>');

        // Partially correct answer is shown as incorrect if all-or-nothing
        questionData['mc-1'].allOrNothingGrading = true;
        mc = new McQuestion(el, questionData, MESSAGES);
        $('#mc-1-0').prop('checked', true);
        $('#mc-1-1').prop('checked', false);
        $('#mc-1-2').prop('checked', false);
        var grade = mc.grade();
        expect(getOuterHTML(grade.feedback)).toBe(
            '<div>' +
            '<h3 class="feedback-header">' +
            '<span class="incorrect">Incorrect.</span>' +
            '<span class="correct-answer-heading">Correct Answer:</span>' +
            '</h3>' +
            '<ul class="correct-choices">' +
            '<li>correct answer 1</li><li>correct answer 2</li>' +
            '</ul>' +
            '</div>');
      });
      it('serializes the student answer', function() {
        var mc = new McQuestion(el, SAMPLE_QUESTION_DATA, MESSAGES);
        expect(mc.getStudentAnswer()).toEqual([true, true, false]);
      });
      describe('restoring the student answer', function() {
        var mc;
        beforeEach(function() {
          mc = new McQuestion(el, SAMPLE_QUESTION_DATA, MESSAGES);
          $('#mc-1-0').prop('checked', false);
          $('#mc-1-1').prop('checked', false);
          $('#mc-1-2').prop('checked', false);
        });
        it('restores a valid answer', function() {
          mc.setStudentAnswer([false, true, true]);
          expectValues('checked', [false, true, true]);
        });
        it('silently passes a null or undefined', function() {
          mc.setStudentAnswer(null);
          expectValues('checked', [false, false, false]);
          mc.setStudentAnswer(undefined);
          expectValues('checked', [false, false, false]);
        });
      });
      it('can be made read-only', function() {
        var mc = new McQuestion(el, SAMPLE_QUESTION_DATA, MESSAGES);
        expectValues('disabled', [false, false, false]);
        mc.makeReadOnly();
        expectValues('disabled', [true, true, true]);
      });
    });
  });
  describe('short answer questions', function() {
    var el;
    beforeEach(function() {
      el = $('#sa-0');
      // Enter 'falafel' as the response
      el.find('> .qt-response > input, .qt-response > textarea').val('falafel');
    });
    function getQuestionData(matcher, response) {
      return {'sa-0': {
        quid: 'sa-0-quid',
        hint: 'it\s \'falafel\'',
        graders: [{
          matcher: matcher,
          response: response,
          score: '1.0',
          feedback: 'good'
        }]
      }};
    }
    function getQuestion(matcher, response) {
      return new SaQuestion(el, getQuestionData(matcher, response), MESSAGES);
    }
    function testMatcherWithResponse(matcher, response, expectedScore) {
      var sa = getQuestion(matcher, response);
      var grade = sa.grade();
      expect(grade.score).toBe(expectedScore);
    }
    describe('regular expression selection', function() {
      it('will accept the string repn of a JS regex with flags', function() {
        expect(SaQuestion.parseRegExp('/a.*c/i').toString()).toBe('/a.*c/i');
      });
      it('will accept the string repn of a JS regex without flags', function() {
        expect(SaQuestion.parseRegExp('/a.*c/').toString()).toBe('/a.*c/');
      });
      it('will accept a bare string as a regular expression', function() {
        expect(SaQuestion.parseRegExp('a.*c').toString()).toBe('/a.*c/');
      });
    });
    describe('case-insensitive grading', function() {
      it('makes case-insensitive matches', function() {
        testMatcherWithResponse('case_insensitive', 'FaLaFeL', 1);
      });
      it('rejects case-insensitive misses', function() {
        testMatcherWithResponse('case_insensitive', 'GaLaFeL', 0);
      });
    });
    describe('regex grading', function() {
      it('makes regex matches', function() {
        testMatcherWithResponse('regex', 'f[a-z]{5}l', 1);
      });
      it('makes regex matches with flags', function() {
        testMatcherWithResponse('regex', '/F[A-Z]{5}L/i', 1);
      });
      it('rejects regex misses', function() {
        testMatcherWithResponse('regex', 'G[a-z]{5}l', 0);
      });
    });
    describe('numeric grading', function() {
      it('matches numerically equivalent answers', function() {
        el.find('> .qt-response > input, .qt-response > textarea').val('3');
        testMatcherWithResponse('numeric', '3.00', 1);
      });
      it('rejects non-numeric answers', function() {
        el.find('> .qt-response > input, .qt-response > textarea')
            .val('falafel');
        testMatcherWithResponse('numeric', '3.00', 0);
      });
      it('rejects unequal numeric answers', function() {
        el.find('> .qt-response > input, .qt-response > textarea').val('3.01');
        testMatcherWithResponse('numeric', '3.00', 0);
      });
    });
    it('gives HTML feedback', function() {
      var questionData = getQuestionData('case_insensitive', 'falafel');
      questionData['sa-0'].graders[0].feedback = '<b>good</b>';
      var sa = new SaQuestion(el, questionData, MESSAGES);
      expect(getOuterHTML(sa.grade().feedback)).toBe('<div><b>good</b></div>');
    });
    it('serializes the student answer', function() {
      var sa = getQuestion('case insensitive', 'Falafel');
      expect(sa.getStudentAnswer()).toEqual({'response': 'falafel'});
    });
    describe('restoring the student answer', function() {
      var sa;
      beforeEach(function() {
        sa = getQuestion('case insensitive', 'Falafel');
      });
      it('restores a valid answer', function() {
        sa.setStudentAnswer({'response': 'foo bar'});
        expect(el.find('> .qt-response > input, .qt-response > textarea')
            .val()).toEqual('foo bar');
      });
      it('does nothing with a null, undefined, or invalid answer', function() {
        sa.setStudentAnswer(null);
        expect(el.find('> .qt-response > input, .qt-response > textarea')
            .val()).toEqual('falafel');
        sa.setStudentAnswer(undefined);
        expect(el.find('> .qt-response > input, .qt-response > textarea')
            .val()).toEqual('falafel');
        sa.setStudentAnswer({'wrong': 'format'});
        expect(el.find('> .qt-response > input, .qt-response > textarea')
            .val()).toEqual('falafel');
        sa.setStudentAnswer(['wrong', 'format']);
        expect(el.find('> .qt-response > input, .qt-response > textarea')
            .val()).toEqual('falafel');
      });
    });
    it('can be made read-only', function() {
      var sa = getQuestion('case insensitive', 'Falafel');
      expect(el.find('> .qt-response > input, .qt-response > textarea')
          .prop('disabled')).toBe(false);
      sa.makeReadOnly();
      expect(el.find('> .qt-response > input, .qt-response > textarea')
          .prop('disabled')).toBe(true);
    });
    it('sends event logging', function() {
      var auditDict;
      var eventPayloads = JSON.parse(
          readFixtures('tests/unit/common/event_payloads.json'));
      var questionData = getQuestionData('case_insensitive', 'FaLaFeL');
      var sa = new SaQuestion(el, questionData, MESSAGES, function(arg) {
        auditDict = arg;
        auditDict.location = LOGGING_LOCATION;
      });
      sa.onCheckAnswer();
      expect(auditDict).toEqual(eventPayloads.short_answer_15.event_data);
    });
  });
  describe('question group', function() {
    var auditDict, qg;
    beforeEach(function() {
      var el = $('#qg-0');
      var questionData = {
        'qg-0': {
          'qg-0-mc-0': {'weight': '10'},
          'qg-0-sa-0': {'weight': '15'},
        },
        'qg-0-mc-0': {
          quid: 'qg-0-mc-0-quid',
          choices: [
            {score: '1', feedback: 'yes'},
            {score: '0', feedback: 'no'}]},
        'qg-0-sa-0': {
          quid: 'qg-0-sa-0-quid',
          hint: 'it\s \'falafel\'',
          graders: [{
            matcher: 'case_insensitive',
            response: 'falafel',
            score: '1.0',
            feedback: 'good'
          }]
        }
      };
      var componentAudit = function(arg) {
        auditDict = arg;
        auditDict.location = LOGGING_LOCATION;
      }
      qg = new QuestionGroup(el, questionData, MESSAGES, componentAudit);
    });
    it('computes a weighted grade', function() {
      $('#qg-0-mc-0-0').prop('checked', false);
      $('#qg-0-sa-0 > .qt-response > input, .qt-response > textarea')
          .val('falafel');
      var grade = qg.grade();
      expect(grade.score).toBeCloseTo(0.6, 10);
    });
    it('rounds fractional grades only when recorded', function() {
      // Initialize the questions with weighting which gives a recurring
      // decimal. Check that the score not not rounded internally (i.e., calls
      // to grade() do not round) but is rounded when reporting to the event
      // stream.
      var el = $('#qg-0');
      var questionData = {
        'qg-0': {
          'qg-0-mc-0': {'weight': '1'},
          'qg-0-sa-0': {'weight': '5'},
        },
        'qg-0-mc-0': {choices: [
          {score: '1', feedback: 'yes'},
          {score: '0', feedback: 'no'}]},
        'qg-0-sa-0': {
          hint: 'it\s \'falafel\'',
          graders: [{
            matcher: 'case_insensitive',
            response: 'falafel',
            score: '1.0',
            feedback: 'good'
          }]
        }
      };
      var componentAudit = function(arg) {
        auditDict = arg;
        auditDict.location = LOGGING_LOCATION;
      }
      qg = new QuestionGroup(el, questionData, MESSAGES, componentAudit);

      $('#qg-0-mc-0-0').prop('checked', true);

      // Expect unrounded score
      expect(qg.grade().score).toBeCloseTo(1/6, 10);

      // Expect rounded score
      qg.onCheckAnswer();
      expect(auditDict.score).toBe(0.17);
    });
    it('gets the feedback from all the questions', function() {
      $('#qg-0-mc-0-0').prop('checked', true);
      $('#qg-0-sa-0 > .qt-response > input, .qt-response > textarea')
          .val('falafel');
      var grade = qg.grade();
      expect(getOuterHTML(grade.feedback[0])).toBe(
          '<div>' +
          '<h3 class="feedback-header">Targeted Feedback:</h3>' +
          '<ul><li>yes</li></ul></div>');
      expect(getOuterHTML(grade.feedback[1])).toBe('<div>good</div>');
    });
    it('computes the total points available', function() {
      expect(qg.getTotalPoints()).toBe(25);
    });
    it('sends event logging on check answer', function() {
      var eventPayloads = JSON.parse(
          readFixtures('tests/unit/common/event_payloads.json'));
      $('#qg-0-mc-0-0').prop('checked', true);
      $('#qg-0-sa-0 > .qt-response > input, .qt-response > textarea')
          .val('falafel');
      qg.onCheckAnswer();
      expect(auditDict).toEqual(eventPayloads.question_group_15.event_data);
    });
    it('sends event logging on grading scored lesson', function() {
      var eventPayloads = JSON.parse(
          readFixtures('tests/unit/common/event_payloads.json'));
      $('#qg-0-mc-0-0').prop('checked', true);
      $('#qg-0-sa-0 > .qt-response > input, .qt-response > textarea')
          .val('falafel');

      // Mock the global function gcbLessonAudit
      var lessonAuditDict;
      window.gcbLessonAudit = function(arg) {
        lessonAuditDict = arg;
        lessonAuditDict.location = LOGGING_LOCATION;
      };

      gradeScoredLesson([qg], MESSAGES);
      expect(lessonAuditDict)
          .toEqual(eventPayloads.scored_lesson_15_qg.event_data);
    });
    it('serializes the student answer', function() {
      $('#qg-0-mc-0-0').prop('checked', true);
      $('#qg-0-sa-0 > .qt-response > input, .qt-response > textarea')
          .val('falafel');
      expect(qg.getStudentAnswer()).toEqual({
        'qg-0-mc-0' : [ true, false ],
        'qg-0-sa-0' : { 'response' : 'falafel' }
      });
    });
    describe('restoring the student answer', function() {
      beforeEach(function() {
        $('#qg-0-mc-0-0').prop('checked', true);
        $('#qg-0-mc-0-1').prop('checked', false);
        $('#qg-0-sa-0 > .qt-response > input, .qt-response > textarea')
            .val('falafel')
      });
      function expectValue(mc1, mc2, text) {
        expect($('#qg-0-mc-0-0').prop('checked')).toBe(mc1);
        expect($('#qg-0-mc-0-1').prop('checked')).toBe(mc2);
        expect($('#qg-0-sa-0 > .qt-response > input, .qt-response > textarea')
            .val()).toBe(text);
      }
      it('restores a valid answer', function() {
        qg.setStudentAnswer({
          'qg-0-mc-0': [false, true],
          'qg-0-sa-0': {'response': 'foo bar'}
        });
        expectValue(false, true, 'foo bar');
      });
      it('does nothing with a null, undefined, or invalid answer', function() {
        qg.setStudentAnswer(null);
        expectValue(true, false, 'falafel');
        qg.setStudentAnswer(undefined);
        expectValue(true, false, 'falafel');
        qg.setStudentAnswer({'wrong': 'format'});
        expectValue(true, false, 'falafel');
        qg.setStudentAnswer(['wrong', 'format']);
        expectValue(true, false, 'falafel');
      });
      it('partially sets answers if the data is partially valid', function() {
        qg.setStudentAnswer({
          'qg-0-mc-0': [false, true],
          'qg-0-sa-0': 'aardvaark'
        });
        expectValue(false, true, 'falafel');
      });
    });
    it('can be made read-only', function() {
      function expectDisabled(mc1, mc2, text) {
        expect($('#qg-0-mc-0-0').prop('disabled')).toBe(mc1);
        expect($('#qg-0-mc-0-1').prop('disabled')).toBe(mc2);
        expect($('#qg-0-sa-0 > .qt-response > input, .qt-response > textarea')
               .prop('disabled')).toBe(text);
      }
      expectDisabled(false, false, false);
      qg.makeReadOnly();
      expectDisabled(true, true, true);
    });
    it('loads the questions in the order they appear on the page', function () {
      var el = $('#qg-1');
      var questionData0 = {choices: [
        {score: '1', feedback: 'yes'},
        {score: '0', feedback: 'no'}]};
      var questionData1 = {
        hint: 'it\s \'falafel\'',
        graders: [{
          matcher: 'case_insensitive',
          response: 'falafel',
          score: '1.0',
          feedback: 'good'
        }]
      };
      var questionData2 = {choices: [
        {score: '1', feedback: 'yes'},
        {score: '0', feedback: 'no'}]};
      var questionData = {
        'qg-1': {
          'qg-1-mc-0': {'weight': '10'},
          'qg-1-sa-0': {'weight': '15'},
          'qg-1-mc-1': {'weight': '20'},
        },
        'qg-1-mc-0': questionData0,
        'qg-1-sa-0': questionData1,
        'qg-1-mc-1': questionData2
      };
      var qg = new QuestionGroup(el, questionData, MESSAGES);
      expect(qg.questions[0] instanceof McQuestion).toBe(true);
      expect(qg.questions[1] instanceof SaQuestion).toBe(true);
      expect(qg.questions[2] instanceof McQuestion).toBe(true);
      expect(qg.questions[0].data).toBe(questionData0);
      expect(qg.questions[1].data).toBe(questionData1);
      expect(qg.questions[2].data).toBe(questionData2);
    });
  });

  function initTwoQuestions() {
    // Set up a multiple choice question
    var mcQuestionData = {
      'mc-0': {
        quid: 'mc-0-quid',
        choices: [
          {score: '1', feedback: 'yes'},
          {score: '0', feedback: 'no'}
        ]
      }
    };
    var mc = new McQuestion($('#mc-0'), mcQuestionData, MESSAGES);
    // Select the first out of two possible choices
    $('#mc-0-0').prop('checked', true);

    // Set up a short answer question
    var saQuestionData = {
      'sa-0': {
        quid: 'sa-0-quid',
        hint: 'it\'s \'falafel\'',
        graders: [
          {
            matcher: 'case_insensitive',
            response: 'FaLaFeL',
            score: '1.0',
            feedback: 'good'
          }
        ]
      }
    };
    var sa = new SaQuestion($('#sa-0'), saQuestionData, MESSAGES);
    // Enter 'falafel' as the response
    $('#sa-0 > .qt-response > input, .qt-response > textarea').val('falafel');

    return [mc, sa];
  }

  describe('scored lesson', function() {
    var auditDict, questions;

    beforeEach(function() {
      // Mock the global function gcbLessonAudit
      window.gcbLessonAudit = function(arg) {
        auditDict = arg;
        auditDict.location = LOGGING_LOCATION;
      };

      // Make a list of questions in the scored lesson
      questions = initTwoQuestions();
    });
    it('sends event logging', function() {
      var eventPayloads = JSON.parse(
        readFixtures('tests/unit/common/event_payloads.json'));
      gradeScoredLesson(questions, MESSAGES);
      expect(auditDict).toEqual(eventPayloads.scored_lesson_15.event_data);
    });
  });
  describe('graded assessment', function() {
    var questions, action, hiddenData;

    beforeEach(function() {
      // Mock the global function submitForm
      window.submitForm = function(_action, _hiddenData) {
        action = _action;
        hiddenData = _hiddenData;
      };

      // Make a list of questions in the scored lesson
      questions = initTwoQuestions();
    });
    it('prepares event logging data', function() {
      var eventPayloads = JSON.parse(
        readFixtures('tests/unit/common/event_payloads.json'));
      gradeAssessment(questions, '6', 'xsrf_tok');
      // Assemble the event payload in the same form as is done by
      // assessments.AnswerHandler.update_assessment_transaction.
      eventPayload = {
        'type': 'assessment-6',
        'values': JSON.parse(hiddenData.answers),
        'location': 'AnswerHandler'
      };
      expect(eventPayload).toEqual(eventPayloads.assessment_15.event_data);
    });
  });
});

describe('maybeMoveGradingButton', function() {
  beforeEach(function() {
    jasmine.getFixtures().fixturesPath = 'base/';
    loadFixtures(
        'modules/assessment_tags/javascript_tests/grading_button_fixture.html');
  });

  it('moves the button', function() {
    maybeMoveGradingButton();
    var children = $('.qt-assessment-button-bar-location > div');
    expect(children.length).toBe(2);
    expect($(children[0]).attr("id")).toBe("other_div");
    expect($(children[1]).attr("class")).toBe("qt-assessment-button-bar");
    expect($('#button_bar_parent > div').length).toBe(0);
  });

  it('does not move the button when there are multiple targets', function() {
    $('#parent').append(
        '<div class="qt-assessment-button-bar-location"></div>');
    var immediate_children = $('#parent > div');
    expect(immediate_children.length).toBe(2);
    maybeMoveGradingButton();
    expect($('.qt-assessment-button-bar').parent().attr("id"))
        .toBe("button_bar_parent");
  });

  it('does not move the button when there are no targets', function() {
    $('.qt-assessment-button-bar-location').removeClass();
    maybeMoveGradingButton();
    expect($('.qt-assessment-button-bar').parent().attr("id"))
        .toBe("button_bar_parent");
  });
});
