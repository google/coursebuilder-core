
// Hide and show the translated asset image and the Delete button
// depending on when the translated version of the image is actually
// present.
$('img').load(function(event){
  event.target.parentElement.style.display = null;
  $('span:contains("Delete")').parent().show();
});
$('img').error(function(event){
  event.target.parentElement.style.display = 'none';
  $('span:contains("Delete")').parent().hide();
});

cb_global.onSaveComplete = function() {
  $.each($('img'), function(i, img) {
    base = img.src.split('?')[0]
    img.src = base + '?z=' + new Date().getTime();
  });
};
