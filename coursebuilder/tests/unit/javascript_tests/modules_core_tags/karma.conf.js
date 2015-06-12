module.exports = function(config) {
  config.set({
    basePath: '../../../..',
    files: [
      'https://ajax.googleapis.com/ajax/libs/jquery/2.1.3/jquery.min.js',
      'tests/unit/javascript_tests/modules_core_tags/*.js',
      'modules/core_tags/resources/drive_tag_script_manager.js',
      'modules/core_tags/resources/drive_tag_parent_frame.js',
      'modules/core_tags/resources/drive_tag_child_frame.js',
    ],
    exclude: ['**/karma.conf.js'],
    frameworks: ['jasmine-jquery', 'jasmine'],
    browsers: ['PhantomJS'],
    singleRun: true
  });
};
