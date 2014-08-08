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

describe('asset table sorting', function() {
  beforeEach(function() {
    jasmine.getFixtures().fixturesPath = 'base/';
    loadFixtures('tests/unit/javascript_tests/modules_dashboard/' +
      'assets_table_fixture.html');
  });
  it('sorts the first column in ascending order', function() {
    var column_header = $('#x');
    sortTable(column_header);
    expect(column_header.hasClass("sort-asc")).toBe(true);
    expect($('#b').index()).toBe(0);
    expect($('#c').index()).toBe(1);
    expect($('#a').index()).toBe(2);
  });
  it('sorts the first column in descending order', function() {
    var column_header = $('#x');
    sortTable(column_header);
    sortTable(column_header);
    expect(column_header.hasClass("sort-desc")).toBe(true);
    expect($('#b').index()).toBe(2);
    expect($('#c').index()).toBe(1);
    expect($('#a').index()).toBe(0);
  });
  it('sorts the second column in ascending order', function() {
    var column_header = $('#y');
    sortTable(column_header);
    expect(column_header.hasClass("sort-asc")).toBe(true);
    expect($('#c').index()).toBe(0);
    expect($('#a').index()).toBe(1);
    expect($('#b').index()).toBe(2);
  });
  it('sorts the second column in descending order', function() {
    var column_header = $('#y');
    sortTable(column_header);
    sortTable(column_header);
    expect(column_header.hasClass("sort-desc")).toBe(true);
    expect($('#c').index()).toBe(2);
    expect($('#a').index()).toBe(1);
    expect($('#b').index()).toBe(0);
  });
  it('sorts the timestamp column in descending order', function() {
    var column_header = $('#timestamped');
    sortTable(column_header);
    sortTable(column_header);
    expect(column_header.hasClass("sort-desc")).toBe(true);
    expect($('#a').index()).toBe(2);
    expect($('#c').index()).toBe(1);
    expect($('#b').index()).toBe(0);
  });
});

describe('draft status toggling', function() {
  beforeEach(function() {
    cbShowAlert = jasmine.createSpy("cbShowAlert");
    cbShowMsg = jasmine.createSpy("cbShowMsg");
    cbHideMsg = jasmine.createSpy("cbHideMsg");
  });
  it('simulates a toggle from public to draft', function() {
    var padlock = $("<div class='icon icon-unlocked'>");
    setDraftStatusCallback(
      '{"status": 200, "payload":"{\\"is_draft\\":true}"}', padlock);
    expect(padlock.hasClass("icon-unlocked")).toBe(false);
    expect(padlock.hasClass("icon-locked")).toBe(true);
    expect(cbShowMsg).toHaveBeenCalled();
  });
  it('simulates a toggle from draft to public', function() {
    var padlock = $("<div class='icon icon-locked'>")
    setDraftStatusCallback(
      '{"status": 200, "payload":"{\\"is_draft\\":false}"}', padlock);
    expect(padlock.hasClass("icon-locked")).toBe(false);
    expect(padlock.hasClass("icon-unlocked")).toBe(true);
    expect(cbShowMsg).toHaveBeenCalled();
  });
  it('simulates an access denied', function() {
    var padlock = $("<div class='icon icon-locked'>")
    setDraftStatusCallback('{"status": 401}', padlock);
    expect(padlock.hasClass("icon-locked")).toBe(true);
    expect(cbShowAlert).toHaveBeenCalled();
  });
});