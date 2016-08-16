module.exports = function(config) {
  config.set({
    basePath: '../../../..',
    files: [
      'lib/_static/jquery-2.2.4/jquery.min.js',
      'tests/unit/javascript_tests/assets_lib_butterbar/*.js',
      'modules/oeditor/_static/js/butterbar.js',
      {
        pattern: 'tests/unit/javascript_tests/assets_lib_butterbar/*.html',
        watched: true,
        included: false,
        served: true
      }
    ],
    exclude: ['**/karma.conf.js'],
    frameworks: ['jasmine-jquery', 'jasmine'],
    browsers: ['PhantomJS'],
    singleRun: true
  });
};
