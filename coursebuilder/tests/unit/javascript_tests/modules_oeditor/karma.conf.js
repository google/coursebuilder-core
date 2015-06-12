module.exports = function(config) {
  config.set({
    basePath: '../../../..',
    files: [
      'tests/unit/javascript_tests/modules_oeditor/*.js',
      'modules/oeditor/oeditor.js',
      'modules/oeditor/resources/popup.js',
      'modules/oeditor/rte.js'
    ],

    exclude: ['**/karma.conf.js'],
    frameworks: ['jasmine-jquery', 'jasmine'],
    browsers: ['PhantomJS'],
    singleRun: true
  });
};
