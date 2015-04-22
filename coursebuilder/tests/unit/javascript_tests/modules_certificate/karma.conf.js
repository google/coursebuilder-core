basePath = '../../../..';

var KARMA_LIB = process.env.KARMA_LIB;

files = [
  JASMINE,
  JASMINE_ADAPTER,
  'https://ajax.googleapis.com/ajax/libs/jquery/2.1.3/jquery.min.js',
  KARMA_LIB + '/jasmine-jquery-1.5.2.js',

  // Test files
  'tests/unit/javascript_tests/modules_certificate/*.js',

  // Test resources
  {
    pattern: 'tests/unit/javascript_tests/modules_certificate/*.html',
    watched: true,
    included: false,
    served: true
  },

  // Files to test
  'modules/certificate/course_settings.js'
];

exclude = [
  '**/karma.conf.js'
];

browsers = ['PhantomJS'];
singleRun = true;