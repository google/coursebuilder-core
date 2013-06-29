describe('assessment tags', function() {
  var MESSAGES = {
    correctAnswer: 'Yes, the answer is correct.',
    incorrectAnswer: 'No, the answer is incorrect.',
    partiallyCorrectAnswer: 'The answer is partially correct.',
    yourScoreIs: 'Your score is: '
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
    loadFixtures('tests/unit/modules_assessment_tags.html');
  });
  describe('base question methods', function() {
    var bq;
    beforeEach(function() {
      bq = new BaseQuestion($('#mc-0'), {}, MESSAGES);
      bq.data = {};
    });
    describe('the message about the score', function() {
      it('calls scores close to 1 correct', function() {
        expect(bq.getMessageAboutScore(0.991)).toBe(MESSAGES.correctAnswer);
      });
      it('calls scores between 0 and 1 partially correct', function() {
        expect(bq.getMessageAboutScore(0.5))
            .toBe(MESSAGES.partiallyCorrectAnswer);
      });
      it('calls scores close to 0 incorrect', function() {
        expect(bq.getMessageAboutScore(0.009)).toBe(MESSAGES.incorrectAnswer);
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
        var questionData = {'mc-0': {choices: [
            {score: '1', feedback: 'yes'},
            {score: '0', feedback: 'no'}]}};
        var mc = new McQuestion(el, questionData, MESSAGES);
        var grade = mc.grade();
        expect(grade.score).toBe(1);
        expect(getOuterHTML(grade.feedback)).toBe('<ul><li>yes</li></ul>');
      });
      it('can omit feedback if none provided', function() {
        var questionData = {'mc-0': {choices: [{score: '1'}, {score: '0'}]}};
        var mc = new McQuestion(el, questionData, MESSAGES);
        var grade = mc.grade();
        expect(grade.score).toBe(1);
        expect(getOuterHTML(grade.feedback)).toBe('<ul></ul>');
      });
      it('doesn\'t give negative scores', function() {
        var questionData = {'mc-0': {choices: [{score: '-1'}, {score: '-5'}]}};
        var mc = new McQuestion(el, questionData, MESSAGES);
        var grade = mc.grade();
        expect(grade.score).toBe(0);
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
    });
    describe('multiple selection', function() {
      var el;
      beforeEach(function() {
        el = $('#mc-1');
        // Select the first two out of three possible choices
        $('#mc-1-0').prop('checked', true);
        $('#mc-1-1').prop('checked', true);
      });
      it('it aggregates the scores/feedback from selected choices', function() {
        var questionData = {'mc-1': {choices: [
            {score: '0.2', feedback: 'good'},
            {score: '0.7', feedback: 'better'},
            {score: '0.1', feedback: 'bad'}]}};
        var mc = new McQuestion(el, questionData, MESSAGES);
        var grade = mc.grade();
        expect(grade.score).toBe(0.9);
        expect(getOuterHTML(grade.feedback))
            .toBe('<ul><li>good</li><li>better</li></ul>');
      });
    });
  });
  describe('short answer questions', function() {
    var el;
    beforeEach(function() {
      el = $('#sa-0');
      // Enter 'falafel' as the response
      el.find('> .qt-response > input').val('falafel');
    });
    function testMatcherWithResponse(matcher, response, expectedScore) {
      var questionData = {'sa-0': {
        hint: 'it\s \'falafel\'',
        graders: [{
          matcher: matcher,
          response: response,
          score: '1.0',
          feedback: 'good'
        }]
      }};
      var sa = new SaQuestion(el, questionData, MESSAGES);
      var grade = sa.grade();
      expect(grade.score).toBe(expectedScore);
    }
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
      it('rejects regex misses', function() {
        testMatcherWithResponse('regex', 'G[a-z]{5}l', 0);
      });
    });
    describe('numeric grading', function() {
      it('matches numerically equivalent answers', function() {
        el.find('> .qt-response > input').val('3');
        testMatcherWithResponse('numeric', '3.00', 1);
      });
      it('rejects non-numeric answers', function() {
        el.find('> .qt-response > input').val('falafel');
        testMatcherWithResponse('numeric', '3.00', 0);
      });
      it('rejects unequal numeric answers', function() {
        el.find('> .qt-response > input').val('3.01');
        testMatcherWithResponse('numeric', '3.00', 0);
      });
    });
  });
  describe('question group', function() {
    var qg;
    beforeEach(function() {
      var el = $('#qg-0');
      var questionData = {
        'qg-0': {
          'qg-0-mc-0': {'weight': '10'},
          'qg-0-sa-0': {'weight': '15'},
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
      qg = new QuestionGroup(el, questionData, MESSAGES);
    });
    it('computes a weighted grade', function() {
      $('#qg-0-mc-0-0').prop('checked', true);
      $('#qg-0-sa-0 > .qt-response > input').val('falafel');
      var grade = qg.grade();
      expect(grade.score).toBe(25);
    });
    it('gets the feedback from all the questions', function() {
      $('#qg-0-mc-0-0').prop('checked', true);
      $('#qg-0-sa-0 > .qt-response > input').val('falafel');
      var grade = qg.grade();
      expect(getOuterHTML(grade.feedback[0])).toBe('<ul><li>yes</li></ul>');
      expect(getOuterHTML(grade.feedback[1])).toBe('<div>good</div>');
    });
    it('computes the total points available', function() {
      expect(qg.getTotalPoints()).toBe(25);
    });
  });
});
