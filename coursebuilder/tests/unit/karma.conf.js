// Karma configuration
// Generated on Mon Mar 25 2013 18:28:05 GMT-0700 (PDT)


// base path, that will be used to resolve files and exclude
basePath = '../../';

var YUI_BASE = process.env.YUI_BASE;
var KARMA_LIB = process.env.KARMA_LIB;

// list of files / patterns to load in the browser
files = [
  JASMINE,
  JASMINE_ADAPTER,
  'assets/lib/jquery-1.7.2.min.js',
  YUI_BASE + '/yui/yui.js',
  YUI_BASE + '/yui-base/yui-base.js',
  YUI_BASE + '/node-core/node-core.js',
  YUI_BASE + '/array-extras/array-extras.js',
  YUI_BASE + '/dom-screen/dom-screen.js',
  YUI_BASE + '/node-screen/node-screen.js',
  YUI_BASE + '/node-style/node-style.js',
  YUI_BASE + '/querystring-stringify-simple/querystring-stringify-simple.js',
  YUI_BASE + '/io-base/io-base.js',
  YUI_BASE + '/json-parse/json-parse.js',
  YUI_BASE + '/json-stringify/json-stringify.js',
  YUI_BASE + '/event-synthetic/event-synthetic.js',
  YUI_BASE + '/event-key/event-key.js',
  YUI_BASE + '/oop/oop.js',
  YUI_BASE + '/event-custom-base/event-custom-base.js',
  YUI_BASE + '/event-custom-complex/event-custom-complex.js',
  YUI_BASE + '/intl/intl.js',
  YUI_BASE + '/pluginhost-base/pluginhost-base.js',
  YUI_BASE + '/pluginhost-config/pluginhost-config.js',
  YUI_BASE + '/attribute-core/attribute-core.js',
  YUI_BASE + '/base-core/base-core.js',
  YUI_BASE + '/attribute-events/attribute-events.js',
  YUI_BASE + '/attribute-extras/attribute-extras.js',
  YUI_BASE + '/attribute-base/attribute-base.js',
  YUI_BASE + '/base-base/base-base.js',
  YUI_BASE + '/base-pluginhost/base-pluginhost.js',
  YUI_BASE + '/dom-core/dom-core.js',
  YUI_BASE + '/dom-base/dom-base.js',
  YUI_BASE + '/selector-native/selector-native.js',
  YUI_BASE + '/selector/selector.js',
  YUI_BASE + '/node-base/node-base.js',
  YUI_BASE + '/event-base/event-base.js',
  YUI_BASE + '/node-pluginhost/node-pluginhost.js',
  YUI_BASE + '/plugin/plugin.js',
  YUI_BASE + '/event-delegate/event-delegate.js',
  YUI_BASE + '/node-event-delegate/node-event-delegate.js',
  YUI_BASE + '/dom-style/dom-style.js',
  KARMA_LIB + '/jasmine-jquery-1.5.2.js',

  // Load the test files
  'tests/unit/*.js',
  {pattern: 'tests/unit/*.html', watched: true, included: false, served: true},

  // Files to test
  'assets/lib/butterbar.js',
  'modules/assessment_tags/resources/grading_lib.js',
  'modules/dashboard/mc_question_editor_lib.js',
  'modules/oeditor/oeditor.js',
  'modules/oeditor/popup.js',
  'modules/oeditor/rte.js'
];


// list of files to exclude
exclude = [
  'tests/unit/karma.conf.js'
];


// test results reporter to use
// possible values: 'dots', 'progress', 'junit'
reporters = ['progress'];


// web server port
port = 9876;


// cli runner port
runnerPort = 9100;


// enable / disable colors in the output (reporters and logs)
colors = true;


// level of logging
// possible values: LOG_DISABLE || LOG_ERROR || LOG_WARN || LOG_INFO || LOG_DEBUG
logLevel = LOG_INFO;


// enable / disable watching file and executing tests whenever any file changes
autoWatch = true;


// Start these browsers, currently available:
// - Chrome
// - ChromeCanary
// - Firefox
// - Opera
// - Safari (only Mac)
// - PhantomJS
// - IE (only Windows)
browsers = ['PhantomJS'];


// If browser does not capture in given timeout [ms], kill it
captureTimeout = 60000;


// Continuous Integration mode
// if true, it capture browsers, run tests and exit
singleRun = true;
