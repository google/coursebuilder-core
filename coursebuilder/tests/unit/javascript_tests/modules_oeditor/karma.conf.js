basePath = '../../../..';

files = [
  JASMINE,
  JASMINE_ADAPTER,

  // Test files
  'tests/unit/javascript_tests/modules_oeditor/*.js',

  // Files to test
  'modules/oeditor/oeditor.js',
  'modules/oeditor/popup.js',
  'modules/oeditor/rte.js'
];

exclude = [
  '**/karma.conf.js'
];

browsers = ['PhantomJS'];
singleRun = true;