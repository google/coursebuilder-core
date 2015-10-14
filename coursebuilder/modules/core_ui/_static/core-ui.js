$(function() {
  window.gcb = {};

  var modules = {
    // TODO(jorr): Bring Butterbar in here.
    collapse: {
      js: ['_static/collapse/collapse.js'],
      css: ['_static/collapse/collapse.css']
    },
    list: {
      js: [],
      css: ['_static/list/list.css']
    },
    lightbox: {
      js: ['_static/lightbox/lightbox.js'],
      css: ['_static/lightbox/lightbox.css']
    }
  };
  var base = '/modules/core_ui/';

  $.each(modules, function(name, module) {
    $.each(module.css, function(_, uri) {
      $('head').append($('<link rel="stylesheet">').attr('href', base + uri));
    });
    $.each(module.js, function(_, uri) {
      $('body').append($('<script>').attr('src', base + uri));
    });
  });
});
