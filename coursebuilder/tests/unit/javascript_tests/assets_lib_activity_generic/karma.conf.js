module.exports = function(config) {
  config.set({
    basePath: '../../../..',
    files: [
      'https://ajax.googleapis.com/ajax/libs/jquery/2.1.3/jquery.min.js',
      'tests/unit/javascript_tests/assets_lib_activity_generic/tests.js',
      {
        pattern: 'tests/unit/javascript_tests/assets_lib_activity_generic/' +
            'interactions.js',
        watched: true,
        included: false,
        served: true
      },
      'assets/lib/activity-generic-1.3.js',
      {
        pattern: 'tests/unit/common/event_payloads.json',
        watched: true,
        included: false,
        served: true
      },
      {
        pattern: 'tests/unit/javascript_tests/assets_lib_activity_generic/' +
            '*.html',
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
