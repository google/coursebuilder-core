describe('V 1.4 Activities and Assessments', function() {

  var event_payloads, interactions;
  var auditDataDict, auditSource, auditIsAsync, mockLocation;

  function checkAuditValues(expectedData, expectedSource, expectedAsync) {
    // This addition to the data dict mocks the corresponding action in gcbAudit
    auditDataDict['location'] = mockLocation;

    expect(auditDataDict).toEqual(expectedData);
    expect(auditSource).toBe(expectedSource);
    expect(auditIsAsync).toBe(expectedAsync);
  }

  beforeEach(function() {
    jasmine.getFixtures().fixturesPath = 'base/';
    loadFixtures(
      'tests/unit/javascript_tests/assets_lib_activity_generic/fixture.html');
    event_payloads = JSON.parse(
      readFixtures('tests/unit/common/event_payloads.json'));
    interactions = eval('(' +
      readFixtures('tests/unit/javascript_tests/assets_lib_activity_generic/interactions.js') +
      ')');

    // Mock global variables used by activity-generic
    window.trans = {};
    window.assessmentGlobals = {};
    window.transientStudent = false;

    // Enable post events
    window.gcbCanRecordStudentEvents = true;

    // Reset tag so that test order doesn't matter
    window.globallyUniqueTag = 0;

    // Clear the test data from the outer scope
    auditCanPost = '';
    auditDataDict = '';
    auditSource = '';
    auditIsAsync = '';
    mockLocation = '';

    // Mock the function used for callbacks by all event emitters
    window.gcbAudit = function (can_post, data_dict, source, is_async) {
      auditCanPost = can_post;
      auditDataDict = data_dict;
      auditSource = source;
      auditIsAsync = is_async;
    };

    // Mock the function used to get params from the URL
    window.getParamFromUrlByName = function(name) {
      return decodeURI(
          (RegExp(name + '=' + '(.+?)(&|$)').exec(mockLocation)||[,null])[1]
      );
    };
  });

  it('can generate events for multiple choice activity', function() {
    var activity = interactions.multiple_choice_activity;
    var expectedEvent = event_payloads.multiple_choice_activity;
    mockLocation = expectedEvent.event_data.location;
    window.renderActivity(activity, $('#activityContents'));

    // Select the first choice and click submit
    $('#q1-0').click();
    $('#submit_1').click();

    checkAuditValues(expectedEvent.event_data, expectedEvent.event_source,
                     expectedEvent.event_async);
  });

  it('can generate events for multiple choice group activity', function() {
    var activity = interactions.multiple_choice_group_activity;
    var expectedEvent = event_payloads.multiple_choice_group_activity;
    mockLocation = expectedEvent.event_data.location;
    window.renderActivity(activity, $('#activityContents'));

    // Select the first choice for question 1, the second for question 2, and
    // click submit
    $('#q1-0-0').click();
    $('#q2-1-1').click();
    $('#submit_3').click();

    checkAuditValues(expectedEvent.event_data, expectedEvent.event_source,
                     expectedEvent.event_async);
  });

  it('can generate events for freetext activity', function() {
    var activity = interactions.free_text_activity;
    var expectedEvent = event_payloads.free_text_activity;
    mockLocation = expectedEvent.event_data.location;
    window.renderActivity(activity, $('#activityContents'));

    // Enter a correct answer and click submit
    $('#input_1').val("42");
    $('#submit_1').click();

    checkAuditValues(expectedEvent.event_data, expectedEvent.event_source,
                     expectedEvent.event_async);
  });

  it('can generate events for mixed assessment', function() {
    var assessment = interactions.mixed_assessment;
    var expectedEvent = event_payloads.mixed_assessment;
    mockLocation = expectedEvent.event_data.location;
    window.renderAssessment(assessment, $('#assessmentContents'));

    // Enter correct answers for all four question and click submit
    $('#q0-0').click();
    $('#q1').val("Rectus");
    $('#q2').val("match");
    $('#q3').val("42.0");
    $('#checkAnswersBtn').click();

    checkAuditValues(expectedEvent.event_data, expectedEvent.event_source,
                     expectedEvent.event_async);
  });
});
