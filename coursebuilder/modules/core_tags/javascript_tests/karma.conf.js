module.exports = function(config) {
  config.set({
    basePath: '../../..',
    files: [
      'https://ajax.googleapis.com/ajax/libs/jquery/2.1.3/jquery.min.js',
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
