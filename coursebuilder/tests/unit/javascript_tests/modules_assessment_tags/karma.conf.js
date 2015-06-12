module.exports = function(config) {
  config.set({
    basePath: '../../../..',
    files: [
      'https://ajax.googleapis.com/ajax/libs/jquery/2.1.3/jquery.min.js',
      'tests/unit/javascript_tests/modules_assessment_tags/*.js',
      {
        pattern: 'tests/unit/common/event_payloads.json',
        watched: true,
        included: false,
        served: true
      },
      {
        pattern: 'tests/unit/javascript_tests/modules_assessment_tags/*.html',
        watched: true,
        included: false,
        served: true
      },
      'modules/assessment_tags/resources/grading_lib.js'
    ],
    exclude: ['**/karma.conf.js'],
    frameworks: ['jasmine-jquery', 'jasmine'],
    browsers: ['PhantomJS'],
    singleRun: true
  });
};
