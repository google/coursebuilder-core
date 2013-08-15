/**
 * The definitions of the controls used by the iframed popup.
 *
 * @param frameProxy The proxy which is used to communicate with the editor in
 *     the parent window.
 * @param env The shared GCB envronment variables.
 */
function FramedEditorControls(Y, frameProxy, env) {
  this._Y = Y;
  this._frameProxy = frameProxy;
  this._env = env;
}
FramedEditorControls.prototype = {
  getSaveButton: function() {
    var that = this;
    return {
      type: 'submit-link',
      value: 'Save',
      className: 'inputEx-Button inputEx-Button-Submit-Link gcb-pull-left',
      onClick: function() {
        that._frameProxy.setValue(that._env.form.getValue());
        that._frameProxy.submit();
      }
    };
  },

  getCloseButton: function() {
    var that = this;
    return {
      type: 'link',
      value: 'Close',
      className: 'inputEx-Button inputEx-Button-Link gcb-pull-left',
      onClick: function() {
        that._frameProxy.close();
      }
    };
  },

  getDeleteButton: function() {
    return null;
  },

  populateForm: function() {
    this._env.form.setValue(this._frameProxy.getValue());
    cbHideMsg();
    document.getElementById("formContainer").style.display = "block";
    this._frameProxy.onLoad();
    this._env.onFormLoad(this._Y);
  }
};

/**
 * FrameProxy provides a object model for the iframed popup.
 *
 * @param rootId the id of the root element for the frame
 * @param value an object holding the values for the popup form
 * @param onSubmit a callback when the user clicks submit, passed the current
 *     value object as a parameter
 * @param onClose a callback when the user clicks close
 */
function FrameProxy(rootId, url, value, context, onSubmit, onClose) {
  this._rootId = rootId;
  this._url = url;
  this._value = value;
  this._context = context;
  this._onSubmit = onSubmit;
  this._onClose = onClose;
}
FrameProxy.prototype = {
  open: function() {
    this._root = document.getElementById(this._rootId);
    this._root.className = '';
    this._iframe = document.createElement('iframe');
    this._iframe.src = this._url;
    this._iframe.id = 'modal-editor-iframe';
    this._root.appendChild(this._iframe);
  },

  getValue: function() {
    return this._value;
  },

  setValue: function(value) {
    this._value = value;
  },

  getContext: function() {
    return this._context;
  },

  onLoad: function() {
    this.refresh();
  },

  refresh: function() {
    var height = this._iframe.contentWindow.document.body.clientHeight + 50;
    // TODO(jorr): Use Y.one('body').get('winHeight') after we get access to Y
    if (window.innerHeight) {
      height = Math.min(height, window.innerHeight - 20);
    }
    this._iframe.style.height = height + 'px';
    this._iframe.style.marginTop = (-height / 2) + 'px';
  },

  submit: function() {
    this._onSubmit(this._value);
    this._close();
  },

  close: function() {
    if (this._iframe) {
      this._close();
      this._onClose();
    }
  },

  _close: function() {
    this._root.removeChild(this._iframe);
    this._iframe = null;
    this._root.className = 'hidden';
  }
};
