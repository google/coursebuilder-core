module.exports = function(config) {
  config.set({
    basePath: '../../..',
    files: [
      'lib/_static/jquery-2.2.4/jquery.min.js',
      'tests/unit/javascript_tests/lib/common.js',
      'modules/core_ui/javascript_tests/*.js',
      {
        pattern: 'modules/core_ui/javascript_tests/*.html',
        watched: true,
        included: false,
        served: true
      },
      'modules/core_ui/_static/*/*.js'
    ],
    exclude: ['**/karma.conf.js'],
    frameworks: ['jasmine-jquery', 'jasmine'],
    browsers: ['PhantomJS'],
    singleRun: true
  });
};
