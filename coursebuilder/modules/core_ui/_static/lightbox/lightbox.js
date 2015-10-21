window.gcb = window.gcb || {};
/**
 * A class to put up a modal lightbox. Use setContent to set the DOM element
 * displayed in the lightbox.
 *
 * @class
 */
window.gcb.Lightbox = function() {
  this._window = $(window);
  this._container = $('<div class="lightbox"/>');
  this._background = $('<div class="background"/>');
  this._content = $('<div class="content"/>');

  this._container.append(this._background);
  this._container.append(this._content);

  this._background.click(this.close.bind(this));
  this._container.hide();
}
window.gcb.Lightbox.prototype = {
  /**
   * Set a DOM element to root the lightbox in. Typically will be document.body.
   *
   * @param rootEl {Node}
   */
  bindTo: function(rootEl) {
    $(rootEl).append(this._container);
    return this;
  },
  /**
   * Show the lightbox to the user.
   */
  show: function() {
    this._container.show();
    var top = this._window.scrollTop() +
        Math.max(8, (this._window.height() - this._content.height()) / 2);
    var left = this._window.scrollLeft() +
        Math.max(8, (this._window.width() - this._content.width()) / 2);

    this._content.css('top', top).css('left', left);
    return this;
  },
  /**
   * Close the lightbox and remove it from the DOM.
   */
  close: function() {
    this._container.remove();
    cbHideMsg();
    return this;
  },
  /**
   * Set the content shown in the lightbox.
   *
   * @param contentEl {Node or jQuery}
   */
  setContent: function(contentEl) {
    this._content.empty().append(contentEl);
    return this;
  }
};
