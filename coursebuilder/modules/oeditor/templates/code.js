function bindCodeField(Y) {
  /**
   * An InputEx field to enter text using CodeMirror.
   *
   * @class
   */
  var CodeEditor = function(options) {
     CodeEditor.superclass.constructor.call(this, options);

    if(this.options.typeInvite) {
      this.updateTypeInvite();
    }
  };

  Y.extend(CodeEditor, Y.inputEx.Field, {
    /*
     * All functions other than setOptions assume renderComponent has already
     * been called.
    */
    setOptions: function(options) {
      CodeEditor.superclass.setOptions.call(this, options);
      this.mode = options.mode;
      this.options.large = options.large;
      this.options.allowResizeWidth = !isNewFormLayout();
    },
    renderComponent: function() {
      // This function is probably only called once per instance
      var that = this;
      CodeMirror.modeURL = "/static/codemirror/mode/%N/%N.js";

      Y.one(this.fieldContainer).addClass('cb-code-field');
      this.wrapEl = Y.inputEx.cn(
        'div', {className: 'inputEx-CodeField-wrapper'});
      this.codeMirrorInstance = CodeMirror(this.wrapEl, {
        lineNumbers: true,
        lineWrapping: true,
        keyMap: "sublime",
        mode: this.mode,
        extraKeys: {"Ctrl-Q": function(cm){ cm.foldCode(cm.getCursor()); }},
        foldGutter: true,
        gutters: ["CodeMirror-linenumbers", "CodeMirror-foldgutter"]
      });
      this.loadMode();

      this.fieldContainer.appendChild(this.wrapEl);
      if (this.options.large) {
        handler = function(){
          that.codeMirrorInstance.off('update', handler);
          that.resize(null, getPotentialHeight(that.wrapEl));
        }
        this.codeMirrorInstance.on('update', handler);
      }

      // Bind the resizer
      new Y.YUI2.util.Resize(this.wrapEl, {
        handles: ['br'],
        minHeight: 200,
        minWidth: 200,
        proxy: true,
        setSize: false
      }).on('resize', function(event) {
        that.resize(event.width, event.height);
      });
    },
    getValue: function() {
      return this.codeMirrorInstance.getValue()
    },
    setValue: function(value) {
      value = value || '';
      this.codeMirrorInstance.setValue(value);
      var that = this;
      setTimeout(function() {
        that.codeMirrorInstance.refresh();
      }, 0);
    },
    setMode: function(mode) {
      this.mode = mode;
      this.codeMirrorInstance.setOption('mode', mode);
      this.loadMode();
    },
    loadMode: function() {
      if (this.mode) {
        CodeMirror.autoLoadMode(this.codeMirrorInstance, this.mode);
      }
    },
    resize: function(width, height) {
      if (!this.options.allowResizeWidth){
        width = null;
      }

      if (height) {
        this.wrapEl.style.height = height + 'px';
      }
      if (width) {
        this.wrapEl.style.width = width + 'px';
      }
      this.codeMirrorInstance.setSize(width, height);
    }
  });

  Y.inputEx.registerType('code', CodeEditor, []);
}
