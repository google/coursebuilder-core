basePath = '../../../..';

var KARMA_LIB = process.env.KARMA_LIB;

files = [
  JASMINE,
  JASMINE_ADAPTER,
  'assets/lib/jquery-1.7.2.min.js',
  KARMA_LIB + '/jasmine-jquery-1.5.2.js',

  // Test files
  'tests/unit/javascript_tests/modules_assessment_tags/*.js',

  // Files to test
  'modules/assessment_tags/resources/grading_lib.js',
  {
    pattern: 'tests/unit/javascript_tests/modules_assessment_tags/*.html',
    watched: true,
    included: false,
    served: true
  }
];

exclude = [
  '**/karma.conf.js'
];

browsers = ['PhantomJS'];
singleRun = true;