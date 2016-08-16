module.exports = function(config) {
  config.set({
    basePath: '../../..',
    files: [
      'lib/_static/jquery-2.2.4/jquery.min.js',
      'modules/core_tags/javascript_tests/*.js',
      'modules/core_tags/_static/js/drive_tag_script_manager.js',
      'modules/core_tags/_static/js/drive_tag_parent_frame.js',
      'modules/core_tags/templates/drive_tag_child_frame.js',
    ],
    exclude: ['**/karma.conf.js'],
    frameworks: ['jasmine-jquery', 'jasmine'],
    browsers: ['PhantomJS'],
    singleRun: true
  });
};
