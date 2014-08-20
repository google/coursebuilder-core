//server communications timeout
var ajaxRpcTimeoutMillis = 45 * 1000;
// XSSI prefix. Must be kept in sync with models/transforms.py.
var xssiPrefix = ")]}'";

/**
 * Compare two JS objects for equality by value.
 */
function deepEquals(x, y) {
  if (typeof(x) != "object") {
    return x === y;
  }
  if (typeof(y) != "object" || propertyCount(x) != propertyCount(y)) {
    return false;
  }
  for (e in x) {
    if (x.hasOwnProperty(e) && (typeof(y[e]) == "undefined" || !deepEquals(x[e], y[e]))) {
      return false;
    }
  }
  return true;
}
function propertyCount(x) {
  var count = 0;
  for (e in x) {
    if (x.hasOwnProperty(e)) {
      ++count;
    }
  }
  return count;
}

/**
 * Parses JSON string that starts with an XSSI prefix.
 */
function parseJson(s) {
  return JSON.parse(s.replace(xssiPrefix, ''));
}


function formatServerErrorMessage(status, message) {
  var msg = "Unknown error (" + status + ").";
  if (message) {
    msg = message;
  }
  switch (status) {
    case 412:
      return msg;
    default:
      return "Server error; error code " + status + ". " + msg;
  }
}

/**
 * Render an asset as an image if it is a recognized image type; otherwise
 * simply expose a link to the asset.
 */
function renderAsset(Y, uri) {
  imageExts = ['png', 'jpg', 'jpeg', 'gif'];
  var div = document.createElement('div');
  for (i in imageExts) {
    var ext = imageExts[i];
    if (uri.length >= ext.length &&
        uri.substring(uri.length - ext.length).toLowerCase() == ext) {
      var img = document.createElement('img');
      img.setAttribute('src', uri);
      img.setAttribute('class', 'framed');
      div.appendChild(img);
      div.appendChild(document.createElement('br'));
      break;
    }
  }
  var link = document.createElement('a');
  link.setAttribute('href', uri);
  link.setAttribute('target', '_blank');
  link.appendChild(document.createTextNode(uri));
  div.appendChild(link);
  return div;
}

/**
 * Expose a method to disable the save button by means of an annotation in the
 * schema. Use the 'uneditable' schema type with visuType=functName and
 * funcname=disableSave.
 *
 * @param {YUI Root} Y the current YUI root object
 * @param {string} value the value of the uneditable schema field
 * @param {object} env the CB environment table
 */
function disableSave(Y, value, env) {
  if (env.form) {
    for (var i = 0; i < env.form.buttons.length; i++) {
      var button = env.form.buttons[i];
      if (button.options.type == 'submit-link') {
        env.form.buttons[i].disable();
      }
    }
  }
  var div = document.createElement('div');
  div.appendChild(document.createTextNode(value));
  return div;
}

function disableAllControlButtons(form) {
  if (form) {
    for (var i = 0; i < form.buttons.length; i++) {
      form.buttons[i].disable();
    }
  }
}

function enableAllControlButtons(form) {
  if (form) {
    for (var i = 0; i < form.buttons.length; i++) {
      form.buttons[i].enable();
    }
  }
}

/**
 * If there is a form element marked with class 'split-from-main-group'
 * then this is pulled out of the fieldset and inserted between the fieldset
 * and the button bar.
 */
function moveMarkedFormElementsOutOfFieldset(Y) {
  var splitFromMainGroup = Y.one('div.split-from-main-group');
  if (splitFromMainGroup != null) {
    // InputEx puts the class name on the div which contains the input element
    // but we really want to work with the parent.
    var splitFromMainGroupParent = splitFromMainGroup.get('parentNode');
    splitFromMainGroupParent.addClass('split-from-main-group-parent');
    Y.one('#cb-oeditor-form').insertBefore(splitFromMainGroupParent,
      Y.one('#cb-oeditor-form > div.inputEx-Form-buttonBar'));
  }
}

function getEditCustomTagUrl(env, tagName) {
  var url = 'oeditorpopup?action=edit_custom_tag';
  url += '&tag_name=' + escape(tagName);
  if (env.schema.id == 'Lesson Entity' && env.schema.properties &&
      env.schema.properties.key) {
    url += '&lesson_id=' + escape(env.form.getValue().key);
  }
  return url;
}

function getAddCustomTagUrl(env, tagName, excludedCustomTags) {
  var url = 'oeditorpopup?action=add_custom_tag';
  if (env.schema.id == 'Lesson Entity' && env.schema.properties &&
      env.schema.properties.key) {
    url += '&lesson_id=' + escape(env.form.getValue().key);
  } else {
    var lessonId = new RegExp('&lesson_id=\\d+').exec(window.location.search);
    if (lessonId) {
      url += lessonId;
    }
  }
  if (tagName) {
    url += '&tag_name=' + escape(tagName);
  }
  if (excludedCustomTags) {
    for (var i = 0; i < excludedCustomTags.length; i++) {
      url += '&excluded_tags=' + escape(excludedCustomTags[i]);
    }
  }
  return url;
}

/**
 * Define a YUI class for a Google Course Builder rich text editor.
 */
var GcbRteField = function(options) {
  GcbRteField.superclass.constructor.call(this, options);
};

function onPageLoad(env) {
  /**
   * Define a rich text editor widget in the module "gcb-rte".
   */
  YUI.add("gcb-rte",
    function(Y) {
      Y.extend(GcbRteField, Y.inputEx.Field, getGcbRteDefs(
          env, Y.DOM, Y.YUI2.widget.SimpleEditor, Y.YUI2.util.Resize));
      Y.inputEx.registerType("html", GcbRteField, []);
    },
    '3.1.0',
    {requires: ['inputex-field', 'yui2-editor', 'yui2-resize']}
  );

  YUI(getYuiConfig(env.bundle_lib_files)).use(
    env.required_modules,
    mainYuiFunction);

  env.inputEx = env.inputEx || {};
  env.inputEx.visus = env.inputEx.visus || {};
  env.inputEx.visus.renderAsset = renderAsset;
  env.inputEx.visus.disableSave = disableSave;

  // set initial UI state
  document.getElementById("formContainer").style.display = "none";
  cbShowMsg("Loading...");
}

function getYuiConfig(bundle_lib_files) {
  if (bundle_lib_files) {
    return {
      filter: "raw",
      combine: true,
      comboBase: '/static/combo/yui?',
      root: 'yui/build/',
      groups: {
        inputex: {
          combine: 'true',
          comboBase: '/static/combo/inputex?',
          root: 'src/'
        },
        yui2: {
          combine: true,
          comboBase: '/static/combo/2in3?',
          root: '2in3-master/dist/2.9.0/build/',
          patterns:  {
            'yui2-': {
              configFn: function(me) {
                if(/-skin|reset|fonts|grids|base/.test(me.name)) {
                  me.type = 'css';
                  me.path = me.path.replace(/\.js/, '.css');
                  me.path = me.path.replace(/\/yui2-skin/, '/assets/skins/sam/yui2-skin');
                }
              }
            }
          }
        }
      }
    }
  } else {
    return {
      filter: "raw",
      combine: false,
      base: '/static/yui_3.6.0/yui/build/',
      groups: {
        inputex: {
          base: '/static/inputex-3.1.0/src/'
        },
        yui2: {
          base: '/static/2in3/2in3-master/dist/2.9.0/build/',
          combine: false,
          patterns:  {
            'yui2-': {
              configFn: function(me) {
                if(/-skin|reset|fonts|grids|base/.test(me.name)) {
                  me.type = 'css';
                  me.path = me.path.replace(/\.js/, '.css');
                  me.path = me.path.replace(/\/yui2-skin/, '/assets/skins/sam/yui2-skin');
                }
              }
            }
          }
        }
      }
    }
  }
}

// here is the main method
function mainYuiFunction(Y) {

  // Add a new visu handler to inputEx, to look for a named function. It must
  // be a member of cb_global.inputEx.visus and should accept Y and the value of
  // the target field as its parameters. It should return the correct inputEx
  // widget initialized to render the given data.
  if (Y.inputEx.visus) {
    Y.inputEx.visus.funcName = function(options, value) {
      return cb_global.inputEx.visus[options.funcName](Y, value, cb_global);
    }
  }

  // here is the object schema
  var schema = {
    root : cb_global.schema
  };

  // inject inputex annotations
  cb_global.load_schema_with_annotations(schema);

  // build form definition from the json schema
  builder = new Y.inputEx.JsonSchema.Builder({
    'schemaIdentifierMap': schema
  });
  var inputExDefinition = builder.schemaToInputEx(schema.root);

  var editorControls = isFramed() ?
      new FramedEditorControls(Y, window.parent.frameProxy, cb_global) :
      new TopLevelEditorControls(Y, cb_global);

  // choose buttons to show
  var saveButton = editorControls.getSaveButton(Y);
  var closeButton = editorControls.getCloseButton(Y);
  var deleteButton = editorControls.getDeleteButton(Y);

  inputExDefinition.buttons = [];
  if (saveButton) {
    inputExDefinition.buttons.push(saveButton);
  }
  inputExDefinition.buttons.push(closeButton);
  if (deleteButton) {
    inputExDefinition.buttons.push(deleteButton);
  }

  // Disable the animated highlighting of list fields on reordering
  if (Y.inputEx.ListField) {
    Y.inputEx.ListField.prototype.arrowAnimColors = {
      'from': '',
      'to': ''
    };
  }

  // Enable the form to read the value of a file selection field
  if (Y.inputEx.FileField) {
    Y.inputEx.FileField.prototype.getValue = function() {
      return this.el.value;
    };
  }

  // create form and bind it to DOM
  inputExDefinition.parentEl = 'formContainer';
  cb_global.form = new Y.inputEx.Form(inputExDefinition);
  cb_global.form.form.setAttribute('id', 'cb-oeditor-form');

  editorControls.populateForm(Y);

  moveMarkedFormElementsOutOfFieldset(Y);
}

function isFramed() {
  return window.parent != window;
}

function TopLevelEditorControls(Y, env) {
  this._Y = Y;
  this._env = env;
}
TopLevelEditorControls.prototype = {
  getSaveButton: function() {
    if (! this._env.save_url || ! this._env.save_method) {
      return null;
    }
    return {
      type: 'submit-link',
      value: this._env.save_button_caption,
      className: 'inputEx-Button inputEx-Button-Submit-Link gcb-pull-left',
      onClick: {
        fn: this._onSaveClick,
        scope: this
      }
    };
  },

  _onSaveClick: function() {
    // Allow custom code to register a pre-save handler. If it returns 'false'
    // it will block further action.
    if (this._env.onSaveClick && this._env.onSaveClick() === false) {
      return false;
    }

    cbShowMsg("Saving...");
    disableAllControlButtons(this._env.form);

    // record current state
    this.lastSavedFormValue = this._env.form.getValue();

    // format request
    var requestSave = this._env.save_args;
    requestSave.payload = JSON.stringify(this.lastSavedFormValue);

    // append xsrf_token if provided
    if (this._env.xsrf_token) {
        requestSave.xsrf_token = this._env.xsrf_token;
    }

    // format request
    var requestData = {"request": JSON.stringify(requestSave)};

    // async post data to the server
    var url = this._env.save_url;

    var yioConfig;
    if (this._env.save_method == 'upload') {
      yioConfig = {
        method: 'POST',
        data: requestData,
        timeout: ajaxRpcTimeoutMillis,
        form: {
          id: 'cb-oeditor-form',
          upload: true
        },
        on: {
          complete: this._onXmlSaveComplete
        },
        context: this
      };
    } else {
      yioConfig = {
        method: 'PUT',
        data: requestData,
        timeout: ajaxRpcTimeoutMillis,
        on: {
          complete: this._onJsonSaveComplete
        },
        context: this
      };
    }

    this._Y.io(url, yioConfig);
    return false;
  },

  _onXmlSaveComplete: function(transactionId, response, args) {
    function extract(nodeName) {
      try {
        return response.responseXML.getElementsByTagName(nodeName)[0].textContent;
      } catch(e) {
        return null;
      }
    }

    var status = extract('status');
    var message = extract('message');
    var payload = extract('payload');

    this._onSaveComplete(status, message, payload);
  },

  _onJsonSaveComplete: function(transactionId, response, args) {
    try {
      var json = parseJson(response.responseText);
      this._onSaveComplete(json.status, json.message, json.payload);
    } catch(e) {
      this._onSaveComplete(null, null, null);
    }
  },

  _onSaveComplete: function(status, message, payload) {
    enableAllControlButtons(this._env.form)
    if (! status) {
      cbShowMsg("Server did not respond. Please reload the page to try again.");
      return;
    }

    if (status != 200) {
      cbShowMsg(formatServerErrorMessage(
          status, message));
      return;
    }

    // save lastSavedFormValue
    this._env.lastSavedFormValue = this.lastSavedFormValue;

    // If the REST handler returns a key value for an artifact
    // which previously had no key, update the form's key so as to
    // correctly reference the asset in future calls.
    if (payload) {
      var payload = JSON.parse(payload);
      if (payload.key && !this._env.save_args.key) {
        this._env.save_args.key = payload.key;
      }
    }

    // update UI
    if (this._env.auto_return) {
      cbShowMsg(message);
      var exit_url = this._env.exit_url;
      setTimeout(function() {
        window.location = exit_url;
      }, 750);
    } else {
      cbShowMsgAutoHide(message);
    }

    // Allow custom code to register a post-save handler.
    this._env.onSaveComplete && this._env.onSaveComplete(payload);
  },

  getCloseButton: function() {
    return {
      type: 'link', value: this._env.exit_button_caption,
      className: 'inputEx-Button inputEx-Button-Link gcb-pull-left',
      onClick: {
        fn: this._onCloseClick,
        scope: this
      }
    };
  },

  _onCloseClick: function(e) {
    // Allow custom code to register a pre-close handler. If it returns 'false'
    // it will block further action.
    if (this._env.onCloseClick && this._env.onCloseClick() === false) {
      return false;
    }

    disableAllControlButtons(this._env.form);
    if (deepEquals(this._env.lastSavedFormValue, this._env.form.getValue()) ||
        confirm("Abandon all changes?")) {
      window.location = this._env.exit_url;
    } else {
      enableAllControlButtons(this._env.form);
    }
  },

  getDeleteButton: function() {
    if (this._env.delete_url == '') {
      return null;
    }
    return {
      type: 'link',
      value: this._env.delete_button_caption,
      className: 'inputEx-Button inputEx-Button-Link gcb-pull-right',
      onClick: {
        fn: this._onDeleteClick,
        scope: this
      }
    }
  },

  _onDeleteClick: function(e) {
    // Allow custom code to register a pre-delete handler. If it returns 'false'
    // it will block further action.
    if (this._env.onDeleteClick && this._env.onDeleteClick() === false) {
      return false;
    }

    disableAllControlButtons(this._env.form);
    if (confirm(this._env.delete_message)) {
      if (this._env.delete_method == 'delete') {
        // async delete
        this._Y.io(this._env.delete_url, {
          method: 'DELETE',
          data: '',
          timeout : ajaxRpcTimeoutMillis,
          on: {
            success: this._onDeleteSuccess,
            failure: this._onDeleteFailure
          },
          context: this
        });
      } else {
        // form delete
        var form = document.createElement('form');
        form.method = this._env.delete_method;
        form.action = this._env.delete_url;
        document.body.appendChild(form);
        form.submit();
      }
    } else {
      enableAllControlButtons(this._env.form);
    }
  },

  _onDeleteSuccess: function(id, o, args) {
    enableAllControlButtons(this._env.form);
    var json = parseJson(o.responseText);
    if (json.status != 200) {
      cbShowMsg(formatServerErrorMessage(json.status, json.message));
      return;
    } else {
      window.location = this._env.exit_url;
    }

    // Allow custom code to register a post-delete handler.
    this._env.onDeleteSuccess && this._env.onDeleteSuccess(json);
  },

  _onDeleteFailure: function (x,o) {
    enableAllControlButtons(this._env.form);
    cbShowMsg("Server did not respond. Please reload the page to try again.");

    // Allow custom code to register a post-delete handler.
    this._env.onDeleteFailure && this._env.onDeleteFailure();
  },

  populateForm: function() {
    // async request data for the object being edited
    this._Y.io(this._env.get_url, {
      method: 'GET',
      timeout : ajaxRpcTimeoutMillis,
      on: {
        success: this._onPopulateFormSuccess,
        failure : this._onPopulateFormFailure
      },
      context: this
    });
  },

  _onPopulateFormSuccess: function(id, o, args) {
    var json = parseJson(o.responseText);

    // check status code
    if (json.status != 200) {
      cbShowMsg(formatServerErrorMessage(json.status, json.message));
      return;
    }

    // check payload
    if (!json.payload) {
      cbShowMsg("Server error; server sent no payload.");
      return
    }

    // push payload into form
    var payload = parseJson(json.payload);
    this._env.form.setValue(payload);

    // record xsrf token if provided
    if (json.xsrf_token) {
      this._env.xsrf_token = json.xsrf_token;
    } else {
      this._env.xsrf_token = null;
    }

    // TODO(jorr): Encapsulate cb_global.original and
    // cb_global.lastSavedFormValue in TopLevelEditorControls rather than
    // global scope
    this._env.original = payload;
    this._env.lastSavedFormValue = this._env.form.getValue();

    // update ui state
    document.getElementById("formContainer").style.display = "block";

    if (json.message) {
      cbShowMsgAutoHide(json.message);
    } else {
      cbHideMsg();
    }
    this._env.onFormLoad(this._Y);
  },

  _onPopulateFormFailure: function (x,o) {
    cbShowMsg("Server did not respond. Please reload the page to try again.");
  }
};
