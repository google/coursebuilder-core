basePath = '../../../../..';

var KARMA_LIB = process.env.KARMA_LIB;

files = [
  JASMINE,
  JASMINE_ADAPTER,
  'https://ajax.googleapis.com/ajax/libs/jquery/1.7.2/jquery.min.js',
  'https://ajax.googleapis.com/ajax/libs/jqueryui/1.11.2/jquery-ui.min.js',
  KARMA_LIB + '/jasmine-jquery-1.5.2.js',

  // Test files
  'tests/unit/javascript_tests/modules_skill_map/student_skill_widget/*.js',

  // Test resources
  {
    pattern: 'tests/unit/javascript_tests/modules_skill_map/student_skill_widget/*.html',
    watched: true,
    included: false,
    served: true
  },

  // Files to test
  'modules/skill_map/resources/js/lesson_header.js'
];

exclude = [
  '**/karma.conf.js'
];

browsers = ['PhantomJS'];
singleRun = true;
