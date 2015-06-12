module.exports = function(config) {
  config.set({
    basePath: '../../../../..',
    files: [
      'https://ajax.googleapis.com/ajax/libs/jquery/2.1.3/jquery.min.js',
      'tests/unit/javascript_tests/modules_skill_map/lesson_editor/*.js',
      {
        pattern: 'tests/unit/javascript_tests/modules_skill_map/' +
            'lesson_editor/*.html',
        watched: true,
        included: false,
        served: true
      },
      'modules/skill_map/resources/js/skill_tagging_lib.js'
    ],
    exclude: ['**/karma.conf.js'],
    frameworks: ['jasmine-jquery', 'jasmine'],
    browsers: ['PhantomJS'],
    singleRun: true
  });
};
