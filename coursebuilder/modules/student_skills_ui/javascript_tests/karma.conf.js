module.exports = function(config) {
  config.set({
    basePath: '../../..',
    files: [
      'lib/_static/jquery-2.2.4/jquery.min.js',
      'lib/_static/d3-3.4.3/d3.min.js',
      'lib/_static/dagre-0.7.4/dagre.min.js',
      'lib/_static/dagre-d3-0.4.17p/dagre-d3.min.js',
      'lib/_static/underscore-1.4.3/underscore.min.js',
      'tests/unit/javascript_tests/lib/common.js',
      'modules/student_skills_ui/javascript_tests/*.js',
      'modules/student_skills_ui/_static/js/viz.js',
      {
        pattern: 'modules/student_skills_ui/javascript_tests/*.html',
        watched: true,
        included: false,
        served: true
      },
      'modules/skill_map/_static/css/skill_map.css'
    ],
    exclude: ['**/karma.conf.js'],
    frameworks: ['jasmine-jquery', 'jasmine'],
    browsers: ['PhantomJS'],
    singleRun: true
  });
};
