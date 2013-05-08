/**
 * Define the methods of the GCB rich text editor here.
 */
function getGcbRteDefs(env, Dom, Editor) {
  return {
    setOptions: function(options) {
      GcbRteField.superclass.setOptions.call(this, options);
      this.options.opts = options.opts || {};
      this.options.supportCustomTags = options.supportCustomTags || false;
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
      if(this.options.name) {
        this.el.setAttribute('name', this.options.name);
      }

      this.fieldContainer.appendChild(this.el);

      // Make a button to toggle between plain text and rich text
      var showRteText = "Rich Text";
      var hideRteText = "<HTML>";
      var showRteFlag = false;
      var toggle = document.createElement("div");
      var toggleText = document.createTextNode(showRteText);
      toggle.appendChild(toggleText);
      toggle.className = "rte-control inputEx-Button";

      var self = this;
      toggle.onclick = function() {
        showRteFlag = !showRteFlag;
        if (showRteFlag) {
          if (self.editor) {
            self.showExistingRte();
          } else {
            self.showNewRte();
          }
          toggleText.nodeValue = hideRteText;
        } else {
          self.hideRte();
          toggleText.nodeValue = showRteText;
        }
      };
      this.divEl.appendChild(toggle);
    },

    _getEditorWindow: function() {
      return document.getElementById(this.id + '_editor').contentWindow;
    },

    _insertMarkerTags: function(editorWin) {
      var editorDoc = editorWin.document;
      var that = this;
      for (var k = 0; k < env.custom_rte_tag_icons.length; k++) {
        var tag = env.custom_rte_tag_icons[k];
        var elts = editorDoc.getElementsByTagName(tag.name);
        for (var i = elts.length - 1; i >= 0; i--) {
          var elt = elts[i];
          var img = editorDoc.createElement('img');
          img.src = tag.iconUrl;
          img.className = 'gcbMarker';
          img.style.cursor = 'pointer';
          img.ondblclick = (function(_elt, _img) {
            // Create a new scope with its own pointer to the current element
            return function(event) {
              var event = event || editorWin.event;
              if (event.stopPropagation) {
                event.stopPropagation();
              } else { // IE 8 & 9
                event.cancelBubble = true;
              }
              that._editCustomTag(_elt, _img);
            };
          })(elt, img);
          img.onmousedown = img.onmouseup = img.onclick = function(event) {
            that._sinkEvent(editorWin, event);
          };
          img.gcbTag = elt;
          that._styleMarkerTag(img);
          elt.parentNode.replaceChild(img, elt);
        }
      }
    },

    _sinkEvent: function(editorWin, event) {
      var event = event || editorWin.event;
      if (event.preventDefault && event.stopPropagation) {
        event.preventDefault();
        event.stopPropagation();
      } else { // IE 8 & 9
        event.returnValue = false;
        event.cancelBubble = true;
      }
      return false;
    },

    _styleMarkerTag: function(img) {
      img.style.borderRadius = '5px';
      img.style.borderColor = '#ccc';
      img.style.borderWidth = '3px';
      img.style.borderStyle = 'ridge'; 
      img.style.width = '48px';
      img.style.height = '48px';
    },

    /**
     * When a custom tag is double-clicked, open up a sub-editor in a lightbox.
     */
    _editCustomTag: function(node, img) {
      var value = {};
      for (var i = 0; i < node.attributes.length; i++) {
        value[node.attributes[i].name] = node.attributes[i].value;
      }
      if (window.frameProxy) {
        window.frameProxy.close();
      }
      window.frameProxy = new FrameProxy(
        'modal-editor',
        getEditCustomTagUrl(env, node.tagName.toLowerCase()),
        value,
        function(value) { // on submit
          for (var name in value) {
            if (value.hasOwnProperty(name)) {
              node.setAttribute(name, value[name]);
            }
          }
        },
        function () { /* on cancel */ }
      );
      window.frameProxy.open();
    },

    _addCustomTag: function() {
      var that = this;
      this._insertInsertionPointTag();

      if (window.frameProxy) {
        window.frameProxy.close();
      }
      window.frameProxy = new FrameProxy(
        'modal-editor',
        getAddCustomTagUrl(env),
        null,
        function(value) { // on submit
          that._insertCustomTag(value);
        },
        function () { // on cancel
          that._removeInsertionPointTag(that._getEditorWindow());
        }
      );
      window.frameProxy.open();
    },

    _insertCustomTag: function(value) {
      var el = document.createElement(value.type.tag);
      for (var name in value.attributes) {
        if (value.attributes.hasOwnProperty(name)) {
          el.setAttribute(name, value.attributes[name]);
        }
      }
      var editorWin = this._getEditorWindow();
      var insertionPoint = editorWin.document.querySelector('.gcbInsertionPoint');
      insertionPoint.parentNode.replaceChild(el, insertionPoint);

      this._refreshMarkerTags()
    },

    _insertInsertionPointTag: function() {
      this.editor.execCommand('inserthtml',
          '<span class="gcbInsertionPoint"></span>');
    },

    _removeInsertionPointTag: function(win) {
      this._removeTagsByClass(win, 'gcbInsertionPoint');
    },

    _removeMarkerTags: function(win) {
      var elts = win.document.querySelectorAll('.gcbMarker');
      for (var i = 0; i < elts.length; i++) {
        var img = elts[i];
        if (img.gcbTag) {
          img.parentNode.replaceChild(img.gcbTag, img);
        } else {
          img.parentNode.removeChild(img);
        }
      }
    },

    _removeTagsByClass: function(win, clazz) {
      var elts = win.document.querySelectorAll('.' + clazz);
      for (var i = 0; i < elts.length; i++) {
        var e = elts[i];
        e.parentNode.removeChild(e);
      }
    },

    showNewRte: function() {
      var that = this;
      var options = this.options;
      var _def = {
        height: '350px',
        width: '510px',
        dompath: true,
      };
      // Merge options.opts into the default options
      var opts = options.opts;
      for (var i in opts) {
        if (opts.hasOwnProperty(i)) {
          _def[i] = opts[i];
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

      // Set up a button to add custom tags
      if (options.supportCustomTags) {
        editor.on('toolbarLoaded', function() {
          var button = {
            type: 'push',
            label: 'Insert Google Course Builder component',
            value: 'insertcustomtag',
            disabled: false
          };
          editor.toolbar.addButtonToGroup(button, 'insertitem');
          editor.toolbar.on('insertcustomtagClick', that._addCustomTag, that, true);
        });
      }

      this.editor = editor;
      this.editor.render();

      // Poll until the editor iframe has loaded
      (function() {
        var ed = document.getElementById(that.id + '_editor');
        if (ed && ed.contentWindow && ed.contentWindow.document &&
            ed.contentWindow.document.readyState == 'complete') {
          that._onEditorIframeLoaded();
        } else {
          setTimeout(arguments.callee, 100);
        }
      })();
    },

    _onEditorIframeLoaded: function() {
      var that = this;
      if (this.options.supportCustomTags) {
        this._insertMarkerTags(this._getEditorWindow());
      }

      // Refresh the marker images after a paste
      this._getEditorWindow().document.body.onpaste = function(e) {
        setTimeout(function() {
          that._refreshMarkerTags();
        }, 10);
      };
    },

    _refreshMarkerTags: function() {
      var editorWin= this._getEditorWindow();
      this._removeMarkerTags(editorWin);
      this._insertMarkerTags(editorWin);
    },

    showExistingRte: function() {
      var editor = this.editor,
          textArea = this.el;
          rteDiv = textArea.previousSibling;

      if (this._cbGetValue) {
        this.getValue = this._cbGetValue;
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
      if (this.options.supportCustomTags) {
        this._insertMarkerTags(this._getEditorWindow());
      }
    },

    hideRte: function() {
      var editor = this.editor,
          textArea = this.el;
          rteDiv = textArea.previousSibling;

      this._removeMarkerTags(this._getEditorWindow());
      editor.saveHTML();

      this._cbGetValue = this.getValue;
      this.getValue = function() {
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
    },

    setValue: function(value, sendUpdatedEvt) {
      this.el.value = value;
      if(sendUpdatedEvt !== false) {
        this.fireUpdatedEvt();
      }
    },

    getValue: function() {
      if (this.editor) {
        var editorDoc = this._getEditorWindow();
        // Clean the editor text before saving, and then restore markers
        this._removeMarkerTags(editorDoc);
        var value = this.editor.saveHTML();
        this._insertMarkerTags(editorDoc);
        return value;
      } else {
        return this.el.value;
      }
    }
  };
};
