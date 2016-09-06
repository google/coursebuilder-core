describe('Student Skills UI', function() {
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
        'nodes': $.extend(true, [], $('div.graph-container').data('nodes')),
        'links': $.extend(true, [], $('div.graph-container').data('links'))
      }
    }
  });

  describe('Graph', function() {
    var checkCenterPos = function(xShift, yShift, scale) {
      // Our nodes are hard-coded in fixture.html

      // Get graph size. The format for style is
      // 'height: <height>px; width: <width>px
      var styleStr = $('.graph-container').attr('style');
      partsOfStr = styleStr.split(';');
      var heightStr = partsOfStr[0].slice(8);
      var widthStr = partsOfStr[1].slice(7);
      var height = parseFloat(heightStr);
      var width = parseFloat(widthStr);

      // Get the actual shifts of the full graph, and for the individual nodes.
      // The format for translate is 'translate(<x_value>,<y_value>)'
      // The graph also has a scaling factor
      var translateGraphStr = $('g').attr('transform');
      var translateGraph = parseFloats(translateGraphStr);
      var translateAStr = $('.node.a').attr('transform');
      var translateBStr = $('.node.b').attr('transform');
      var translateA = parseFloats(translateAStr);
      var translateB = parseFloats(translateBStr);
      var scaleStr = $('g').attr('transform');

      // Take the shift for the full graph, and add the average of the shifts
      // for each node, multiplied by the scaling factor
      var scale = translateGraph[2];
      var xCenter = translateGraph[0] + scale*(translateA[0] + translateB[0])/2;
      var yCenter = translateGraph[1] + scale*(translateA[1] + translateB[1])/2;

      // Find the expected center, and compare to the actual center
      var xExpected = width/2 + xShift;
      var yExpected = height/2 + yShift;

      var xError = Math.abs(xCenter - xExpected)/width;
      var yError = Math.abs(yCenter - yExpected)/height;

      expect(xError).toBeCloseTo(0);
      expect(yError).toBeCloseTo(0);
    }

    var parseFloats = function(str) {
      var regex = /[+-]?\d+(\.\d+)?/g;
      var floats = str.match(regex).map(function(v) { return parseFloat(v); });
      return floats;
    }

    var renderTest = function(xShift, yShift, scale) {
      data = {
        'directed': true,
        'multigraph': false,
        'graph': [],
        'nodes': $('div.graph-container').data('nodes'),
        'links': $('div.graph-container').data('links')
      };
      window.GcbStudentSkillsUiModule.setupGraph(data, xShift, yShift, scale);
      checkCenterPos(xShift, yShift, scale);
    }

    it('can be shifted right', function() {
      renderTest(200, 0, 1);
    });

    it('can be shifted up', function() {
      renderTest(0, -100, 1);
    });

    it('can be scaled', function() {
      renderTest(0, 0, 2);
    });

    it('can be shifted and scaled', function() {
      renderTest(-200, 200, 0.5);
    });
  });

  describe('Panel', function() {
    beforeEach(function() {
      data = {
        'directed': true,
        'multigraph': false,
        'graph': [],
        'nodes': $('div.graph-container').data('nodes'),
        'links': $('div.graph-container').data('links')
      };

      window.GcbStudentSkillsUiModule.setupGraph(data, 0, 0, 1);
    });

    var checkPanelHtml = function(htmlString) {
      text = $('.panel-links')[0].textContent.trim();
      expect(text).toBe(htmlString);
    };

    it('can have text added and changed', function() {
      // Check that panel is initially empty
      checkPanelHtml('');

      // Click on node --> info should be added to panel
      $('.node.a').trigger('click');
      checkPanelHtml('Selected node: a');

      // Click on new node --> panel info should be updated
      $('.node.b').trigger('click');
      checkPanelHtml('Selected node: b');

      // TODO(tujohnson): Click on background, check that panel is empty
    });
  });
});
