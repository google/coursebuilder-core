//server communications timeout
var ajaxRpcTimeoutMillis = 15 * 1000;
// XSSI prefix. Must be kept in sync with models/transforms.py.
var xssiPrefix = ")]}'";

function cbShowMsg(text){
  var popup = document.getElementById("formStatusPopup");
  var message = document.getElementById("formStatusMessage");
  message.textContent = text;  // FF, Chrome
  message.innerText = text;    // IE
  popup.style.display = "block";
}

function cbHideMsg(){
  elem = document.getElementById("formStatusPopup");
  elem.style.display = "none";
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

/**
 * Parses JSON string that starts with an XSSI prefix.
 */
function parseJson(s) {
  return JSON.parse(s.replace(xssiPrefix, ''));
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

function keepPopupInView(Y) {
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
}

function onPageLoad(env) {
  YUI.add("gcb-rte", bindGcbRteField, '3.1.0', {
    requires: ['inputex-field', 'yui2-editor']
  });

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

/**
 * Define a rich text editor widget in the module "gcb-rte".
 */
function bindGcbRteField(Y) {

  var inputEx = Y.inputEx,
      Dom = Y.DOM;

  /**
   * Define a YUI class for a Google Course Builder rich text editor.
   */
  var GcbRteField = function(options) {
    GcbRteField.superclass.constructor.call(this, options);
  };

  /**
   * Define the methods of the GCB rich text editor here. They are bound
   * immediately below.
   */
  var gcbRteDefs = {
    setOptions: function(options) {
      GcbRteField.superclass.setOptions.call(this, options);
      this.options.opts = options.opts || {};
      this.options.editorType = options.editorType;
    },
    renderComponent: function() {
      var self = this;

      // Make a unique id for the field
      if (!GcbRteField.idCounter) {
        GcbRteField.idCounter = 0;
      }
      var id = "gcbRteField-" + GcbRteField.idCounter;
      GcbRteField.idCounter += 1;

      // Insert the text area for plain text editing
      var attributes = {id: id};
      if(this.options.name) {
        attributes.name = this.options.name;
      }
      this.el = inputEx.cn('textarea', attributes);
      this.fieldContainer.appendChild(this.el);

      // Make a button to toggle between plain text and rich text
      var showRteText = "Rich Text";
      var hideRteText = "Plain Text";
      var showRteFlag = false;
      var toggle = document.createElement("div");
      var toggleText = document.createTextNode(showRteText);
      toggle.appendChild(toggleText);
      Dom.addClass(toggle, "rte-control");
      toggle.onclick = function() {
        showRteFlag = !showRteFlag;
        if (showRteFlag) {
          if (self.editor) {
            showExistingRte(self);
          } else {
            showNewRte(self);
          }
          toggleText.nodeValue = hideRteText;
        } else {
          hideRte(self);
          toggleText.nodeValue = showRteText;
        }
      };
      this.divEl.appendChild(toggle);

      // The methods for switching between plain text and rich text editing:

      function showNewRte(rteField) {
        var options = rteField.options;
        var _def = {
          height: '300px',
          width: '500px',
          dompath: true,
        };
        // Merge options.opts into the default options
        var opts = options.opts;
        for (var i in opts) {
          if (Y.Lang.hasOwnProperty(opts, i)) {
            _def[i] = opts[i];
          }
        }

        var editor = new Y.YUI2.widget.SimpleEditor(id, _def);

        // Disable any HTML cleaning done by the editor.
        editor.cleanHTML = function(html) {
          if (!html) {
              html = this.getEditorHTML();
          }
          this.fireEvent('cleanHTML',
              {type: 'cleanHTML', target: this, html: html});
          return html;
        };
        editor._cleanIncomingHTML = function(html) {
          return html;
        };
        editor._fixNodes = function() {};

        rteField.editor = editor;
        rteField.editor.render();
      }

      function showExistingRte(rteField) {
        var editor = rteField.editor,
            textArea = rteField.el;
            rteDiv = textArea.previousSibling;

        if (rteField._cbGetValue) {
          rteField.getValue = rteField._cbGetValue;
        }

        Dom.setStyle(rteDiv, 'position', 'static');
        Dom.setStyle(rteDiv, 'top', '0');
        Dom.setStyle(rteDiv, 'left', '0');
        Dom.setStyle(textArea, 'visibility', 'hidden');
        Dom.setStyle(textArea, 'top', '-9999px');
        Dom.setStyle(textArea, 'left', '-9999px');
        Dom.setStyle(textArea, 'position', 'absolute');
        editor.get('element_cont').addClass('yui-editor-container');
        editor._setDesignMode('on');
        editor.setEditorHTML(textArea.value);
      }

      function hideRte(rteField) {
        var editor = rteField.editor,
            textArea = rteField.el;
            rteDiv = textArea.previousSibling;

        editor.saveHTML();

        rteField._cbGetValue = rteField.getValue;
        rteField.getValue = function() {
          return textArea.value;
        };

        Dom.setStyle(rteDiv, 'position', 'absolute');
        Dom.setStyle(rteDiv, 'top', '-9999px');
        Dom.setStyle(rteDiv, 'left', '-9999px');
        editor.get('element_cont').removeClass('yui-editor-container');
        Dom.setStyle(textArea, 'visibility', 'visible');
        Dom.setStyle(textArea, 'top', '');
        Dom.setStyle(textArea, 'left', '');
        Dom.setStyle(textArea, 'position', 'static');
        Dom.addClass(textArea, 'raw-text-editor');
      }
    },
    setValue: function(value, sendUpdatedEvt) {
      this.el.value = value;
      if(sendUpdatedEvt !== false) {
        this.fireUpdatedEvt();
      }
    },
    getValue: function() {
      if (this.editor) {
        return this.editor.saveHTML();
      } else {
        return this.el.value;
      }
    }
  };
  Y.extend(GcbRteField, inputEx.Field, gcbRteDefs);
  inputEx.registerType("html", GcbRteField, []);
};

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
    keepPopupInView(Y);
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

  // save button
  var saveButton = {type: 'submit-link', value: cb_global.save_button_caption, onClick: function() {
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
                setTimeout(function(){
                  cbHideMsg();
                  if (cb_global.auto_return) {
                    window.location = cb_global.exit_url;
                  }
                }, 5000);
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

        Y.io(url, yioConfig);
        return false;
  }};

  // close button
  var closeButton = {type: 'link', value: cb_global.exit_button_caption, onClick:function(e) {
      if (deepEquals(cb_global.lastSavedFormValue, cb_global.form.getValue()) ||
          confirm("Abandon all changes?")) {
        window.location = cb_global.exit_url;
      }
  }};

  // delete button
  var deleteButton = {type: 'link', value: 'Delete',
      className: 'inputEx-Button inputEx-Button-Link pull-right',
      onClick:function(e) {
          if (confirm("Are you sure you want to delete this " + 
                cb_global.type_label + "?")) {
              if (cb_global.delete_method == 'delete') {
                // async delete
                Y.io(cb_global.delete_url, {
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
      }
  };

  // choose buttons to show
  inputExDefinition.buttons = [];
  if (cb_global.save_url && cb_global.save_method) {
    inputExDefinition.buttons.push(saveButton);
  }
  inputExDefinition.buttons.push(closeButton);
  if (cb_global.delete_url != '') {
    inputExDefinition.buttons.push(deleteButton);
  }

  // Disable the animated highlighting of list fields on reordering
  if (Y.inputEx.ListField) {
    Y.inputEx.ListField.prototype.arrowAnimColors = {
      'from': '',
      'to': ''
    };
  }

  // create form and bind it to DOM
  inputExDefinition.parentEl = 'formContainer';
  cb_global.form = new Y.inputEx.Form(inputExDefinition);
  cb_global.form.form.setAttribute('id', 'cb-oeditor-form');

  moveMarkedFormElementsOutOfFieldset(Y);

  // async request data for the object being edited
  Y.io(cb_global.get_url, {
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

        // save lastSavedFormValue
        cb_global.original = payload;
        cb_global.lastSavedFormValue = payload;

        // it is better to set lastSavedFormValue to a cb_global.form.getValue(),
        // but it does not work for rich edit control as it has delayed loading
        // and may not be ready when this line above is executed

        // update ui state
        document.getElementById("formContainer").style.display = "block";
        cbShowMsg(json.message);
        setTimeout(function(){ cbHideMsg(); }, 5000);
      },
      failure : function (x,o) {
          cbShowMsg("Server did not respond. Please reload the page to try again.");
      }
    }
  });
}
