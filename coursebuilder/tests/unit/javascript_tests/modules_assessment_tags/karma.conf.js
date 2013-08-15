basePath = '../../../..';

var KARMA_LIB = process.env.KARMA_LIB;

files = [
  JASMINE,
  JASMINE_ADAPTER,
  'assets/lib/jquery-1.7.2.min.js',
  KARMA_LIB + '/jasmine-jquery-1.5.2.js',

  // Test files
  'tests/unit/javascript_tests/modules_assessment_tags/*.js',

  // Test resources
  {
    pattern: 'tests/unit/common/event_payloads.json',
    watched: true,
    included: false,
    served: true
  },
  {
    pattern: 'tests/unit/javascript_tests/modules_assessment_tags/*.html',
    watched: true,
    included: false,
    served: true
  },

  // Files to test
  'modules/assessment_tags/resources/grading_lib.js'
];

exclude = [
  '**/karma.conf.js'
];

browsers = ['PhantomJS'];
singleRun = true;