module.exports = function(config) {
  config.set({
    basePath: '../../..',
    files: [
      'https://ajax.googleapis.com/ajax/libs/jquery/2.1.3/jquery.min.js',
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
