module.exports = function(config) {
  config.set({
    basePath: '../../../..',
    files: [
      'tests/unit/javascript_tests/modules_oeditor/*.js',
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
