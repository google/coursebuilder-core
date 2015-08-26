function ButterBar(popup, message, close) {
  this.popup = popup;
  this.message = message;
  this.close = close;
}
ButterBar.prototype.showMessage = function(text) {
  this.message.textContent = text;  // FF, Chrome
  this.message.innerText = text;    // IE
  if (! $(this.popup).hasClass("shown")) {
    $(this.popup).addClass("shown");
  }
  if (this.close != null) {
    this.close.onclick = cbHideMsg;
  }
  if (!$('.gcb-butterbar-dashboard').length) {
    ButterBar.keepInView();
    window.onscroll = ButterBar.keepInView;
  }
};
ButterBar.prototype.hide = function() {
  if ($(this.popup).hasClass("shown")) {
    $(this.popup).removeClass("shown");
  }
};
ButterBar.prototype.setCloseButtonVisible = function(visible) {
  if (visible) {
    $(this.close).css('display', '');
  } else {
    $(this.close).css('display', 'none');
  }
}
ButterBar.getButterBar = function() {
  return new ButterBar(document.getElementById("gcb-butterbar-top"),
    document.getElementById("gcb-butterbar-message"),
    document.getElementById("gcb-butterbar-close"));
};
ButterBar.setAutoHide = function() {
  ButterBar.cancelAutoHide();
  ButterBar.hideTimeoutID = window.setTimeout(cbHideMsg, 5000);
}
ButterBar.cancelAutoHide = function() {
  if(typeof ButterBar.hideTimeoutID == "number") {
    window.clearTimeout(ButterBar.hideTimeoutID);
    delete ButterBar.hideTimeoutID;
  }
}
function cbShowMsg(text) {
  ButterBar.cancelAutoHide();
  var butterBar = ButterBar.getButterBar();
  butterBar.setCloseButtonVisible(true);
  butterBar.showMessage(text);
}
function cbShowMsgAutoHide(text) {
  cbShowMsg(text);
  ButterBar.setAutoHide();
}
function cbShowAlert(text) {
  ButterBar.cancelAutoHide();
  // An alert should not be closed; hide the close button
  var butterBar = ButterBar.getButterBar();
  butterBar.setCloseButtonVisible(false);
  butterBar.showMessage(text);
}
function cbHideMsg() {
  ButterBar.getButterBar().hide();
  ButterBar.cancelAutoHide();
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
