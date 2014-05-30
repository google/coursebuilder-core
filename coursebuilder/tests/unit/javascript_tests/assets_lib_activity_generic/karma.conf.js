basePath = '../../../..';

var KARMA_LIB = process.env.KARMA_LIB;

files = [
  JASMINE,
  JASMINE_ADAPTER,
  'https://ajax.googleapis.com/ajax/libs/jquery/1.7.2/jquery.min.js',
  KARMA_LIB + '/jasmine-jquery-1.5.2.js',

  // Test file
  'tests/unit/javascript_tests/assets_lib_activity_generic/tests.js',

  {
    pattern: 'tests/unit/javascript_tests/assets_lib_activity_generic/interactions.js',
    watched: true,
    included: false,
    served: true
  },

  // Files to test
  'assets/lib/activity-generic-1.3.js',
  {
    pattern: 'tests/unit/common/event_payloads.json',
    watched: true,
    included: false,
    served: true
  },
  {
    pattern: 'tests/unit/javascript_tests/assets_lib_activity_generic/*.html',
    watched: true,
    included: false,
    served: true
  }
];

exclude = [
  '**/karma.conf.js',
];

browsers = ['PhantomJS'];
singleRun = true;
