//server communications timeout
var ajaxRpcTimeoutMillis = 45 * 1000;
// XSSI prefix. Must be kept in sync with models/transforms.py.
var xssiPrefix = ")]}'";

var URL_VALIDATION_REGEX =
  '(^(http:\/\/|https:\/\/|\/\/|\/).*$)|(^[^.\/]*(\/.*)?$)';

/**
 * Utility class for an on/off toggle button.
 *
 * @class
 */
function ToggleButton(label, className) {
  var that = this;

  this.root = $('<label></label>');
  this.root.addClass('gcb-toggle-button gcb-toggle-button--alone').addClass(
    className).text(label);

  this.checkbox = $('<input type="checkbox">');
  this.root.append(this.checkbox);
  this.checkbox.click(function() {
    that._updateClass();
    if (this.checked) {
      that.onSelect && that.onSelect();
    } else {
      that.onDeselect && that.onDeselect();
    }
  });
}
/**
 * Return the root element of the togglebutton.
 *
 * @method
 * @return {Element} The root element.
 */
ToggleButton.prototype.getRoot = function() {
  return this.root.get(0);
};
/**
 * Set the handlers for selected and deselected click events.
 *
 * @method
 * @param onSelect {function} Called when the click leaves the button selected.
 * @param onDeselect {function} Called when the click leaves the button
 *     deselected.
 */
ToggleButton.prototype.onClick = function(onSelect, onDeselect) {
  this.onSelect = onSelect;
  this.onDeselect = onDeselect;
};
/**
 * Set the state of the button.
 *
 * @method
 * @param selected {boolean} The selected (deselected) state.
 */
ToggleButton.prototype.set = function(selected) {
  this.checkbox.prop('checked', selected);
  this._updateClass();
};
ToggleButton.prototype._updateClass = function() {
  if (this.checkbox.prop('checked')) {
    this.root.addClass('selected');
  } else {
    this.root.removeClass('selected');
  }
};

/**
 * Utility class to build a very simple tabbar and to fire callback functions
 * on each button press.
 *
 * @class
 */
function TabBar(className) {
  this.root = $('<div></div>');
  className = className || 'tabbar';
  this.root.addClass(className);
}
/**
 * Add a new button to the tab bar.
 *
 * @method
 * @param label {string} The label to be displayed on the tab button
 * @param onclick {function} A zero-args callback which is called when the
 *     button is clicked.
 */
TabBar.prototype.addTab = function(label, className, onclick) {
  var that = this;
  var button = $('<button></button>');
  button.click(function() {
    that._select($(this));
    onclick();
    return false;
  });
  button.addClass(className).text(label);
  this.root.append(button);
};
/**
 * Return the root element of the tab bar.
 *
 * @method
 * @return {Element} The root element.
 */
TabBar.prototype.getRoot = function() {
  return this.root.get(0);
};
/**
 * Select the button with given index. Note the callback function will not fire.
 *
 * @method
 * @param index {number} Zero-based index of the button.
 */
TabBar.prototype.selectTabByIndex = function(index) {
  this._select(this.root.find('> button').eq(index));
};
/**
 * Select the button with given label. Note the callback function will not fire.
 *
 * @method
 * @param label {string} The label of the button to be selected.
 */
TabBar.prototype.selectTabByLabel = function(label) {
  this._select(this.root.find('> button').filter(function() {
    return $(this).text() === label;
  }));
};
TabBar.prototype._select = function(button) {
  this.root.find('> button').removeClass('selected');
  button.addClass('selected');
}

/**
 * Perform the given action, or not, depending on the decision made by the
 * decider function. The decider can return "yes" (boolean true), "no" (boolean
 * false), or "maybe" (a promise). If it returns a promise the action is
 * performed if and when the promise is resolved. If no decider is provided, the
 * action is performed by default.
 *
 * @param decider {Function} A zero-args function which returns either boolean
       or a promise.
 * @param action {Function} A zero-args function which is conditionally
       executed.
 */
function maybePerformAction(decider, action) {
  if (! decider) {
    action();
    return;
  }
  var decision = decider();
  if (typeof decision == 'boolean') {
    if (decision == true) {
      action();
    }
    return;
  }
  if (decision.then) {
    decision.then(function() {
      action();
    });
  }
}

function setQuestionDescriptionIfEmpty(quForm) {
  var descriptionField = quForm.getFieldByName('description');
  var description = descriptionField.getValue();
  if (description !== null && description.trim() !== '') {
    return;
  }
  var questionField = quForm.getFieldByName('question');
  var questionText = $('<div></div>').html(questionField.getValue()).text();
  var maxSize = 60;
  var truncated = questionText.length <= maxSize
      ? questionText
      : (questionText.slice(0, maxSize - 3) + '...')

  descriptionField.setValue(truncated);
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
  var div = document.createElement('div');

  // If loc is null after the execution of the loop checking for allowed
  // image asset file extensions, it is assumed that a match was not found,
  // and the new asset case needs to be handled.
  var found = false;

  // The first item in the render div is a "location", which is either a link
  // to the existing image asset or, for the new image upload case, a link
  // back to the "Create > Images" list page.
  var loc = document.createElement('a');
  loc.setAttribute('target', '_blank');
  loc.appendChild(document.createTextNode(uri));
  div.appendChild(loc);
  div.appendChild(document.createElement('br'));

  // One way or another, the enclosing render div will contain a description
  // as the last element.
  var desc = document.createElement('div');
  desc.setAttribute('class', 'inputEx-description');

  // Normally the description would not be created inside a visualization, and
  // it would get a similar ID to the other parts of the field.  However, that
  // ID is not passed down here.  We need a unique ID to display a tooltip
  // though, so we make up a new one.
  desc.setAttribute('id', Y.guid() + '-desc');

  // Compare the tail end of the uri to allowed image asset file extensions.
  imageExts = ['.png', '.jpg', '.jpeg', '.gif'];
  for (i in imageExts) {
    var ext = imageExts[i];
    if ((uri.length > ext.length) && uri.toLowerCase().endsWith(ext)) {
      // uri matches one of the valid image asset file extensions, so assume
      // it points to an existing image asset.
      found = true;
      // Insert a "preview" of the existing image asset that will be replaced.
      // ("Preview" because CSS is used to cap the maximum displayed size.)
      var img = document.createElement('img');
      img.setAttribute('src', uri);
      img.setAttribute('class', 'framed'); // img.framed caps max-width.
      div.appendChild(img);
      div.appendChild(document.createElement('br'));
      // Customize the "helper text" in the description div to the specific
      // case of replacing an existing image asset.
      desc.appendChild(document.createTextNode(
          "A preview of the existing image that will be replaced."));
      // Set the loc link target to that existing image asset.
      loc.setAttribute('href', uri);
      loc.setAttribute('title',
                       "Opens this existing image in a new browser tab.");
      break;
    }
  }
  if (!found) {
    // uri did not match one of the valid image asset file extensions, so
    // this is not the "replacing an existing asset" case.
    desc.appendChild(document.createTextNode(
        "Destination for a new uploaded image, which must not have the same" +
        " name as any existing image."));
    desc.appendChild(document.createElement('br'));
    desc.appendChild(document.createTextNode(
        "To override an existing image, select that image from the previous "));
    var images = document.createElement('a');
    images.setAttribute('href', "dashboard?action=edit_images");
    images.setAttribute('target', '_blank');
    images.appendChild(document.createTextNode("Create > Images"));
    desc.appendChild(images);
    desc.appendChild(document.createTextNode(" list."));
    loc.setAttribute('href', "dashboard?action=edit_images");
    loc.setAttribute('title',
                     "Opens the Create > Images list in a new browser tab.");
  }
  // Return a completed render div after appending an always-last description.
  div.appendChild(desc);
  return div;
}

function renderImage(Y, url) {
  var img = document.createElement('img');
  img.src = url;
  return img;
}

/**
 * Expose a method to disable the save button by means of an annotation in the
 * schema. Use the 'uneditable' schema type with visuType=funcName and
 * funcName=disableSave.
 *
 * @param {YUI Root} Y the current YUI root object
 * @param {string} value the value of the uneditable schema field
 * @param {object} env the CB environment table
 */
function disableSave(Y, value, env) {
  setTimeout(function() {
    // Timeout is needed because this function is called during the setup of
    // env.form and so the variable is not set until the end of the execution
    // thread.
    for (var i = 0; i < env.form.buttons.length; i++) {
      var button = env.form.buttons[i];
      if (button.options.type == 'submit-link') {
        env.form.buttons[i].disable();
      }
    }
  }, 0);
  var div = document.createElement('div');
  div.innerHTML = value;
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
  var splits = Y.all('div.split-from-main-group').each(function(splitItem){
    // InputEx puts the class name on the div which contains the input element
    // but we really want to work with the parent.
    var splitFromMainGroupParent = splitItem.get('parentNode');
    splitFromMainGroupParent.addClass('split-from-main-group-parent');
    Y.one('#cb-oeditor-form').insertBefore(splitFromMainGroupParent,
      Y.one('#cb-oeditor-form > div.inputEx-Form-buttonBar'));
  });
}

function addRequiredFieldsMessage(Y) {
  var buttonBar = Y.one('#cb-oeditor-form > div.inputEx-Form-buttonBar');
  var requiredFieldsMessage = '<div class="required-fields-message">' +
      'Fields marked with an asterisk (<span class="asterisk">*</span>) ' +
      'are required.' +
      '</div>';
  Y.one('#cb-oeditor-form').insertBefore(requiredFieldsMessage, buttonBar);
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

function startValueLoad(env) {
  if (!isFramed()) {
    // Kick of early asynchronous loading of the editor content while the rest
    // of the JS is initializing.
    disableAllControlButtons(env.form);
    env.get_url_promise = $.ajax({
      type: 'GET',
      url: env.get_url,
      dataType: 'text'
    });
  }
}

function onPageLoad(env) {
  startValueLoad(env);
  /**
   * Define a rich text editor widget in the module "gcb-rte".
   */
  YUI.add('gcb-rte', bindEditorField, '3.1.0', {
    requires: ['inputex-field', 'yui2-editor', 'yui2-resize']
  });
  YUI.add('gcb-code', bindCodeField, '3.1.0', {
    requires: ['inputex-field', 'yui2-resize']
  });
  YUI.add('gcb-uneditable', bindUneditableField, '3.1.0', {
    requires: ['inputex-uneditable']
  });
  YUI.add('gcb-datetime', bindDatetimeField, '3.1.0', {
    requires: ['inputex-datetime']
  });
  YUI.add("gcb-checkbox-list", bindCheckboxListField, '3.1.0', {
    requires: ['inputex-checkbox']
  });
  YUI.add("gcb-array-select", bindArraySelectField, '3.1.0', {
    requires: ['inputex-select']
  });
  YUI(getYuiConfig(env.bundle_lib_files)).use(
    env.required_modules,
    mainYuiFunction);

  env.inputEx = env.inputEx || {};
  env.inputEx.visus = env.inputEx.visus || {};
  env.inputEx.visus.renderAsset = renderAsset;
  env.inputEx.visus.renderImage = renderImage;
  env.inputEx.visus.disableSave = disableSave;

  // set initial UI state
  document.getElementById("formContainer").style.display = "none";
  cbShowMsg("Loading...");
  setupTooltips();
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
          root: 'src/',
          base: '/static/inputex-3.1.0/src/'
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

/**
 * Returns a message if there are unsaved changes in the form. Returns null
 * otherwise.
 */
function alertIfNotSavedChanges(cb_global) {
  if (cb_global.is_deleted) {
    return null;
  }
  if (deepEquals(cb_global.lastSavedFormValue, cb_global.form.getValue())) {
    return null;
  } else {
    return "You have unsaved changes that will be lost if you leave.";
  }
}

// here is the main method
function mainYuiFunction(Y) {

  // Override inputEx behavior for URL fields
  Y.inputEx.regexps.url = URL_VALIDATION_REGEX;
  Y.inputEx.messages.invalidUrl =
    'Links to other sites must start with "http" or "https".';
  Y.inputEx.messages.required = null;

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
      new FramedEditorControls(Y, window.parent.frameProxy, cb_global,
          maybePerformAction, alertIfNotSavedChanges) :
      new TopLevelEditorControls(Y, cb_global);
  cb_global.editorControls = editorControls;

  // choose buttons to show
  var saveButton = editorControls.getSaveButton(Y);
  var closeButton = editorControls.getCloseButton(Y);
  var deleteButton = editorControls.getDeleteButton(Y);

  inputExDefinition.buttons = [];
  if (saveButton) {
    inputExDefinition.buttons.push(saveButton);
  }
  if (closeButton) {
    inputExDefinition.buttons.push(closeButton);
  }
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

  // Patch InputEx.Field to keep a copy of all the config options it was passed.
  // This enables extra schema data to be attached to the form elements.
  if (Y.inputEx.Field) {
    Y.inputEx.Field.prototype._origSetOptions =
        Y.inputEx.Field.prototype.setOptions;
    Y.inputEx.Field.prototype.setOptions = function(options) {
      this.allOptions = options;
      this._origSetOptions(options);
    };
  }

  // create form and bind it to DOM
  inputExDefinition.parentEl = 'formContainer';
  cb_global.form = new Y.inputEx.Form(inputExDefinition);
  cb_global.form.form.setAttribute('id', 'cb-oeditor-form');

  editorControls.populateForm(Y);

  moveMarkedFormElementsOutOfFieldset(Y);
  addRequiredFieldsMessage(Y);
  tooltipifyHelpText();

  // Show a confirmation box if there are unsaved changes.
  if (! isFramed()) {
    window.onbeforeunload = function () {
      return alertIfNotSavedChanges(cb_global);
    };
  }
}

function isFramed() {
  return window.parent != window && window.parent.frameProxy;
}

function TopLevelEditorControls(Y, env) {
  this._Y = Y;
  this._env = env;
}
TopLevelEditorControls.prototype = {
  getSaveButton: function() {
    var that = this;
    if (! this._env.save_url || ! this._env.save_method) {
      return null;
    }
    return {
      type: 'submit-link',
      value: this._env.save_button_caption,
      className: 'inputEx-Button inputEx-Button-Submit-Link gcb-pull-left',
      onClick: function() {
        maybePerformAction(that._env.onSaveClick, function() {
          that._onSaveClick();
        });
        return false;
      }
    };
  },

  _onSaveClick: function() {
    var valid = this._env.validate
        ? this._env.validate() : this._env.form.validate();
    if (! valid) {
      cbShowMsg('Cannot save because some required fields have not been set.');
      return;
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

  _getEditorFieldState: function() {
    var editorFieldConstructor = this._Y.inputEx.getFieldClass('html');
    var groupConstructor = this._Y.inputEx.getFieldClass('group');
    var listConstructor = this._Y.inputEx.getFieldClass('list');

    var inputs = this._env.form.inputsNames;
    var state = {};

    doRecursion(inputs, state);
    return state;

    function doRecursion(inputs, state) {
      for (var name in inputs) {
        if (inputs.hasOwnProperty(name)) {
          var field = inputs[name];
          if (field.constructor === groupConstructor) {
            state[name] = {};
            doRecursion(field.inputsNames, state[name]);
          } else if (field.constructor === listConstructor) {
            state[name] = [];
            doRecursion(field.subFields, state[name]);
          } else if (field.constructor === editorFieldConstructor) {
            state[name] = {editorType: field.getEditorType()};
          }
        }
      }
    }
  },

  _storeEditorFieldState: function() {
    var state = this._getEditorFieldState();
    var request = {
      xsrf_token: this._env.editor_prefs.xsrf_token,
      payload: JSON.stringify({
        location: this._env.editor_prefs.location,
        key: this._env.save_args.key,
        state: state
      })
    };
    this._Y.io('oeditor/rest/editor_prefs', {
      method: 'POST',
      data: {request: JSON.stringify(request)}
    })
  },

  _restoreEditorFieldState: function() {
    var that = this;
    var editorFieldConstructor = this._Y.inputEx.getFieldClass('html');
    var groupConstructor = this._Y.inputEx.getFieldClass('group');
    var listConstructor = this._Y.inputEx.getFieldClass('list');

    var inputs = this._env.form.inputsNames;

    doRecursion(inputs, this._env.editor_prefs.prefs || {});

    function doRecursion(inputs, state) {
      for (var name in inputs) {
        if (inputs.hasOwnProperty(name)) {
          var field = inputs[name];
          var prefs = state[name] || {};
          if (field.constructor === groupConstructor) {
            doRecursion(field.inputsNames, prefs);
          } else if (field.constructor == listConstructor) {
            doRecursion(field.subFields, prefs);
          } else if (field.constructor === editorFieldConstructor) {
            setEditorFieldState(field, prefs);
          }
        }
      }
    }

    function setEditorFieldState(field, fieldPrefs) {
      var editorType = fieldPrefs.editorType;
      if (! editorType) {
        if (field.getValue()) {
          editorType = editorFieldConstructor.prototype.HTML_EDITOR;
        } else {
          editorType = editorFieldConstructor.prototype.RICH_TEXT_EDITOR;
        }
      }
      field.setEditorType(editorType);
    }
  },

  _lockDisabledFields: function() {
    // InputEx does not provide full support for disabling parts of a form, so
    // we run through the tree and explicitly disable all fields maked with
    // "disabled" flag, together with their children
    function doRecursion(inputs, parentDisabled) {
      for (var name in inputs) {
        if (inputs.hasOwnProperty(name)) {
          var field = inputs[name];
          var disabled = parentDisabled || field.allOptions.disabled;

          if (field.inputsNames) {
            // An InputEx.Group
            doRecursion(field.inputsNames, disabled);
          } else if (field.subFields) {
            // And InputEx.ListField
            if (disabled) {
              disableListFieldControls(field);
            }
            doRecursion(field.subFields, disabled);
          } else {
            if (disabled) {
              field.disable();
            }
          }
        }
      }
    }

    function disableListFieldControls(field) {
      $(field.addButton).hide();
      $(field.fieldContainer).find('> .inputEx-ListField-childContainer ' +
          '> div > .inputEx-List-link').hide();
    }

    doRecursion(this._env.form.inputsNames, false);
  },

  _onSaveComplete: function(status, message, payload) {
    enableAllControlButtons(this._env.form);
    if (! status) {
      cbShowMsg("Server did not respond. Please reload the page to try again.");
      return;
    }

    if (status != 200) {
      cbShowMsg(formatServerErrorMessage(status, message));
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

    // Also store the state of the EditorField tabs. (Note this must come after
    // save_args.key is updated.)
    this._storeEditorFieldState();

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
    var that = this;
    if (this._env.exit_url == '') {
      return null;
    }
    return {
      type: 'link', value: this._env.exit_button_caption,
      className: 'inputEx-Button inputEx-Button-Link gcb-pull-left',
      onClick: function() {
        maybePerformAction(that._env.onCloseClick, function() {
          that._onCloseClick();
        });
        return false;
      }
    };
  },

  _onCloseClick: function(e) {
    window.location = cb_global.exit_url;
  },

  getDeleteButton: function() {
    var that = this;
    if (this._env.delete_url == '') {
      return null;
    }
    return {
      type: 'link',
      value: this._env.delete_button_caption,
      className: 'inputEx-Button inputEx-Button-Link gcb-pull-right',
      onClick: function() {
        maybePerformAction(that._env.onDeleteClick, function() {
          that._onDeleteClick();
        });
        return false;
      }
    }
  },

  _onDeleteClick: function(e) {
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
      this._env.is_deleted = true;
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
    var that = this;
    // Retrieve editor content from the asynchronous load started in onPageLoad.
    this._env.get_url_promise
        .done(function(responseText) {
          that._onPopulateFormSuccess(responseText);
        })
        .error(function() {
          that._onPopulateFormFailure();
        });
  },

  _onPopulateFormSuccess: function(responseText) {
    var json = parseJson(responseText);

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
    this._lockDisabledFields();
    this._restoreEditorFieldState();

    // InputEx sets classes on invalid fields on load but we want this only
    // on submit
    this._Y.all('.inputEx-invalid').removeClass('inputEx-invalid');

    // Put some hints on the field wrapper divs about what type of input field
    // is being used.
    var FIELD_WRAPPER_SEL = 'div.new-form-layout div.inputEx-fieldWrapper';
    var TEXT_INPUT_SEL = '> div.inputEx-Field ' +
        '> div.inputEx-StringField-wrapper > input[type=text]';
    var CHECKBOX_SEL = '> div.inputEx-Field.inputEx-CheckBox ' +
        '> input[type=checkbox]';
    var SELECT_SEL = '> div.inputEx-Field > select';
    this._Y.all(FIELD_WRAPPER_SEL).each(function(node) {
      if (node.one(TEXT_INPUT_SEL)) {
        node.addClass('gcb-text-input');
      } else if (node.one(CHECKBOX_SEL)) {
        node.addClass('gcb-checkbox-input');
      } else if (node.one(SELECT_SEL)) {
        node.addClass('gcb-select');
      }
    });

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

    cb_global.form.on('updated', function(event) {
      tooltipifyHelpText();
    });
    enableAllControlButtons(this._env.form);
  },

  _onPopulateFormFailure: function () {
    cbShowMsg("Server did not respond. Please reload the page to try again.");
    enableAllControlButtons(this._env.form);
  }
};

function getPotentialHeight(element) {
  // Calculate a height for an element so that it fills up all remaining
  // vertical space in the page.
  var extraSpace = Math.max(200, verticalExtraPageSpace());
  return $(element).height() + extraSpace;
}

function verticalExtraPageSpace() {
  // Find out how much unused space is left on this page right now
  return $(window).height() - $(document.documentElement).height();
}

function isNewFormLayout(){
  var SCHEMA = cb_global.schema;
  return (SCHEMA._inputex && SCHEMA._inputex.className
    && SCHEMA._inputex.className.indexOf('new-form-layout') > -1)
}

// Tooltips

function tooltipifyHelpText() {
  $('.inputEx-description').each(function(){
    var original = $(this);
    var label = original.closest('.inputEx-fieldWrapper').find(
      '.inputEx-label').eq(0);

    var icon = $(
      '<div class="icon material-icons gcb-form-help-icon">help</div>');
    icon.attr({id: original.attr('id')});

    var tip = $('<div class="mdl-tooltip gcb-form-tooltip"></div>');
    tip.attr({'for': original.attr('id')});
    tip.html(original.html());

    label.prepend(icon);
    label.prepend(tip);
    original.remove();
  });
  window.componentHandler.upgradeAllRegistered();
}

function setupTooltips() {
  function removeTooltip() {
    this.element_.classList.remove(this.CssClasses_.IS_ACTIVE);
  }

  function cancelRemoveTooltip() {
    clearTimeout(this.leaveTimer);
  }

  MaterialTooltip.prototype.handleMouseLeave_ = function() {
    this.leaveTimer = setTimeout(removeTooltip.bind(this), 500);
  }

  var original_enter = MaterialTooltip.prototype.handleMouseEnter_;
  MaterialTooltip.prototype.handleMouseEnter_ = function(event) {
    cancelRemoveTooltip.call(this);
    return original_enter.call(this, event);
  }

  var original_init = MaterialTooltip.prototype.init;
  MaterialTooltip.prototype.init = function() {
    original_init.call(this);

    if (this.element_) {
      this.element_.addEventListener(
        'mouseleave', this.handleMouseLeave_.bind(this));
      this.element_.addEventListener(
        'mouseenter', cancelRemoveTooltip.bind(this));
      this.element_.addEventListener(
        'touchend', cancelRemoveTooltip.bind(this));
    }
  }
}
