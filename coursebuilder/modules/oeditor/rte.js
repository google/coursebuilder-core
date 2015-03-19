/**
 * Define the methods of the GCB rich text editor here.
 */
function getGcbRteDefs(env, Dom, Editor, Resize) {
  var IS_NEW_FORM_LAYOUT = false;

  return {
    setOptions: function(options) {
      GcbRteField.superclass.setOptions.call(this, options);
      this.options.opts = options.opts || {};
      this.options.excludedCustomTags = options.excludedCustomTags || [];
      this.options.supportCustomTags = options.supportCustomTags || false;

      if (env.schema._inputex && env.schema._inputex.className
          && env.schema._inputex.className.indexOf('new-form-layout') > -1) {
        IS_NEW_FORM_LAYOUT = true;
      }
    },

    renderComponent: function() {
      // Make a unique id for the field
      if (!GcbRteField.idCounter) {
        GcbRteField.idCounter = 0;
      }
      this.id = "gcbRteField-" + GcbRteField.idCounter;
      GcbRteField.idCounter += 1;

      // Insert the text area for plain text editing
      this.el = document.createElement('textarea');
      this.el.setAttribute('id', this.id);
      this.el.setAttribute('class', 'gcb-rte-textarea');
      if(this.options.name) {
        this.el.setAttribute('name', this.options.name);
      }

      this.fieldContainer.appendChild(this.el);
      this.isInRteMode = false;

      this._replaceTextAreaWithCodeMirror();
      this.divEl.appendChild(this._getModeToggle());

      if (! env.can_highlight_code) {
        this._monitorResizeOfTextArea();
      }
    },

    _getModeToggle: function() {
      var that = this;
      var controls = document.createElement("div");
      controls.className = "rte-control showing-html";
      controls.innerHTML =
          '<div class="html">HTML</div>' +
          '<div class="rich-text">Rich Text</div>';
      var htmlButton = controls.querySelector('.html');
      var rteButton = controls.querySelector('.rich-text');

      htmlButton.onclick = function() {
        that.hideRte();
        controls.className = "rte-control showing-html";
        that.isInRteMode = false;
      };
      rteButton.onclick = function() {
          if (that.editor) {
            that.showExistingRte();
          } else {
            that.showNewRte();
          }
          controls.className = "rte-control showing-rte";
          that.isInRteMode = true;
      };
      return controls;
    },

    _monitorResizeOfTextArea: function() {
      var that = this, width = 0, height = 0;
      setInterval(function() {
        if (that.el.offsetWidth != width || that.el.offsetHeight != height) {
          width = that.el.offsetWidth;
          height = that.el.offsetHeight;
          that._resizeEditorsExceptTextArea(width, height);
        }
      }, 100);
    },

    _replaceTextAreaWithCodeMirror: function() {
      var that = this;

      if (! env.can_highlight_code) {
        return;
      }

      this.cmReady = false;

      // note: the first calling when this.cmInstance does not exist
      //       (by renderComponent) will not make CodeMirror ready
      //       this is because setValue must be call after renderComponent
      //       (to sync old value from database, "" will passed for first time)
      //       this is why this.cmReady will be set on the else clause
      if (! this.cmInstance) {
        this.cmInstance = CodeMirror(this.fieldContainer,
            {
              value: this.el.value,
              lineNumbers: true,
              lineWrapping: true,
              keyMap: "sublime",
              mode: "htmlmixed",
              extraKeys: {
                "Ctrl-Q": function(cm){ cm.foldCode(cm.getCursor()); }
              },
              foldGutter: true,
              gutters: ["CodeMirror-linenumbers", "CodeMirror-foldgutter"]
            }
        );
        // Reference used for testing
        this.cmInstance.gcbCodeMirrorMonitor = this;

        new Resize(this.cmInstance.getWrapperElement(),
            {
              handles: ['br'],
              minHeight: 200,
              minWidth: 200,
              proxy: true,
              setSize: false
            }
        ).on("resize", function(args) {
          that._resizeEditors(args.width, args.height);
        });
      } else {
        this.cmInstance.setValue(this.el.value);
        this.cmReady = true;
      }

      Dom.addClass(this.el, "hidden");
      Dom.removeClass(this.cmInstance.getWrapperElement(), "hidden");

      window.setTimeout(function(){
        that.cmInstance.refresh();
      }, 0);
    },

    _syncTextAreaWithCodeMirror: function() {
      if (! env.can_highlight_code) {
        return;
      }

      this.el.value = this.cmInstance.getValue();
    },

    _replaceCodeMirrorWithTextArea: function() {
      if (! env.can_highlight_code) {
        return;
      }

      if (this.cmInstance) {
        this._syncTextAreaWithCodeMirror();
        this.cmReady = false;

        Dom.removeClass(this.el, "hidden");
        Dom.addClass(this.cmInstance.getWrapperElement(), "hidden");
      }
    },

    _resizeEditors: function(width, height) {
      this._resizeEditorsExceptTextArea(width, height);

      // Resize the text area
      this.el.style.width = width + "px";
      this.el.style.height = height + "px";
    },

    _resizeEditorsExceptTextArea: function(width, height) {
      if (this.editor) {
        var toolbarHeight = this.editor.toolbar.get('element').clientHeight + 2;
        if (! IS_NEW_FORM_LAYOUT) {
          this.editor.set('width', width + 'px');
        }
        this.editor.set('height', (height - toolbarHeight) + 'px');
      }
      if (this.cmInstance) {
        this.cmInstance.setSize(IS_NEW_FORM_LAYOUT ? null : width, height);
      }
      this._lastResizeDimensions = {width: width, height: height};
    },

    showNewRte: function() {
      this._replaceCodeMirrorWithTextArea();

      var that = this;

      var extraCss =
        "::-webkit-scrollbar {" +
        "  width: 10px;" +
        "}" +
        "::-webkit-scrollbar:horizontal {" +
        "  height: 10px;" +
        "}" +
        "::-webkit-scrollbar-track {" +
        "  background-color: #f5f5f5;" +
        "}" +
        "::-webkit-scrollbar-thumb {" +
        "  background-color: #c0c0c0;" +
        "  border: solid 1px #b4b4b4;" +
        "}";
      var _def = {
        extracss: extraCss
      }
      for (var i in this.options.opts) {
        if (this.options.opts.hasOwnProperty(i)) {
          _def[i] = this.options.opts[i];
        }
      }

      var editor = new Editor(this.id, _def);

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

      editor.on('editorContentLoaded', function() {
        new Resize(editor.get('element_cont').get('element'),
          {
            handles: ['br'],
            minHeight: 300,
            minWidth: 400,
            proxy: true,
            setSize: false
          }
        ).on('resize', function(args) {
          that._resizeEditors(args.width, args.height);
        });
        if (that._lastResizeDimensions) {
          that._resizeEditors(
              that._lastResizeDimensions.width,
              that._lastResizeDimensions.height);
        }
        if (IS_NEW_FORM_LAYOUT) {
          editor.set('width', null);
        }
      });

      // Set up a button to add custom tags
      if (this.options.supportCustomTags) {
        editor.on('toolbarLoaded', function() {
          var button = {
            type: 'push',
            label: 'Insert Google Course Builder component',
            value: 'insertcustomtag',
            disabled: false
          };
          editor.toolbar.addButtonToGroup(button, 'insertitem');
          editor.toolbar.on('insertcustomtagClick',
              function() {
                // defer dereferencing the _customTagManager, which is
                // created later
                that._customTagManager.addCustomTag();
              },
              that, true);
        });

        // Poll until the editor iframe has loaded and attach custom tag manager
        (function() {
          var ed = document.getElementById(that.id + '_editor');
          if (ed && ed.contentWindow && ed.contentWindow.document &&
              ed.contentWindow.document.readyState == 'complete') {
            that._customTagManager = new CustomTagManager(ed.contentWindow,
                editor, env.custom_rte_tag_icons,
                that.options.excludedCustomTags,
                new FrameProxyOpener(window),
                {
                  getAddUrl: function() {
                    return getAddCustomTagUrl(
                        env, null, that.options.excludedCustomTags);
                  },
                  getEditUrl: function(tagName) {
                    return getEditCustomTagUrl(env, tagName);
                  }
                });
          } else {
            setTimeout(arguments.callee, 100);
          }
        })();
      } else {
        this._customTagManager = new DummyCustomTagManager();
      }

      this.editor = editor;
      this.editor.render();
    },

    showExistingRte: function() {
      this._replaceCodeMirrorWithTextArea();

      var editor = this.editor,
          textArea = this.el,
          rteDiv = textArea.previousSibling,
          resizeDiv = textArea.nextSibling;

      Dom.setStyle(textArea, 'visibility', 'hidden');
      Dom.setStyle(textArea, 'top', '-9999px');
      Dom.setStyle(textArea, 'left', '-9999px');
      Dom.setStyle(textArea, 'position', 'absolute');
      Dom.removeClass(rteDiv, "hidden");
      Dom.removeClass(resizeDiv, "hidden");
      editor.get('element_cont').addClass('yui-editor-container');
      editor._setDesignMode('on');
      editor.setEditorHTML(textArea.value);
      this._customTagManager.insertMarkerTags();
    },

    hideRte: function() {
      var editor = this.editor,
          textArea = this.el,
          rteDiv = textArea.previousSibling,
          resizeDiv = textArea.nextSibling;

      this._customTagManager.removeMarkerTags();
      editor.saveHTML();

      Dom.addClass(rteDiv, "hidden");
      Dom.addClass(resizeDiv, "hidden");
      editor.get('element_cont').removeClass('yui-editor-container');
      Dom.setStyle(textArea, 'visibility', 'visible');
      Dom.setStyle(textArea, 'top', '');
      Dom.setStyle(textArea, 'left', '');
      Dom.setStyle(textArea, 'position', 'static');
      Dom.addClass(textArea, 'raw-text-editor');

      this._replaceTextAreaWithCodeMirror();
    },

    setValue: function(value, sendUpdatedEvt) {
      if (this.isInRteMode) {
        this.editor.setEditorHTML(value);
      } else {
        this.el.value = value;
        this._replaceTextAreaWithCodeMirror();
      }
      if(sendUpdatedEvt !== false) {
        this.fireUpdatedEvt();
      }
    },

    getValue: function() {
      if (this.isInRteMode) {
        // Clean the editor text before saving, and then restore markers
        this._customTagManager.removeMarkerTags();
        var value = this.editor.saveHTML();
        this._customTagManager.insertMarkerTags();
        return value;
      } else {
        this._syncTextAreaWithCodeMirror();
        return this.el.value;
      }
    }
  };
};

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
 * @param customRteTagIcons a list of pairs of tag names and their icon urls
 * @param frameProxyOpener the opener object for the lightbox
 * @param serviceUrlProvider a provider for the urls the lightbox will use
 */
function CustomTagManager(win, editor, customRteTagIcons, excludedCustomTags,
    frameProxyOpener, serviceUrlProvider) {
  this._win = win;
  this._editor = editor;
  this._customRteTagIcons = customRteTagIcons;
  this._excludedCustomTags = excludedCustomTags;
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

  addCustomTag: function() {
    var that = this;
    this._insertInsertionPointTag();
    this._frameProxyOpener.open(
      this._serviceUrlProvider.getAddUrl(),
      null,
      {excludedCustomTags: this._excludedCustomTags}, // context object
      function(value, schema) { // on submit
        that._insertCustomTag(value, schema);
      },
      function () { // on cancel
        that._removeInsertionPointTag();
      }
    );
  },

  _insertCustomTag: function(value, schema) {
    var node = this._win.document.createElement(value.type.tag);
    this._populateTagNode(
        node, schema.properties.attributes.properties, value.attributes);
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
      {excludedCustomTags: this._excludedCustomTags}, // context object
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
    for (var k = 0; k < this._customRteTagIcons.length; k++) {
      var tag = this._customRteTagIcons[k];
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
  addCustomTag: function() {},
  insertMarkerTags: function() {},
  removeMarkerTags: function() {}
};
