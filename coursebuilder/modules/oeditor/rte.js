/**
 * Define the methods of the GCB rich text editor here.
 */
function getGcbRteDefs(env, Dom, Editor) {
  return {
    setOptions: function(options) {
      GcbRteField.superclass.setOptions.call(this, options);
      this.options.opts = options.opts || {};
      this.options.editorType = options.editorType;
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
      var hideRteText = "Plain Text";
      var showRteFlag = false;
      var toggle = document.createElement("div");
      var toggleText = document.createTextNode(showRteText);
      toggle.appendChild(toggleText);
      Dom.addClass(toggle, "rte-control");

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

    _getEditorWindow: function(id) {
      return document.getElementById(id + '_editor').contentWindow;
    },

    _insertMarkerTags: function(editorWin) {
      var editorDoc = editorWin.document;
      var that = this;
      for (var k = 0; k < env.custom_rte_tag_icons.length; k++) {
        var tag = env.custom_rte_tag_icons[k];
        var elts = editorDoc.getElementsByTagName(tag.name);
        for (var i = 0; i < elts.length; i++) {
          var img = editorDoc.createElement('img');
          img.src = tag.iconUrl;
          img.className = 'gcbMarker';
          img.style.cursor = 'pointer';
          img.ondblclick = (function(target) {
            // Create a new scope with its own pointer to the current element
            return function(event) {
              var event = event || editorWin.event;
              if (event.stopPropagation) {
                event.stopPropagation();
              } else { // IE 8 & 9
                event.cancelBubble = true;
              }
              that._onCustomTagAction(target);
            };
          })(elts[i]);
          img.onmousedown = function(event) {
            var event = event || editorWin.event;
            if (event.preventDefault && event.stopPropagation) {
              event.preventDefault();
              event.stopPropagation();
            } else { // IE 8 & 9
              event.returnValue = false;
              event.cancelBubble = false;
            }
          };
          if (typeof elts[i].canHaveChildren == 'boolean'
              && !elts[i].canHaveChildren) { // IE 8 & 9
            elts[i].parentNode.insertBefore(img, elts[i]);
          } else {
            // Prefer to append the image as child so it can't be separated from
            // its tag by the editor.
            elts[i].appendChild(img);
          }
        }
      }
    },

    /**
     * When a custom tag is double-clicked, open up a sub-editor in a lightbox.
     */
    _onCustomTagAction: function(node) {
      var url = '/oeditor/popup?action=custom_tag&tag_name=' +
          escape(node.tagName.toLowerCase());
      var value = {};
      for (var i = 0; i < node.attributes.length; i++) {
        value[node.attributes[i].name] = node.attributes[i].value;
      }
      if (window.frameProxy) {
        window.frameProxy.close();
      }
      window.frameProxy = new FrameProxy(
        'modal-editor',
        url,
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

    _removeMarkerTags: function(editorWin) {
      var editorDoc = editorWin.document;
      if (editorDoc.getElementsByClassName) {
        var elts = editorDoc.getElementsByClassName('gcbMarker');
        while (elts.length > 0) {
          var e = elts[0];
          e.parentNode.removeChild(e);
        }
      } else { // IE8
        var elts = editorDoc.querySelectorAll('.gcbMarker')
        for (var i = 0; i < elts.length; i++) {
          var e = elts[i];
          e.parentNode.removeChild(e);
        }
      }
    },

    showNewRte: function() {
      var options = this.options;
      var _def = {
        height: '300px',
        width: '500px',
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

      this.editor = editor;
      this.editor.render();

      // Poll until the editor iframe has loaded
      var that = this;
      (function() {
        var ed = document.getElementById(that.id + '_editor');
        if (ed && ed.contentWindow && ed.contentWindow.document &&
            ed.contentWindow.document.readyState == 'complete') {
          that._insertMarkerTags(that._getEditorWindow(that.id));
        } else {
          setTimeout(arguments.callee, 100);
        }
      })();
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
      this._insertMarkerTags(this._getEditorWindow(this.id));
    },

    hideRte: function() {
      var editor = this.editor,
          textArea = this.el;
          rteDiv = textArea.previousSibling;

      this._removeMarkerTags(this._getEditorWindow(this.id));
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
        var editorDoc = this._getEditorWindow(this.id);
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
