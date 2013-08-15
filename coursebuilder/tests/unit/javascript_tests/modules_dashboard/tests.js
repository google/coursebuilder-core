describe('normalize scores', function() {
  var oldY;

  function arrayEqual(a, b) {
    if (a.length != b.length) {
      return false;
    }
    for (var i = 0; i < a.length; i++) {
      if (a[i] !== b[i]) {
        return false;
      }
    }
    return true;
  }

  beforeEach(function() {
    if (window.Y) {
      oldY = Y;
    }
    Y = YUI();
    Y.use('node', 'array-extras');

    this.addMatchers({
      toBeArrayEqual: function(expected) {
        return arrayEqual(this.actual, expected);
      }
    });
  });

  afterEach(function() {
    if (oldY) {
      window.Y = oldY;
    }
  });

  it('normalizes single and multiple selection appropriately', function() {
    var scores = [1, 2, 3, 2, 1];
    var expectedForSingle = [0, 0, 1, 0, 0];
    var expectedForMultiple = [0.2, 0.2, 0.2, 0.2, 0.2];

    singleSelection = true;
    expect(normalizeScores(scores))
        .toBeArrayEqual(expectedForSingle);

    singleSelection = false;
    expect(normalizeScores(scores))
        .toBeArrayEqual(expectedForMultiple);

  });

  describe('single selection', function() {
    it('makes the largest element 1 and the rest zero', function() {
      var scores = [1, 2, 3, 2, 1];
      var expected = [0, 0, 1, 0, 0];
      expect(normalizeScoresForSingleSelectionModel(scores))
          .toBeArrayEqual(expected);
    });
    it('does nothing to an empty list', function() {
      var scores = [];
      var expected = [];
      expect(normalizeScoresForSingleSelectionModel(scores))
          .toBeArrayEqual(expected);
    });
    it('is idempotent', function() {
      var list = [
        [1, 2, 3, 4],
        [0, 0, 1, 2],
        [0, 0, 0, 0],
        [1, 0, 1, 1],
        [0, 1, -1, 3, 5, 0.11]
      ];
      for (var i = 0; i < list.length; i++) {
        var orig = list[i];
        var first = normalizeScoresForSingleSelectionModel(orig);
        var second = normalizeScoresForSingleSelectionModel(first);
        expect(first).toBeArrayEqual(second);
      }
    });
  });

  describe('multiple selection', function() {
    it('it splits score evenly between the positive entries', function() {
      var scores = [0, 1, 0, 1];
      var expected = [-1, 0.5, -1, 0.5];
      expect(normalizeScoresForMultipleSelectionModel(scores))
          .toBeArrayEqual(expected);
    });
    it('includes a fudge for score which don\'t split evenly', function() {
      var scores = [1, 1, 1];
      var expected = [0.33, 0.33, 0.34];
      expect(normalizeScoresForMultipleSelectionModel(scores))
          .toBeArrayEqual(expected);
    });
    it('is idempotent', function() {
      var list = [
        [1, 2, 3, 4],
        [0, 0, 1, 2],
        [0, 0, 0, 0],
        [1, 0, 1, 1],
        [0, 1, -1, 3, 5, 0.11]
      ];
      for (var i = 0; i < list.length; i++) {
        var orig = list[i];
        var first = normalizeScoresForMultipleSelectionModel(orig);
        var second = normalizeScoresForMultipleSelectionModel(first);
        expect(first).toBeArrayEqual(second);
      }
    });
  });
});