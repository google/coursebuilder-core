function bindEditorField(Y) {
  var RTE_TAG_DATA = cb_global.rte_tag_data;
  var SCHEMA = cb_global.schema;
  var CAN_HIGHLIGHT_CODE = cb_global.can_highlight_code

  /**
   * An editor component which provides HTML syntax highlighting.
   * See TextAreaEditor for the full documentation of the interface.
   *
   * @class
   */
  function HtmlEditor(root) {
    this.root = root;
    this.codeMirrorInstance = CodeMirror(root, {
      lineNumbers: true,
      lineWrapping: true,
      keyMap: "sublime",
      mode: "htmlmixed",
      extraKeys: {
        "Ctrl-Q": function(cm){ cm.foldCode(cm.getCursor()); }
      },
      foldGutter: true,
      gutters: ["CodeMirror-linenumbers", "CodeMirror-foldgutter"]
    });
  }
  HtmlEditor.prototype.hide = function() {
    this.root.style.display = 'none';
  };
  HtmlEditor.prototype.show = function() {
    this.root.style.display = null;
    this.codeMirrorInstance.refresh();
  };
  HtmlEditor.prototype.setSize = function(width, height) {
    this.codeMirrorInstance.setSize(width, height);
  };
  HtmlEditor.prototype.getValue = function() {
    return this.codeMirrorInstance.getValue();
  };
  HtmlEditor.prototype.setValue = function(value) {
    this.codeMirrorInstance.setValue(value);
    var that = this;
    setTimeout(function() {
      that.codeMirrorInstance.refresh();
    }, 0);
  };

  /**
   * An editor component which provides plain text editing in a textarea.
   *
   * @class
   * @param root {Element} The root element to hold the editor's HTML.
   */
  function TextareaEditor(root) {
    this.textarea = document.createElement('textarea');
    root.appendChild(this.textarea);
  }
  /**
   * Hide the component.
   *
   * @method
   */
  TextareaEditor.prototype.hide = function() {
    this.textarea.style.display = 'none';
  };
  /**
   * Reveal the component.
   *
   * @method
   */
  TextareaEditor.prototype.show = function() {
    this.textarea.style.display = null;
  };
  /**
   * Set the size of the editor component.
   *
   * @method
   * @param width {number} The new width of the component.
   * @param height {number} The new height of the component.
   */
  TextareaEditor.prototype.setSize = function(width, height) {
    this.textarea.style.width = width + 'px';
    this.textarea.style.height = height + 'px';
  };
  /**
   * Get the current value in the editor.
   *
   * @method
   * @return {string}
   */
  TextareaEditor.prototype.getValue = function() {
    return this.textarea.value;
  };
  /**
   * Set the value of the text to be edited.
   *
   * @method
   * @param value {string}
   */
  TextareaEditor.prototype.setValue = function(value) {
    this.textarea.value = value;
  };

  /**
   * An editor component which provides rich text editing and management of CB
   * content extensions.
   * See TextAreaEditor for the full documentation of the interface.
   *
   * @class
   */
  function RichTextEditor(root, opts, supportCustomTags, excludedCustomTags) {
    var that = this;

    this.root = root;
    this.excludedCustomTags = excludedCustomTags;

    var textarea = document.createElement('textarea');
    root.appendChild(textarea);

    var extraCss =
      '::-webkit-scrollbar {' +
      '  width: 10px;' +
      '}' +
      '::-webkit-scrollbar:horizontal {' +
      '  height: 10px;' +
      '}' +
      '::-webkit-scrollbar-track {' +
      '  background-color: #f5f5f5;' +
      '}' +
      '::-webkit-scrollbar-thumb {' +
      '  background-color: #c0c0c0;' +
      '  border: solid 1px #b4b4b4;' +
      '}';
    var attrs = {extracss: extraCss};
    for (var i in opts) {
      if (opts.hasOwnProperty(i)) {
        attrs[i] = opts[i];
      }
    }
    this.editor = new Y.YUI2.widget.Editor(textarea, attrs);
    this._disableHtmlCleaning();

    this.editorIsRendered = $.Deferred(function(def) {
      that.editor.on('afterRender', function() {
        def.resolve();
      });
    });
    this.editorIsVisible = $.Deferred();

    this._customTagManager = new DummyCustomTagManager();
    if (supportCustomTags) {
      $.when(this.editorIsRendered).then(function() {
        that._addCustomComponentButtons();
        that._bindCustomTagManager();
      });
    }

    this.editor.render();
  }
  RichTextEditor.prototype.hide = function() {
    this.root.style.display = 'none';
    this.editorIsVisible = $.Deferred();
  };
  RichTextEditor.prototype.show = function() {
    this.root.style.display = null;
    this.editorIsVisible.resolve();
  };
  RichTextEditor.prototype.setSize = function(width, height) {
    var that = this;
    $.when(this.editorIsRendered, this.editorIsVisible).then(function() {
      if (width) {
        that.editor.set('width', width + 'px');
      }
      // Note: be sure to calculate the toolbar height *after* setting the new
      // width because the number of button rows may have changed.
      // See: http://yui.github.io/yui2/docs/yui_2.9.0_full/examples/resize/rte_resize.html
      var toolbarHeight = that.editor.toolbar.get('element').clientHeight + 2;
      that.editor.set('height', (height - toolbarHeight) + 'px');
    });
  };
  RichTextEditor.prototype.getValue = function() {
    // Clean the editor text before saving, and then restore markers
    this._customTagManager.removeMarkerTags();
    var value = this.editor.saveHTML();
    this._customTagManager.insertMarkerTags();
    return value;
  };
  RichTextEditor.prototype.setValue = function(value) {
    var that = this;
    $.when(this.editorIsRendered).then(function() {
      that.editor.setEditorHTML(value);
      that._customTagManager.insertMarkerTags();
    });
  };
  RichTextEditor.prototype._addCustomComponentButtons = function() {
    // Add buttons to the tool bar for each of the CB custom components.
    var that = this;
    for (var i = 0; i < RTE_TAG_DATA.length; i++) {
      var componentData = RTE_TAG_DATA[i];
      if (this.excludedCustomTags.indexOf(componentData.name) >= 0) {
        continue;
      }
      var buttonDef = {
        type: 'push',
        label: componentData.label,
        value: componentData.name,
        disabled: false
      };
      this.editor.toolbar.addButtonToGroup(buttonDef, 'insertitem');
    }
    this.editor.toolbar.on('buttonClick', function(evt) {
      that._onAddCustomComponentButtonClicked(evt);
    });
  };
  RichTextEditor.prototype._onAddCustomComponentButtonClicked = function(evt) {
    var value = evt.button.value;
    for (var i = 0; i < RTE_TAG_DATA.length; i++) {
      if (value == RTE_TAG_DATA[i].name) {
        this._customTagManager.addCustomTag(value);
      }
    }
  };
  RichTextEditor.prototype._bindCustomTagManager = function() {
    // Activate a helper class (CustomTagManager) to handle insertion of icons
    // for custom tags in the rich text editor.
    var serviceUrlProvider = {
      getEditUrl: function(tagName) {
        return getEditCustomTagUrl(cb_global, tagName);
      }
    };
    this._customTagManager = new CustomTagManager(
      this.root.querySelector('iframe').contentWindow,
      this.editor,
      RTE_TAG_DATA,
      new FrameProxyOpener(window),
      serviceUrlProvider
    );
  };
  RichTextEditor.prototype._disableHtmlCleaning = function () {
    // Disable any HTML cleaning done by the editor.
    this.editor.cleanHTML = function(html) {
      if (! html) {
          html = this.getEditorHTML();
      }
      this.fireEvent('cleanHTML',
          {type: 'cleanHTML', target: this, html: html});
      return html;
    };
    this.editor._cleanIncomingHTML = function(html) {
      return html;
    };
    this.editor._fixNodes = function() {};
  };

  /**
   * The main class for CB's multi-faceted HTML editor. This base class handles
   * switching between a number of alternate editor components (e.g., plain
   * text, rich text editor, etc), and manages (re)sizing the component. The
   * editors must all provide the following interface:
   *   constructor(rootElt), hide(), show(), setSize(width, height), getValue(),
   *   setValue(value).
   * See TextAreaEditor for the full documentation of the interface.
   *
   * @class
   */
  function EditorField(options) {
    EditorField.superclass.constructor.call(this, options);
  }
  Y.extend(EditorField, Y.inputEx.Field);

  EditorField.prototype.setOptions = function(options) {
    EditorField.superclass.setOptions.call(this, options);
    this.opts = options.opts || {};
    this.excludedCustomTags = options.excludedCustomTags || [];
    this.supportCustomTags = options.supportCustomTags || false;

    if (SCHEMA._inputex && SCHEMA._inputex.className
        && SCHEMA._inputex.className.indexOf('new-form-layout') > -1) {
      this.fixedWidthLayout = true;
    }
  };
  EditorField.prototype.renderComponent = function() {
    // The basic structure of an InputExField
    //   <div class="inputEx-fieldWrapper">
    //     <div class="inputEx-label"></div>
    //     <div class="inputEx-Field"></div>
    //     </div style="clear: both;"></div>
    //   </div>
    // When this method is called, "this" is populated with:
    //   this.divEl: the inputEx-fieldWrapper
    //   this.fieldContainer:  the inputEx-Field div
    // Note that at this point this.fieldContainer has not yet been added as a
    // child to this.divEl at this point.
    var that = this;

    Y.one(this.fieldContainer).addClass('cb-editor-field');
    this.fieldContainer.innerHTML =
        '<div class="tabbar">' +
        '  <button class="html-button">HTML</button>' +
        '  <button class="rte-button">Rich Text</button>' +
        '</div>' +
        '<div class="editors-div">' +
        '  <div class="html-div"></div>' +
        '  <div class="rte-div"></div>' +
        '</div>';
    this.tabbar = this.fieldContainer.querySelector('.tabbar');
    this.htmlButton = this.fieldContainer.querySelector('.html-button');
    this.rteButton = this.fieldContainer.querySelector('.rte-button');
    this.editorsDiv = this.fieldContainer.querySelector('.editors-div');
    this.htmlDiv = this.fieldContainer.querySelector('.html-div');
    this.rteDiv = this.fieldContainer.querySelector('.rte-div');

    if (CAN_HIGHLIGHT_CODE) {
      this.htmlEditor = new HtmlEditor(this.htmlDiv);
    } else {
      this.htmlEditor = new TextareaEditor(this.htmlDiv);
    }
    this.richTextEditor = new RichTextEditor(this.rteDiv, this.opts,
        this.supportCustomTags, this.excludedCustomTags);

    // Default mode is HTML editing
    this._selectHtmlMode();

    // Bind the buttons
    this.htmlButton.onclick = function() {
      that._selectHtmlMode();
      return false;
    };
    this.rteButton.onclick = function() {
      that._selectRichTextMode();
      return false;
    };

    // Bind the resizer
    new Y.YUI2.util.Resize(this.editorsDiv, {
      handles: ['br'],
      minHeight: 200,
      minWidth: 200,
      proxy: true,
      setSize: false
    }).on('resize', function(evt) {
      that._resize(evt.width, evt.height);
    });
  };
  EditorField.prototype.setValue = function(value, sendUpdatedEvt) {
    this.activeEditor.setValue(value);
    if(sendUpdatedEvt !== false) {
      this.fireUpdatedEvt();
    }
  };
  EditorField.prototype.getValue = function() {
    return this.activeEditor.getValue();
  };
  EditorField.prototype._selectHtmlMode = function() {
    this.tabbar.className = 'tabbar showing-html';
    this.htmlEditor.setValue(this.richTextEditor.getValue());
    this.htmlEditor.show();
    this.richTextEditor.hide();
    this.activeEditor = this.htmlEditor;
  };
  EditorField.prototype._selectRichTextMode = function() {
    this.tabbar.className = 'tabbar showing-rte';
    this.richTextEditor.setValue(this.htmlEditor.getValue());
    this.htmlEditor.hide();
    this.richTextEditor.show();
    this.activeEditor = this.richTextEditor;
  };
  EditorField.prototype._resize = function(width, height) {
    if (this.fixedWidthLayout) {
      this.editorsDiv.style.height = height + 'px';
      this.htmlEditor.setSize(null, height);
      this.richTextEditor.setSize(null, height);
    } else {
      this.editorsDiv.style.width = width + 'px';
      this.editorsDiv.style.height = height + 'px';
      this.htmlEditor.setSize(width, height);
      this.richTextEditor.setSize(width, height);
    }
  };

  // Bind the EditorField to handle HTML data type for InputEx.
  Y.inputEx.registerType("html", EditorField, []);
}

/**
 * A utility class to open the lightbox window.
 *
 * @param win the root window
 */
function FrameProxyOpener(win) {
  this._win = win;
}

FrameProxyOpener.prototype.open = function(url, getValue, context, submit,
    cancel) {
  if (this._win.frameProxy) {
    this._win.frameProxy.close();
  }
  this._win.frameProxy = new FrameProxy('modal-editor', url, getValue, context,
      submit, cancel);
  this._win.frameProxy.open();
};

/**
 * Provides the logic for handling custom tags inside the YUI editor.
 *
 * @param win the window from the RTE iframe
 * @param editor the YUI editor component itself
 * @param rteTagData a list of pairs of tag names and their icon urls
 * @param frameProxyOpener the opener object for the lightbox
 * @param serviceUrlProvider a provider for the urls the lightbox will use
 */
function CustomTagManager(win, editor, rteTagData, frameProxyOpener,
    serviceUrlProvider) {
  this._win = win;
  this._editor = editor;
  this._rteTagData = rteTagData;
  this._frameProxyOpener = frameProxyOpener;
  this._serviceUrlProvider = serviceUrlProvider;

  this._init();
}

CustomTagManager.prototype = {
  _init: function() {
    var that = this;

    // List of elements which have been replaced by marker tags. This is
    // populated by insertMarkerTags and read by removeMarkerTags. We store the
    // original CB custom tag elements rather than rebuilding them because older
    // IE can't create non-HTML elements in JS.
    this._markerTagElements = [];

    this.insertMarkerTags();

    // Refresh the marker images after a paste
    this._win.document.body.onpaste = function(e) {
      setTimeout(function() {
        that._refreshMarkerTags();
      }, 10);
    };
  },

  /**
   * Returns an instanceid that is unique within the context of the RTE.
   */
  _getNewInstanceId: function(value) {
    var ALPHANUM_CHARS = (
      'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789');
    var REFID_LENGTH = 12;

    var documentContent = this._win.document.documentElement.innerHTML;
    var foundUniqueInstanceId = false;

    while (true) {
      var newInstanceId = '';
      for (var i = 0; i < REFID_LENGTH; i++) {
        newInstanceId += ALPHANUM_CHARS.charAt(
            Math.floor(Math.random() * ALPHANUM_CHARS.length));
      }

      if(documentContent.indexOf(newInstanceId) == -1) {
        return newInstanceId;
      }
    }
  },

  _setTextContent: function(node, value) {
    if (document.body.textContent) {
      node.textContent = value;
    } else {
      node.innerText = value;
    }
  },

  _populateTagNode: function(node, properties, value) {
    for (var name in properties) {
      if (properties.hasOwnProperty(name)) {
        if (properties[name].type === "text") {
          this._setTextContent(node, value[name]);
        } else {
          node.setAttribute(name, value[name]);
        }
      }
    }
  },

  _getValueFromTagNode: function(properties, node) {
    var value = {};
    for (var name in properties) {
      if (properties.hasOwnProperty(name)) {
        if (properties[name].type === "text") {
          value[name] = node.textContent || node.innerText;
        }
      }
    }

    for (var i = 0; i < node.attributes.length; i++) {
      var name = node.attributes[i].name;
      value[name] = node.attributes[i].value;
    }

    return value;
  },

  addCustomTag: function(tagName) {
    var that = this;
    this._insertInsertionPointTag();
    this._frameProxyOpener.open(
      this._serviceUrlProvider.getEditUrl(tagName),
      null,
      {}, // context object
      function(value, schema) { // on submit
        that._insertCustomTag(tagName, value, schema);
      },
      function () { // on cancel
        that._removeInsertionPointTag();
      }
    );
  },

  _insertCustomTag: function(tagName, value, schema) {
    var node = this._win.document.createElement(tagName);
    this._populateTagNode(
        node, schema.properties, value);
    node.setAttribute('instanceid', this._getNewInstanceId());

    var insertionPoint = this._win.document.querySelector('.gcbInsertionPoint');
    insertionPoint.parentNode.replaceChild(node, insertionPoint);

    this._refreshMarkerTags();
  },

  /**
   * When a custom tag is double-clicked, open up a sub-editor in a lightbox.
   */
  _editCustomTag: function(node) {
    var that = this;

    this._frameProxyOpener.open(
      this._serviceUrlProvider.getEditUrl(node.tagName.toLowerCase()),
      function(schema) { // callback for tag values
        return that._getValueFromTagNode(schema.properties, node);
      },
      {}, // context object
      function(value, schema) { // on submit
        var instanceid = node.getAttribute('instanceid');
        that._populateTagNode(node, schema.properties, value);
        node.setAttribute('instanceid', instanceid);
      },
      function () { /* on cancel */ }
    );
  },

  _refreshMarkerTags: function() {
    this.removeMarkerTags();
    this.insertMarkerTags();
  },

  insertMarkerTags: function() {
    var editorDoc = this._win.document;
    var that = this;
    this.markerTags = [];
    for (var k = 0; k < this._rteTagData.length; k++) {
      var tag = this._rteTagData[k];
      var elts = editorDoc.getElementsByTagName(tag.name);
      for (var i = elts.length - 1; i >= 0; i--) {
        var elt = elts[i];
        var img = editorDoc.createElement('img');
        img.src = tag.iconUrl;
        img.className = 'gcbMarker';
        img.style.cursor = 'pointer';
        img.ondblclick = (function(_elt) {
          // Create a new scope with its own pointer to the current element
          return function(event) {
            var event = event || editorWin.event;
            if (event.stopPropagation) {
              event.stopPropagation();
            } else { // IE 8 & 9
              event.cancelBubble = true;
            }
            that._editCustomTag(_elt);
          };
        })(elt);
        img.onmousedown = img.onmouseup = img.onclick = function(event) {
          that._sinkEvent(event);
        };
        var index = that._markerTagElements.push(elt);
        img.id = 'markerTag-' + (index - 1);
        that._styleMarkerTag(img);
        elt.parentNode.replaceChild(img, elt);
      }
    }
    // Make sure that YUI Editor doesn't keep a copy of the original HTML
    // content on its undo stack
    this._editor._undoLevel = 0;
    this._editor._undoCache = [];
    this._editor._putUndo(this._editor.getEditorHTML());
  },

  _styleMarkerTag: function(img) {
    img.style.borderRadius = '5px';
    img.style.borderColor = '#ccc';
    img.style.borderWidth = '3px';
    img.style.borderStyle = 'ridge';
    img.style.width = '48px';
    img.style.height = '48px';
  },

  _sinkEvent: function(event) {
    var event = event || this._win.event;
    if (event.preventDefault && event.stopPropagation) {
      event.preventDefault();
      event.stopPropagation();
    } else { // IE 8 & 9
      event.returnValue = false;
      event.cancelBubble = true;
    }
    return false;
  },

  removeMarkerTags: function() {
    var elts = this._win.document.querySelectorAll('.gcbMarker');
    for (var i = 0; i < elts.length; i++) {
      var img = elts[i];
      var match = (img.id || '').match(/markerTag-(\d+)/);
      if (match) {
        var index = Number(match[1]);
        img.parentNode.replaceChild(this._markerTagElements[index], img);
      } else {
        img.parentNode.removeChild(img);
      }
    }
  },

  _insertInsertionPointTag: function() {
    this._editor.execCommand('inserthtml',
        '<span class="gcbInsertionPoint"></span>');
  },

  _removeInsertionPointTag: function() {
    this._removeTagsByClass('gcbInsertionPoint');
  },

  _removeTagsByClass: function(clazz) {
    var elts = this._win.document.querySelectorAll('.' + clazz);
    for (var i = 0; i < elts.length; i++) {
      var e = elts[i];
      e.parentNode.removeChild(e);
    }
  }
};

/**
 * A dummy tag manager used when the RTE is in a context where custom tags are
 * not supported.
 */
function DummyCustomTagManager() {};

DummyCustomTagManager.prototype = {
  addCustomTag: function(tagName) {},
  insertMarkerTags: function() {},
  removeMarkerTags: function() {}
};
