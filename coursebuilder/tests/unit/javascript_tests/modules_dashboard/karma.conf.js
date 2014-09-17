basePath = '../../../..';

var YUI_BASE = process.env.YUI_BASE;
var KARMA_LIB = process.env.KARMA_LIB;

files = [
  JASMINE,
  JASMINE_ADAPTER,
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
  'https://ajax.googleapis.com/ajax/libs/jquery/1.7.2/jquery.min.js',
  KARMA_LIB + '/jasmine-jquery-1.5.2.js',

  // Test files
  'tests/unit/javascript_tests/modules_dashboard/*.js',

  // Test resources
  {
    pattern: 'tests/unit/javascript_tests/modules_dashboard/*.html',
    watched: true,
    included: false,
    served: true
  },

  // Files to test
  'modules/dashboard/mc_question_editor_lib.js',
  'modules/dashboard/resources/js/view.js',
  'modules/dashboard/resources/js/role_editor.js',
];

exclude = [
  '**/karma.conf.js'
];

browsers = ['PhantomJS'];
singleRun = true;
