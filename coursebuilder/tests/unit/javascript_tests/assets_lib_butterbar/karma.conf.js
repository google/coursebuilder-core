basePath = '../../../..';

var KARMA_LIB = process.env.KARMA_LIB;

files = [
  JASMINE,
  JASMINE_ADAPTER,
  'assets/lib/jquery-1.7.2.min.js',
  KARMA_LIB + '/jasmine-jquery-1.5.2.js',

  // Test files
  'tests/unit/javascript_tests/assets_lib_butterbar/*.js',

  // Files to test
  'assets/lib/butterbar.js',
  {
    pattern: 'tests/unit/javascript_tests/assets_lib_butterbar/*.html',
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