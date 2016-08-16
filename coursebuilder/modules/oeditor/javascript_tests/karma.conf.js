module.exports = function(config) {
  config.set({
    basePath: '../../..',
    files: [
      'lib/_static/jquery-2.2.4/jquery.min.js',
      'tests/unit/javascript_tests/lib/common.js',
      'modules/oeditor/javascript_tests/*.js',
      'modules/oeditor/templates/oeditor.js',
      'modules/oeditor/_static/js/popup.js',
      'modules/oeditor/templates/rte.js'
    ],

    exclude: ['**/karma.conf.js'],
    frameworks: ['jasmine-jquery', 'jasmine'],
    browsers: ['PhantomJS'],
    singleRun: true
  });
};
