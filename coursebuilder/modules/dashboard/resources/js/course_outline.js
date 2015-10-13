var COURSE_SORTABLE_SELECTOR = 'div.course-outline.reorderable ol.course';
var UNIT_SORTABLE_SELECTOR = 'div.course-outline.reorderable ol.unit';
var UNIT_LESSON_TITLE_REST_HANDLER_URL = 'rest/course/outline';
var UNIT_LESSON_TITLE_XSRF_TOKEN = $('.course-outline')
    .data('unitLessonTitleXsrfToken');
var UNIT_TITLE_TEMPLATE = $('.course-outline').data('unitTitleTemplate');


function parseJson(s) {
  var XSSI_PREFIX = ')]}\'';
  return JSON.parse(s.replace(XSSI_PREFIX, ''));
}
function zebraStripeList() {
  $('.course-outline li > div').each(function(i, elt) {
    $(elt).removeClass('gcb-list__row--dark-stripe')
    if (i % 2 == 0) {
      $(elt).addClass('gcb-list__row--dark-stripe')
    }
  });
}
function addNumbering() {
  $('.course-outline ol.course > li > .gcb-list__row.unit').each(function(i) {
    var unitIndex = i + 1;
    var titleEl = $(this).find('.name > a');
    var title = UNIT_TITLE_TEMPLATE
        .replace('%(index)s', unitIndex)
        .replace('%(title)s', titleEl.data('title'))
    titleEl.text(title);

    var lessonIndex = 1;
    $(this).parent().find('ol.unit:not(.pre, .post) > li').each(function() {
      if ($(this).data('autoIndex') == 'True') {
        var titleEl = $(this)
            .find('> .gcb-list__row.lesson .name > a');
        titleEl.text(lessonIndex + '. ' + titleEl.data('title'));
        ++lessonIndex;
      }
    });
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
function onUpdate(event, ui) {
  // Called when a item has been dragged and dropped
  redraw();
  reorderCourse(ui.item);
}
function reorderCourse(draggedItem) {
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
    success: function(data) {
      onReorderAjaxSuccess(data, draggedItem)
    },
    error: function() {
      onReorderAjaxError(draggedItem);
    },
    complete: onReorderAjaxComplete
  });
  // Dsiable further sorting while the update is in progress
  $(COURSE_SORTABLE_SELECTOR).sortable('disable');
  $(UNIT_SORTABLE_SELECTOR).sortable('disable');
}
function onReorderAjaxSuccess(data, draggedItem) {
  data = parseJson(data);
  if (data.status == 200) {
    cbShowMsgAutoHide(data.message)
  } else {
    showErrorMessageAndRevert(data.message, draggedItem);
  }
}
function onReorderAjaxError(draggedItem) {
  showErrorMessageAndRevert('Cannot save your changes. Please re-try.',
      draggedItem);
}
function onReorderAjaxComplete() {
  // Re-enabled sorting after the update is complete
  $(COURSE_SORTABLE_SELECTOR).sortable('enable');
  $(UNIT_SORTABLE_SELECTOR).sortable('enable');
}
function showErrorMessageAndRevert(message, draggedItem) {
  cbShowMsg(message);
  draggedItem.closest('ol').sortable('cancel');
  redraw();
}
function redraw() {
  zebraStripeList();
  setTimeout(addNumbering, 500);
}
function bindSortableBehavior() {
  $(COURSE_SORTABLE_SELECTOR).sortable({
    cancel: '.add-lesson, .pre-assessment, .post-assessment',
    handle: '.reorder',
    placeholder: 'placeholder unit gcb-list__row',
    update: onUpdate
  }).disableSelection();
  $(UNIT_SORTABLE_SELECTOR).sortable({
    cancel: '.add-lesson, .pre-assessment, .post-assessment',
    connectWith: 'ol.unit:not(.pre, .post)',
    handle: '.reorder',
    placeholder: 'placeholder lesson gcb-list__row',
    update: onUpdate
  }).disableSelection();
}
function init() {
  bindSortableBehavior();
  zebraStripeList();
  addNumbering();
}

init();
