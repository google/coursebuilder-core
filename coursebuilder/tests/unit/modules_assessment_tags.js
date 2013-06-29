describe('assessment tags', function() {
  beforeEach(function() {
    jasmine.getFixtures().fixturesPath = 'base/';
    loadFixtures('tests/unit/modules_assessment_tags.html');
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
        var questionData = {'mc-0': [
            {score: '1', feedback: 'yes'},
            {score: '0', feedback: 'no'}]};
        var mc = new McQuestion(el, questionData);
        var grade = mc.grade();
        expect(grade.score).toBe(1);
        expect(grade.feedback[0].outerHTML).toBe('<ul><li>yes</li></ul>');
      });
      it('can omit feedback if none provided', function() {
        var questionData = {'mc-0': [{score: '1'}, {score: '0'}]};
        var mc = new McQuestion(el, questionData);
        var grade = mc.grade();
        expect(grade.score).toBe(1);
        expect(grade.feedback[0].outerHTML).toBe('<ul></ul>');
      });
      it('doesn\'t give negative scores', function() {
        var questionData = {'mc-0': [{score: '-1'}, {score: '-5'}]};
        var mc = new McQuestion(el, questionData);
        var grade = mc.grade();
        expect(grade.score).toBe(0);
      });
      it('doesn\'t give negative scores', function() {
        var questionData = {'mc-0': [{score: '-1'}, {score: '-5'}]};
        var mc = new McQuestion(el, questionData);
        var grade = mc.grade();
        expect(grade.score).toBe(0);
      });
      it('doesn\'t give scores over 1', function() {
        var questionData = {'mc-0': [{score: '5'}, {score: '0'}]};
        var mc = new McQuestion(el, questionData);
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
        var questionData = {'mc-1': [
            {score: '0.2', feedback: 'good'},
            {score: '0.7', feedback: 'better'},
            {score: '0.1', feedback: 'bad'}]};
        var mc = new McQuestion(el, questionData);
        var grade = mc.grade();
        expect(grade.score).toBe(0.9);
        expect(grade.feedback[0].outerHTML)
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
      var sa = new SaQuestion(el, questionData);
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
});