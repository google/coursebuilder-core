module.exports = function(config) {
  config.set({
    basePath: '../../../..',
    files: [
      'https://ajax.googleapis.com/ajax/libs/jquery/2.1.3/jquery.min.js',
      'https://ajax.googleapis.com/ajax/libs/jqueryui/1.11.2/jquery-ui.min.js',
      'modules/skill_map/javascript_tests/student_skill_widget/*.js',
      {
        pattern: 'modules/skill_map/javascript_tests/student_skill_widget/' +
            '*.html',
        watched: true,
        included: false,
        served: true
      },
      'modules/skill_map/resources/js/lesson_header.js'
    ],
    exclude: ['**/karma.conf.js'],
    frameworks: ['jasmine-jquery', 'jasmine'],
    browsers: ['PhantomJS'],
    singleRun: true
  });
};
