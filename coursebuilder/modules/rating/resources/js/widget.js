var XSRF_TOKEN = $('div.gcb-ratings-widget').data('xsrf-token');
var KEY = window.location.pathname + window.location.search;

function parseJson(s) {
  var XSSI_PREFIX = ')]}\'';
  return JSON.parse(s.replace(XSSI_PREFIX, ''));
}

function onRatingClick(target) {
  target = $(target);
  target.closest('ul').find('li > button').removeClass('selected');
  target.addClass('selected');
  target.closest('div.gcb-ratings-widget')
      .find('div.gcb-extra-feedback')
      .removeClass('hidden');
  doPostRating(target.data('value'), null);
}

function onSubmitClick(target) {
  $(target).parent().addClass('hidden');
  var textarea = $(target).parent().find('textarea');
  var additionalComments = textarea.val();
  textarea.val('');

  var rating = $(target).closest('div.gcb-ratings-widget')
      .find('li > button.selected').data('value');

  doPostRating(rating, additionalComments);
}

function doPostRating(rating, additionalComments) {

  var request = JSON.stringify({
    xsrf_token: XSRF_TOKEN,
    payload: JSON.stringify({
      key: KEY,
      rating: rating,
      additional_comments: additionalComments
    })
  });

  $.ajax({
    type: 'POST',
    url: 'rest/modules/rating',
    data: {'request': request},
    dataType: 'text',
    success: function(data) {
      onAjaxPostRating(data);
    }
  });
}

function onAjaxPostRating(data) {
  data = parseJson(data);
  if (data.status == 200) {
    cbShowMsgAutoHide(data.message)
  } else {
    cbShowMsg(data.message);
  }
}

function loadRating() {

  var request = JSON.stringify({
    xsrf_token: XSRF_TOKEN,
    payload: JSON.stringify({
      key: KEY
    })
  });

  $.ajax({
    type: 'GET',
    url: 'rest/modules/rating',
    data: {'request': request},
    dataType: 'text',
    success: function(data) {
      onAjaxGetRating(data);
    }
  });
}

function onAjaxGetRating(data) {
  data = parseJson(data);
  if (data.status != 200) {
    cbShowMsg(data.message);
    return;
  }
  var payload = JSON.parse(data.payload);
  var index = payload.rating;
  if (index != null) {
    var selectedEl = $('ul.gcb-ratings button')[index];
    $(selectedEl).addClass('selected');
  }
}

function init() {
  $('div.gcb-ratings-widget ul.gcb-ratings > li > button').click(function() {
    onRatingClick(this);
  });
  $('div.gcb-ratings-widget > div.gcb-extra-feedback > button').click(function() {
    onSubmitClick(this);
  });

  setInterval(function() {
    var submitButton = $('div.gcb-ratings-widget > div.gcb-extra-feedback ' +
        '> button');

    if ($('div.gcb-ratings-widget > div.gcb-extra-feedback > textarea').val()) {
      submitButton.prop('disabled', false);
    } else {
      submitButton.prop('disabled', true);
    }
  }, 100);

  loadRating();
}

init();
