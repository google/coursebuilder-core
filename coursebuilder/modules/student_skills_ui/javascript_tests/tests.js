describe('Student Skills UI', function() {
  ASYNC_CALL_TIMEOUT_MS = 20000;
  var originalTimeout;

  beforeEach(function() {
    jasmine.getFixtures().fixturesPath = 'base/';
    loadFixtures('modules/student_skills_ui/javascript_tests/fixture.html');

    // Copied from the script in templates/course_map.html
    window.getGraphData = function() {
      return {
        'directed': true,
        'multigraph': false,
        'graph': [],
        'nodes': $.extend(true, [], $('div.graph').data('nodes')),
        'links': $.extend(true, [], $('div.graph').data('links'))
      }
    }

    // D3 can take a while to render, so we increase the timeout
    originalTimeout = jasmine.DEFAULT_TIMEOUT_INTERVAL;
    jasmine.DEFAULT_TIMEOUT_INTERVAL = ASYNC_CALL_TIMEOUT_MS;
  });

  afterEach(function() {
    jasmine.DEFAULT_TIMEOUT_INTERVAL = originalTimeout;
  });

  describe('Graph', function() {

    allowedError = 0.05;

    var checkCenterPos = function(xShift, yShift, scale) {
      // Our nodes are hard-coded in fixture.html
      var xA = $('g.node-a').attr("cx");
      var yA = $('g.node-a').attr("cy");
      var xB = $('g.node-b').attr("cx");
      var yB = $('g.node-b').attr("cy");
      var xCenter = (xA + xB)/2;
      var yCenter = (yA + yB)/2;

      // Get graph size, with margins copied from viz.js
      var width = window.innerWidth - 64;
      var height = window.innerHeight - 200;

      // Find the expected center, and compare to the actual center
      var xExpected = width/2 + xShift;
      var yExpected = height/2 + yShift;

      var xError = Math.abs(xCenter - xExpected)/width;
      var yError = Math.abs(yCenter - yExpected)/height;

      expect(xError < allowedError);
      expect(yError < allowedError);
    }

    var renderTest = function(xShift, yShift, scale, done) {
      var xShift = 200;
      var yShift = 0;
      var scale = 1;
      window.GcbStudentSkillsUiModule.setupGraph(xShift, yShift, scale);

      $('div.graph').on('graph-loaded', function() {
        checkCenterPos(xShift, yShift, scale);
        done();
      });
    }

    it('can be shifted right', function(done) {
      renderTest(200, 0, 1, done);
    });

    it('can be shifted up', function(done) {
      renderTest(0, -100, 1, done);
    });

    it('can be scaled', function(done) {
      renderTest(0, 0, 2, done);
    });

    it('can be shifted and scaled', function(done) {
      renderTest(-200, 200, 0.5, done);
    });
  });
});
