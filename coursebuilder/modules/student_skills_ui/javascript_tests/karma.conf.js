module.exports = function(config) {
  config.set({
    basePath: '../../..',
    files: [
      'lib/_static/jquery-2.2.4/jquery.min.js',
      'lib/_static/d3-3.4.3/d3.min.js',
      'lib/_static/underscore-1.4.3/underscore.min.js',
      'tests/unit/javascript_tests/lib/common.js',
      'modules/student_skills_ui/javascript_tests/*.js',
      {
        pattern: 'modules/student_skills_ui/javascript_tests/*.html',
        watched: true,
        included: false,
        served: true
      },
      'modules/student_skills_ui/_static/*/*.js',
      'modules/skill_map/_static/css/skill_map.css'
    ],
    exclude: ['**/karma.conf.js'],
    frameworks: ['jasmine-jquery', 'jasmine'],
    browsers: ['PhantomJS'],
    singleRun: true
  });
};
