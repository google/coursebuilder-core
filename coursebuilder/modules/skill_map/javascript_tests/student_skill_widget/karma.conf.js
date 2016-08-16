module.exports = function(config) {
  config.set({
    basePath: '../../../..',
    files: [
      'lib/_static/jquery-2.2.4/jquery.min.js',
      'lib/_static/jqueryui-1.11.4/jquery-ui.min.js',
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
