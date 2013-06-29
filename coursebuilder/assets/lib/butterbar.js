function ButterBar(popup, message, close) {
  this.popup = popup;
  this.message = message;
  this.close = close;
}
ButterBar.prototype.showMessage = function(text) {
  this.message.textContent = text;  // FF, Chrome
  this.message.innerText = text;    // IE
  this.popup.className = "gcb-butterbar shown";
  if (this.close != null) {
    this.close.onclick = cbHideMsg;
  }
  window.onscroll = ButterBar.keepInView;
};
ButterBar.prototype.hide = function() {
  this.popup.className = "gcb-butterbar";
};
ButterBar.getButterBar = function() {
  return new ButterBar(document.getElementById("gcb-butterbar-top"),
    document.getElementById("gcb-butterbar-message"),
    document.getElementById("gcb-butterbar-close"));
};
function cbShowMsg(text) {
  ButterBar.getButterBar().showMessage(text);
}
function cbHideMsg() {
  ButterBar.getButterBar().hide();
}
ButterBar.keepInView = function() {
  var popup = ButterBar.getButterBar().popup;
  var container = popup.parentElement;

  container.style.top = null;
  $(container).removeClass('fixed');

  var offset = $(popup).offset().top;
  if (offset - $(document).scrollTop() <= 10) {
    $(container).addClass('fixed');
    container.style.top = (10 - popup.offsetTop) + "px";
  }
};
