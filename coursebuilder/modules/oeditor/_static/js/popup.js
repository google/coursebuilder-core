/**
 * The definitions of the controls used by the iframed popup.
 *
 * @param frameProxy The proxy which is used to communicate with the editor in
 *     the parent window.
 * @param env The shared GCB envronment variables.
 */
function FramedEditorControls(Y, frameProxy, env, maybePerformAction,
    alertIfNotSavedChanges) {
  var that = this;
  this._Y = Y;
  this._frameProxy = frameProxy;
  this._env = env;
  this._maybePerformAction = maybePerformAction;
  this._alertIfNotSavedChanges = alertIfNotSavedChanges;

  var close = this._close.bind(this);
  this._Y.one('.close-button').on('click', close);
  this._frameProxy.onBackgroundClick(close);
}
FramedEditorControls.prototype = {
  _close: function() {
    var that = this;
    var reallyClose = true;
    var changesMessage = this._alertIfNotSavedChanges(this._env);
    if (changesMessage) {
      reallyClose = confirm(changesMessage + '\n\n' +
          'Are you sure you want to close?');
    }
    if (reallyClose) {
      this._maybePerformAction(this._env.onCloseClick, function() {
        that._frameProxy.close();
      });
    }
    return false;
  },

  getSaveButton: function() {
    var that = this;
    return {
      type: 'submit-link',
      value: 'Save',
      className: 'inputEx-Button inputEx-Button-Submit-Link gcb-pull-left',
      onClick: function() {
        var valid = that._env.validate
            ? that._env.validate() : that._env.form.validate();
        if (! valid) {
          cbShowMsg('Cannot save because some required fields have not been ' +
              'set.');
          return;
        }
        that._maybePerformAction(that._env.onSaveClick, function() {
          that._frameProxy.setValue(that._env.form.getValue());
          that._frameProxy.submit();
        });
        return false;
      }
    };
  },

  getCloseButton: function() {
    var that = this;
    return {
      type: 'link',
      value: 'Close',
      className: 'inputEx-Button inputEx-Button-Link gcb-pull-left',
      onClick: this._close.bind(this)
    };
  },

  getDeleteButton: function() {
    return null;
  },

  populateForm: function() {
    this._frameProxy.init(this._env.schema);
    this._env.form.setValue(this._frameProxy.getValue());
    this._env.lastSavedFormValue = this._env.form.getValue();

    // InputEx sets invalid field class on load but we want this only on submit
    this._Y.all('.inputEx-invalid').removeClass('inputEx-invalid');

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
function FrameProxy(win, rootId, url, getValue, context, onSubmit, onClose) {
  this._win = win;
  this._rootId = rootId;
  this._url = url;
  this._getValue = getValue;
  this._schema = null;
  this._value = null;
  this._context = context;
  this._onSubmit = onSubmit;
  this._onClose = onClose;
}
FrameProxy.prototype = {
  open: function() {
    this._root = this._win.document.getElementById(this._rootId);
    this._root.className = '';
    this._iframe = this._win.document.createElement('iframe');
    this._iframe.src = this._url;
    this._iframe.id = 'modal-editor-iframe';
    this._root.appendChild(this._iframe);
  },

  init: function(schema) {
    this._schema = schema;
    if (this._getValue) {
      this._value = this._getValue(schema);
    }
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

  onBackgroundClick: function(callback) {
    // Use plain JS because we don't have a $ or Y for the parent window.
    this._root.querySelector('.background').addEventListener('click', callback);
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
    this._onSubmit(this._value, this._schema);
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
