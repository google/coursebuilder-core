basePath = '../../../..';

var KARMA_LIB = process.env.KARMA_LIB;

files = [
  JASMINE,
  JASMINE_ADAPTER,
  'https://ajax.googleapis.com/ajax/libs/jquery/1.7.2/jquery.min.js',
  KARMA_LIB + '/jasmine-jquery-1.5.2.js',

  // Test files
  'tests/unit/javascript_tests/modules_core_tags/*.js',

  // Files to test
  'modules/core_tags/resources/drive_tag_script_manager.js',
  'modules/core_tags/resources/drive_tag_parent_frame.js',
  'modules/core_tags/resources/drive_tag_child_frame.js',
];

exclude = [
  '**/karma.conf.js'
];

browsers = ['PhantomJS'];
singleRun = true;
