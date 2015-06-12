module.exports = function(config) {
  config.set({
    basePath: '../../../..',
    files: [
      'https://ajax.googleapis.com/ajax/libs/jquery/2.1.3/jquery.min.js',
      'tests/unit/javascript_tests/modules_questionnaire/*.js',
      {
        pattern: 'tests/unit/javascript_tests/modules_questionnaire/' +
            'fixture.html',
        watched: true,
        included: false,
        served: true
      },
      {
        pattern: 'tests/unit/javascript_tests/modules_questionnaire/' +
            'form_data.json',
        watched: true,
        included: false,
        served: true
      },
      'modules/questionnaire/resources/js/questionnaire.js'
    ],
    exclude: ['**/karma.conf.js'],
    frameworks: ['jasmine-jquery', 'jasmine'],
    browsers: ['PhantomJS'],
    singleRun: true,
  });
};
