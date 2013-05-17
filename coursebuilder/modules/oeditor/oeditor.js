//server communications timeout
var ajaxRpcTimeoutMillis = 15 * 1000;
// XSSI prefix. Must be kept in sync with models/transforms.py.
var xssiPrefix = ")]}'";

function ButterBar(popup, message) {
  this.popup = popup;
  this.message = message;
}
ButterBar.prototype.showMessage = function(text) {
  this.message.textContent = text;  // FF, Chrome
  this.message.innerText = text;    // IE
  this.popup.style.display = "block";
};
ButterBar.prototype.hide = function() {
  this.popup.style.display = "none";
};
ButterBar.getButterBar = function() {
  return new ButterBar(document.getElementById("formStatusPopup"),
    document.getElementById("formStatusMessage"));
};
ButterBar.keepInView = function(Y) {
  var container = Y.one('#oeditor-container');
  var popup = Y.one('#formStatusPopup');
  // The 'absolute' style positions the popup 45px above the top of the
  // container and we want 'fixed' to pin it at 10px below the top of the
  // window, so check that the container isn't less than 55px from the top of
  // the window.
  if (container.getY() - container.get('docScrollY') <= 55) {
    popup.addClass('fixed');
    popup.removeClass('absolute');
  } else {
    popup.removeClass('fixed');
    popup.addClass('absolute');
  }
};
function cbShowMsg(text){
  ButterBar.getButterBar().showMessage(text);
}
function cbHideMsg(){
  ButterBar.getButterBar().hide();
}

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

function getAddCustomTagUrl(env, tagName) {
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
      Y.extend(GcbRteField, Y.inputEx.Field,
          getGcbRteDefs(env, Y.DOM, Y.YUI2.widget.SimpleEditor));
      Y.inputEx.registerType("html", GcbRteField, []);
    },
    '3.1.0',
    {requires: ['inputex-field', 'yui2-editor']}
  );

  YUI(getYuiConfig(env.bundle_lib_files)).use(
    env.required_modules,
    mainYuiFunction);

  document.getElementById("close-status-popup-button").onclick = cbHideMsg;

  env.inputEx = env.inputEx || {};
  env.inputEx.visus = env.inputEx.visus || {};
  env.inputEx.visus.renderAsset = renderAsset;

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
      return cb_global.inputEx.visus[options.funcName](Y, value);
    }
  }

  Y.on('scroll', function(e) {
    ButterBar.keepInView(Y);
  });

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
      new FramedEditorControls(window.parent.frameProxy, cb_global) :
      new TopLevelEditorControls(Y);

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

function TopLevelEditorControls(Y) {
  this._Y = Y;
}
TopLevelEditorControls.prototype = {
  getSaveButton: function() {
    var that = this;
    if (cb_global.save_url && cb_global.save_method) {
      return {type: 'submit-link', value: cb_global.save_button_caption, onClick: function() {
        cbShowMsg("Saving...");

        // record current state
        var lastSavedFormValue = cb_global.form.getValue();

        // format request
        var requestSave = cb_global.save_args;
        requestSave.payload = JSON.stringify(lastSavedFormValue);

        // append xsrf_token if provided
        if (cb_global.xsrf_token) {
            requestSave.xsrf_token = cb_global.xsrf_token;
        }

        // format request
        var requestData = {"request": JSON.stringify(requestSave)};

        // async post data to the server
        var url = cb_global.save_url;

          yioConfig = {
            method: 'PUT',
            data: requestData,
            timeout : ajaxRpcTimeoutMillis,
            on: {
                complete: function(transactionId, response, args) {
                  var json;
                  if (response && response.responseText) {
                    json = parseJson(response.responseText);
                  } else {
                    cbShowMsg("Server did not respond. Please reload the page to try again.");
                    return;
                  }

                if (json.status != 200) {
                  cbShowMsg(formatServerErrorMessage(json.status, json.message));
                  return;
                }

                // save lastSavedFormValue
                cb_global.lastSavedFormValue = lastSavedFormValue;

                  // update UI
                  cbShowMsg(json.message);
                  if (cb_global.auto_return) {
                    setTimeout(function() {
                      window.location = cb_global.exit_url;
                    }, 750);
                  } else {
                    setTimeout(function() {
                      cbHideMsg();
                    }, 5000);
                  }
                }
            }
          };

          if (cb_global.save_method == 'upload') {
            yioConfig.method = 'POST';
            yioConfig.form = {
              id: 'cb-oeditor-form',
              upload: true
            };
          }

          that._Y.io(url, yioConfig);
          return false;
        }};
    } else {
      return null;
    }
  },

  getCloseButton: function() {
    return {type: 'link', value: cb_global.exit_button_caption, onClick:function(e) {
      if (deepEquals(cb_global.lastSavedFormValue, cb_global.form.getValue()) ||
              confirm("Abandon all changes?")) {
            window.location = cb_global.exit_url;
          }
      }};
  },

  getDeleteButton: function() {
    var that = this;
    if (cb_global.delete_url != '') {
      return {type: 'link', value: 'Delete',
        className: 'inputEx-Button inputEx-Button-Link gcb-pull-right',
        onClick:function(e) {
            if (confirm("Are you sure you want to delete this " +
                cb_global.type_label + "?")) {
              if (cb_global.delete_method == 'delete') {
                // async delete
                that._Y.io(cb_global.delete_url, {
                  method: 'DELETE',
                  timeout : ajaxRpcTimeoutMillis,
                  on: {
                    success: function(id, o, args) {
                      var json = parseJson(o.responseText);
                      if (json.status != 200) {
                        cbShowMsg(formatServerErrorMessage(json.status, json.message));
                        return;
                      } else {
                        window.location = cb_global.exit_url;
                      }
                    },
                    failure : function (x,o) {
                      cbShowMsg("Server did not respond. Please reload the page to try again.");
                    }
                  }
                });
              } else {
                // form delete
                var form = document.createElement('form');
                form.method = cb_global.delete_method;
                form.action = cb_global.delete_url;
                document.body.appendChild(form);
                form.submit();
              }
            }
          }};
    } else {
      return null;
    }
  },

  populateForm: function() {
    // async request data for the object being edited
    this._Y.io(cb_global.get_url, {
      method: 'GET',
      timeout : ajaxRpcTimeoutMillis,
      on: {
        success: function(id, o, args) {
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
          cb_global.form.setValue(payload);

          // record xsrf token if provided
          if (json.xsrf_token) {
            cb_global.xsrf_token = json.xsrf_token;
          } else {
            cb_global.xsrf_token = null;
          }

          // TODO(jorr): Encapsulate cb_global.original and
          // cb_global.lastSavedFormValue in TopLavelEditorControls rather than
          // global scope
          cb_global.original = payload;
          cb_global.lastSavedFormValue = payload;

          // it is better to set lastSavedFormValue to a cb_global.form.getValue(),
          // but it does not work for rich edit control as it has delayed loading
          // and may not be ready when this line above is executed

          // update ui state
          document.getElementById("formContainer").style.display = "block";

          if (json.message) {
            cbShowMsg(json.message);
            setTimeout(function(){ cbHideMsg(); }, 5000);
          } else {
            cbHideMsg();
          }
          cb_global.onFormLoad();
        },
        failure : function (x,o) {
            cbShowMsg("Server did not respond. Please reload the page to try again.");
        }
      }
    });
  }
};
