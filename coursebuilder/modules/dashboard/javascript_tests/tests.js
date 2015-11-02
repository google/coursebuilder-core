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

    jasmine.addMatchers({
      toBeArrayEqual: function(util, customEqualityTesters) {
        return {
          compare: function(actual, expected) {
            return {
              pass: arrayEqual(actual, expected),
              message: 'Expected ' + actual + ' to equal ' + expected
            };
          }
        }
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
    loadFixtures(
        'modules/dashboard/javascript_tests/assets_table_fixture.html');
  });
  it('sorts the first column in ascending order', function() {
    var column_header = $('#x');
    sortTable(column_header, true);
    expect(column_header.hasClass("sort-asc")).toBe(true);
    expect($('#b').index()).toBe(0);
    expect($('#c').index()).toBe(1);
    expect($('#a').index()).toBe(2);
  });
  it('sorts the first column in descending order', function() {
    var column_header = $('#x');
    sortTable(column_header, false);
    expect(column_header.hasClass("sort-desc")).toBe(true);
    expect($('#b').index()).toBe(2);
    expect($('#c').index()).toBe(1);
    expect($('#a').index()).toBe(0);
  });
  it('sorts the second column in ascending order', function() {
    var column_header = $('#y');
    sortTableByClick.call(column_header);
    expect(column_header.hasClass("sort-asc")).toBe(true);
    expect($('#c').index()).toBe(0);
    expect($('#a').index()).toBe(1);
    expect($('#b').index()).toBe(2);
  });
  it('sorts the second column in descending order', function() {
    var column_header = $('#y');
    sortTableByClick.call(column_header);
    sortTableByClick.call(column_header);
    expect(column_header.hasClass("sort-desc")).toBe(true);
    expect($('#c').index()).toBe(2);
    expect($('#a').index()).toBe(1);
    expect($('#b').index()).toBe(0);
  });
  it('sorts the timestamp column in descending order', function() {
    var column_header = $('#timestamped');
    sortTable(column_header, false);
    expect(column_header.hasClass("sort-desc")).toBe(true);
    expect($('#a').index()).toBe(2);
    expect($('#c').index()).toBe(1);
    expect($('#b').index()).toBe(0);
  });
});

describe('question table filtering', function() {
  function verifySingleRow(table, expectedId) {
    var visibleRows = table.find("tr:visible");
    expect(visibleRows.size()).toBe(1);
    expect(visibleRows.attr("id")).toBe(expectedId);
  }
  beforeEach(function() {
    jasmine.getFixtures().fixturesPath = 'base/';
    loadFixtures('modules/dashboard/javascript_tests/filtering_fixture.html');
    setUpFiltering();
    this.form = $("#question-filter-popup form");
    this.descriptionField = this.form.find(".description");
    this.typeField = this.form.find(".type");
    this.unitField = this.form.find(".unit");
    this.lessonField = this.form.find(".lesson");
    this.groupField = this.form.find(".group");
    this.unusedField = this.form.find(".unused");
  });
  it('moves the popup into the question filter div', function() {
    expect(this.form.closest("#question-filter").size()).toBe(1);
  });
  it('initializes dropdowns using data-filter attribute',function() {
    var typeOptions = this.typeField.find("option");
    expect(typeOptions.size()).toBe(3);
    expect(typeOptions.eq(0).val()).toBe("");
    expect(typeOptions.eq(1).val()).toBe("0");
    expect(typeOptions.eq(2).val()).toBe("1");

    var unitOptions = this.unitField.find("option");
    expect(unitOptions.size()).toBe(4);
    expect(unitOptions.eq(0).val()).toBe("");
    expect(unitOptions.eq(1).val()).toBe("1");
    expect(unitOptions.eq(2).val()).toBe("4");
    expect(unitOptions.eq(3).val()).toBe("6");

    var lessonOptions = this.lessonField.find("option");
    expect(lessonOptions.size()).toBe(4);
    expect(lessonOptions.eq(0).val()).toBe("");
    expect(lessonOptions.eq(1).val()).toBe("2");
    expect(lessonOptions.eq(2).val()).toBe("3");
    expect(lessonOptions.eq(3).val()).toBe("5");

    var groupOptions = this.groupField.find("option");
    expect(groupOptions.size()).toBe(3);
    expect(groupOptions.eq(0).val()).toBe("");
    expect(groupOptions.eq(1).val()).toBe("1");
    expect(groupOptions.eq(2).val()).toBe("2");
  });
  it('adapts the lesson field to the selected unit', function() {
    this.unitField.val("1").trigger("change");
    var lessonOptions = this.lessonField.find("option");
    expect(lessonOptions.size()).toBe(3);
    expect(lessonOptions.eq(0).val()).toBe("");
    expect(lessonOptions.eq(1).val()).toBe("2");
    expect(lessonOptions.eq(2).val()).toBe("3");

    this.unitField.val("4").trigger("change");
    lessonOptions = this.lessonField.find("option");
    expect(lessonOptions.size()).toBe(2);
    expect(lessonOptions.eq(0).val()).toBe("");
    expect(lessonOptions.eq(1).val()).toBe("5");

    this.unitField.val("6").trigger("change");
    expect(this.lessonField.prop("disabled")).toBe(true);
    lessonOptions = this.lessonField.find("option");
    expect(lessonOptions.size()).toBe(1);
    expect(lessonOptions.eq(0).val()).toBe("");

    this.unitField.val("").trigger("change");
    expect(this.lessonField.prop("disabled")).toBe(false);
    expect(this.lessonField.find("option").size()).toBe(4);
    expect(this.lessonField.val()).toBe("");
  });
  it('unchecks the unused checkbox when a unit is selected', function() {
    this.unusedField.prop("checked", true);
    this.unitField.val("1").trigger("change");
    expect(this.unusedField.prop("checked")).toBe(false);
  });
  it('unchecks the unused checkbox when a lesson is selected', function() {
    this.unusedField.prop("checked", true);
    this.lessonField.val("2").trigger("change");
    expect(this.unusedField.prop("checked")).toBe(false);
  });
  it('resets the unit field when the unused checkbox is checked', function() {
    this.unitField.val("1");
    this.unusedField.prop("checked", true).trigger("change");
    expect(this.unitField.val()).toBe("");
  });
  it('resets the lesson field when the unused checkbox is checked', function() {
    this.unitField.val("1").trigger("change");
    this.lessonField.val("2");
    this.unusedField.prop("checked", true).trigger("change");
    expect(this.lessonField.prop("disabled")).toBe(false);
    expect(this.lessonField.find("option").size()).toBe(4);
    expect(this.lessonField.val()).toBe("");
  });
  it('filters the questions using the filter form data', function() {
    var resetButton = this.form.find(".reset");
    var table = $("#question-table");

    this.unitField.val("1");
    this.lessonField.val("2").trigger("change");
    verifySingleRow(table, "a");
    resetButton.trigger("click");

    this.groupField.val("2").trigger("change");
    verifySingleRow(table, "b");

    this.groupField.val("1");
    this.typeField.val("1").trigger("change");
    verifySingleRow(table, "c");
    resetButton.trigger("click");

    this.descriptionField.val("-x-").trigger("keyup");
    expect(table.find("tr:visible").size()).toBe(2);
    this.unitField.val("6").trigger("change");
    verifySingleRow(table, "d");
    resetButton.trigger("click");

    this.unusedField.prop("checked", true);
    this.typeField.val("0").trigger("change");
    verifySingleRow(table, "e");

    this.typeField.val("1").trigger("change");
    verifySingleRow(table, "f");

    this.groupField.val("1").trigger("change");
    expect(table.find("tr:visible").size()).toBe(1);
    expect(table.find("tfoot tr").is(":visible")).toBe(true);
  });
});

describe('adding a question to a question group', function() {
  beforeEach(function() {
    cbShowAlert = jasmine.createSpy("cbShowAlert");
    cbShowMsgAutoHide = jasmine.createSpy("cbShowMsgAutoHide");
    closeModal = jasmine.createSpy("closeModal");
    jasmine.getFixtures().fixturesPath = 'base/';
    loadFixtures(
        'modules/dashboard/javascript_tests/add_to_group_fixture.html');
  });
  it('receives a successful response to add_to_question_group', function() {
    addToGroupCallback(
      '{"status": 200, "payload":"{\\"question-id\\": 2, \\"group-id\\": 3}"}');
    expect($("#question-table td.groups ul:nth-child(1) li").size()).toBe(1);
    var locations = $("#question-table td.locations ul:first-child li")
    expect(locations.size()).toBe(3);
    expect(locations.eq(0).data("count")).toBe(2);
    expect(locations.eq(0).find(".count").text()).toBe(" (2)");
    expect(locations.eq(1).data("count")).toBe(1);
    expect(locations.eq(1).find(".count").text()).toBe("");
    expect(locations.eq(2).data("count")).toBe(1);
    expect(
      $("#question-group-table td.questions ul:first-child li").size()).toBe(1);
    expect(cbShowMsgAutoHide).toHaveBeenCalled();
  });
  it('receives an unsuccessful response to add_to_question_group', function() {
    addToGroupCallback('{"status": 500, "message": "error"}');
    expect(cbShowAlert).toHaveBeenCalledWith("Error: error");
  });
});

describe('editing a role in the role editor', function() {
  beforeEach(function() {
    showNoPermissionsMessage = jasmine.createSpy("showNoPermissionsMessage");
    jasmine.getFixtures().fixturesPath = 'base/';
    loadFixtures('modules/dashboard/javascript_tests/role_editor_fixture.html');
  });
  it('it shows a message when there are no permissions available', function() {
    $(".inputEx-ListField-childContainer").text("");
    setUpRoleEditorForm();
    expect(showNoPermissionsMessage).toHaveBeenCalled();
  });
  it('it shows no message with at least one permission', function() {
    setUpRoleEditorForm();
    expect(showNoPermissionsMessage).not.toHaveBeenCalled();
  });
  it('hides permissions modules with no permissions', function() {
    setUpRoleEditorForm();
    expect($("#a").is(":visible")).toBe(true);
    expect($("#b").is(":visible")).toBe(false);
  })
});

describe('the toggle feedback button', function() {
  beforeEach(function() {
    this.fixture = $(
      '<div>' +
      '  <div class="feedback"></div>' +
      '</div>'
    );
    $('body').empty().append(this.fixture);
    this.feedbackField = {
      divEl: this.fixture.find('.feedback').get(0),
      getValue: function() {},
      setValue: function(value) {}
    };
  });
  it('is a button in the DOM', function() {
    expect(this.fixture.find('button')).not.toExist();
    addToggleFeedbackButton(this.feedbackField);
    expect(this.fixture.find('button')).toExist();
  });
  it('is only added once', function() {
    addToggleFeedbackButton(this.feedbackField);
    expect(this.fixture.find('button').length).toEqual(1);
    addToggleFeedbackButton(this.feedbackField);
    expect(this.fixture.find('button').length).toEqual(1);
    addToggleFeedbackButton(this.feedbackField);
    expect(this.fixture.find('button').length).toEqual(1);
  });
  it('toggles the feedback visibility', function() {
    addToggleFeedbackButton(this.feedbackField);
    var button = this.fixture.find('button');
    var feedback = this.fixture.find('.feedback');
    expect(feedback).toBeVisible();
    button.click();
    expect(feedback).not.toBeVisible();
    button.click();
    expect(feedback).toBeVisible();
  });
});
