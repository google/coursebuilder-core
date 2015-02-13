var UNIT_LESSON_TITLE_REST_HANDLER_URL = 'rest/course/outline';
var UNIT_LESSON_TITLE_XSRF_TOKEN = $('.course-outline')
    .data('unitLessonTitleXsrfToken');

function parseJson(s) {
  var XSSI_PREFIX = ')]}\'';
  return JSON.parse(s.replace(XSSI_PREFIX, ''));
}
function zebraStripeList() {
  $('.course-outline li > div').each(function(i, elt) {
    $(elt).removeClass('even odd').addClass(i % 2 == 0 ? 'even' : 'odd')
  });
}
function getCourseOutlineData() {
  // Marshall the course outline data in the format consumed by
  // courses.Course.reorder_units()
  var courseOrderData = [];
  $('.course-outline ol.course > li').each(function() {
    var unitId = $(this).data('unitId');
    var lessons = []

    // The table presents pre-assessments as part of the containing unit, but
    // we need to assign them a position in the list of units. So insert this
    // unit's pre-assessment (if any) immediately above the unit itself.
    $(this).find('ol.unit.pre > li').each(function() {
      courseOrderData.push({
        id: $(this).data('unitId'),
        title: '',
        lessons: []
      });
    });

    // Insert the unit with all its lessons into the list of unit data
    $(this).find('ol.unit:not(.pre, .post) > li').each(function() {
      var lessonId = $(this).data('lessonId');
      lessons.push({id: lessonId, title: ''});
    });
    courseOrderData.push({id: unitId, title: '', lessons: lessons});

    // Finally insert the unit's post-assessment (if any) after the unit.
    $(this).find('ol.unit.post > li:not(.add-lesson)').each(function() {
      courseOrderData.push({
        id: $(this).data('unitId'),
        title: '',
        lessons: []});
    });
  });
  return courseOrderData;
}
function reorderCourse() {
  var courseOutlineData = getCourseOutlineData();
  var request = JSON.stringify({
    xsrf_token: UNIT_LESSON_TITLE_XSRF_TOKEN,
    payload: JSON.stringify({outline: courseOutlineData})
  });
  $.ajax({
    type: 'PUT',
    url: UNIT_LESSON_TITLE_REST_HANDLER_URL,
    data: {request: request},
    dataType: 'text',
    success: onReorderCourse
  });
}
function onReorderCourse(data) {
  data = parseJson(data);
  if (data.status == 200) {
    cbShowMsgAutoHide(data.message)
  } else {
    cbShowMsg(data.message);
  }
}
function onUpdate(event, ui) {
  // Called when a item has been dragged and dropped
  zebraStripeList();
  reorderCourse();
}
function bindSortableBehavior() {
  $('div.course-outline.editable ol.course').sortable({
    cancel: '.add-lesson, .pre-assessment, .post-assessment',
    handle: '.reorder',
    placeholder: 'placeholder unit',
    update: onUpdate
  }).disableSelection();
  $('div.course-outline.editable ol.unit').sortable({
    cancel: '.add-lesson, .pre-assessment, .post-assessment',
    connectWith: 'ol.unit:not(.pre, .post)',
    handle: '.reorder',
    placeholder: 'placeholder lesson',
    update: onUpdate
  }).disableSelection();
}
function init() {
  bindSortableBehavior();
  zebraStripeList();
}

init();
