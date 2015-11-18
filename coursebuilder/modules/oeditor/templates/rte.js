function bindEditorField(Y) {
  var RTE_TAG_DATA = cb_global.rte_tag_data;
  var PREVIEW_XSRF_TOKEN = cb_global.preview_xsrf_token;

  /**
   * An editor component which provides HTML syntax highlighting.
   * See TextAreaEditor for the full documentation of the interface.
   *
   * @class
   */
  function HtmlEditor(root) {
    var that = this;
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
  HtmlEditor.prototype.isReady = function() {
    var ready = $.Deferred();
    ready.resolve();
    return ready;
  };
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
    value = value || '';
    this.codeMirrorInstance.setValue(value);
    var that = this;
    setTimeout(function() {
      that.codeMirrorInstance.refresh();
    }, 0);
  };
  HtmlEditor.prototype.disable = function() {
    this.codeMirrorInstance.setOption('readOnly', 'nocursor');
  };

  /**
   * An editor component which provides plain text editing in a textarea.
   * TODO(nretallack): Delete this class. It is no longer used.
   *
   * @class
   * @param root {Element} The root element to hold the editor's HTML.
   */
  function TextareaEditor(root) {
    this.textarea = document.createElement('textarea');
    root.appendChild(this.textarea);
  }
  /**
   * Return a promise for the editor being fully loaded.
   *
   * @method
   */
  TextareaEditor.prototype.isReady = function() {
    var ready = $.Deferred();
    ready.resolve();
    return ready;
  };
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
  function RichTextEditor(root, options) {
    var that = this;

    this.root = root;
    this.excludedCustomTags = options.excludedCustomTags || [];

    var textarea = document.createElement('textarea');
    root.appendChild(textarea);

    var attrs = {
      extracss: this.EXTRA_CSS,
    };
    var buttonSet = this.FULL_BUTTON_SET;
    if (options['rteButtonSet'] == 'reduced') {
      buttonSet = this.REDUCED_BUTTON_SET;
    }
    attrs.toolbar = $.extend(true, {}, {buttons: buttonSet});
    // The YUI method of autocomputing the url from the CSS isn't working in
    // Firefox in the inline editor, so set the url explicitly.
    // See: yui2-editor.js Editor._getBlankImage()
    attrs.blankimage = '/static/2in3/2in3-master/dist/2.9.0/build/' +
        'yui2-skin-sam-editor/assets/skins/sam/blankimage.png';

    this.editor = new Y.YUI2.widget.Editor(textarea, attrs);
    this._disableHtmlCleaning();

    this.editorIsRendered = $.Deferred(function(def) {
      // See:
      //   http://yui.github.io/yui2/docs/yui_2.9.0_full/docs/YAHOO.widget.SimpleEditor.html#event_editorContentLoaded
      that.editor.on('editorContentLoaded', function() {
        def.resolve();
      });
    });
    this.editorIsVisible = $.Deferred();

    // Reveal the toolbar on focus and hide it on blur
    this.toolbarSlideInProgress = false;
    this.editor.on('editorWindowFocus', this._onEditorWindowFocus.bind(this));
    this.editor.on('editorWindowBlur', this._onEditorWindowBlur.bind(this));
    $(this.root)
        .on('mouseenter', function() { that.mouseEntered = true })
        .on('mouseleave', function() { that.mouseEntered = false });

    this._customTagManager = new DummyCustomTagManager();
    if (options.supportCustomTags) {
      $.when(this.editorIsRendered).then(function() {
        that._addCustomComponentButtons();
        that._bindCustomTagManager();
      });
    }

    this.editor.render();
    this.setValue('');
  }
  RichTextEditor.prototype.EXTRA_CSS =
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
  /* See http://yui.github.io/yui2/docs/yui_2.9.0_full/examples/editor/toolbar_editor.html */
  RichTextEditor.prototype.FULL_BUTTON_SET = [
    {
      group: 'fontstyle', label: 'Font Name and Size',
      buttons: [
        {
          type: 'select', label: 'Arial', value: 'fontname', disabled: true,
          menu: [
            { text: 'Arial', checked: true },
            { text: 'Arial Black' },
            { text: 'Comic Sans MS' },
            { text: 'Courier New' },
            { text: 'Lucida Console' },
            { text: 'Tahoma' },
            { text: 'Times New Roman' },
            { text: 'Trebuchet MS' },
            { text: 'Verdana' }
          ]
        },
        { type: 'spin', label: '13', value: 'fontsize', range: [ 9, 75 ], disabled: true }
      ]
    },
    { type: 'separator' },
    {
      group: 'textstyle', label: 'Font Style',
      buttons: [
        { type: 'push', label: 'Bold CTRL + SHIFT + B', value: 'bold' },
        { type: 'push', label: 'Italic CTRL + SHIFT + I', value: 'italic' },
        { type: 'push', label: 'Underline CTRL + SHIFT + U', value: 'underline' },
        { type: 'separator' },
        { type: 'push', label: 'Subscript', value: 'subscript', disabled: true },
        { type: 'push', label: 'Superscript', value: 'superscript', disabled: true },
        { type: 'separator' },
        { type: 'color', label: 'Font Color', value: 'forecolor', disabled: true },
        { type: 'color', label: 'Background Color', value: 'backcolor', disabled: true },
        { type: 'separator' },
        { type: 'push', label: 'Remove Formatting', value: 'removeformat', disabled: true },
        { type: 'push', label: 'Show/Hide Hidden Elements', value: 'hiddenelements' }
      ]
    },
    { type: 'separator' },
    {
      group: 'alignment', label: 'Alignment',
      buttons: [
        { type: 'push', label: 'Align Left CTRL + SHIFT + [', value: 'justifyleft' },
        { type: 'push', label: 'Align Center CTRL + SHIFT + |', value: 'justifycenter' },
        { type: 'push', label: 'Align Right CTRL + SHIFT + ]', value: 'justifyright' },
        { type: 'push', label: 'Justify', value: 'justifyfull' }
      ]
    },
    { type: 'separator' },
    {
      group: 'parastyle', label: 'Paragraph Style',
      buttons: [
        {
          type: 'select', label: 'Normal', value: 'heading', disabled: true,
          menu: [
            { text: 'Normal', value: 'none', checked: true },
            { text: 'Header 1', value: 'h1' },
            { text: 'Header 2', value: 'h2' },
            { text: 'Header 3', value: 'h3' },
            { text: 'Header 4', value: 'h4' },
            { text: 'Header 5', value: 'h5' },
            { text: 'Header 6', value: 'h6' }
          ]
        }
      ]
    },
    { type: 'separator' },
    {
      group: 'indentlist', label: 'Indenting and Lists',
      buttons: [
        { type: 'push', label: 'Indent', value: 'indent', disabled: true },
        { type: 'push', label: 'Outdent', value: 'outdent', disabled: true },
        { type: 'push', label: 'Create an Unordered List', value: 'insertunorderedlist' },
        { type: 'push', label: 'Create an Ordered List', value: 'insertorderedlist' }
      ]
    },
    { type: 'separator' },
    {
      group: 'insertitem', label: 'Insert Item',
      buttons: []
    }
  ];
  /* See http://yui.github.io/yui2/docs/yui_2.9.0_full/examples/editor/toolbar_editor.html */
  RichTextEditor.prototype.REDUCED_BUTTON_SET = [
    {
      group: 'fontstyle', label: 'Font Name and Size',
      buttons: [
        {
          type: 'select', label: 'Arial', value: 'fontname', disabled: true,
          menu: [
            { text: 'Arial', checked: true },
            { text: 'Arial Black' },
            { text: 'Comic Sans MS' },
            { text: 'Courier New' },
            { text: 'Lucida Console' },
            { text: 'Tahoma' },
            { text: 'Times New Roman' },
            { text: 'Trebuchet MS' },
            { text: 'Verdana' }
          ]
        },
        { type: 'spin', label: '13', value: 'fontsize', range: [ 9, 75 ], disabled: true }
      ]
    },
    { type: 'separator' },
    {
      group: 'textstyle', label: 'Font Style',
      buttons: [
        { type: 'push', label: 'Bold CTRL + SHIFT + B', value: 'bold' },
        { type: 'push', label: 'Italic CTRL + SHIFT + I', value: 'italic' },
        { type: 'push', label: 'Underline CTRL + SHIFT + U', value: 'underline' },
        { type: 'color', label: 'Font Color', value: 'forecolor', disabled: true },
        { type: 'color', label: 'Background Color', value: 'backcolor', disabled: true }
      ]
    },
    {
      group: 'indentlist', label: 'Indenting and Lists',
      buttons: [
        { type: 'push', label: 'Create an Unordered List', value: 'insertunorderedlist' },
        { type: 'push', label: 'Create an Ordered List', value: 'insertorderedlist' }
      ]
    },
    {
      group: 'insertitem', label: 'Insert Item',
      buttons: []
    }
  ];
  /**
   * This list holds the tag names of tags in the order in which their buttons
   * should be displayed. Because of the loose-coupling between OEditor and the
   * other modules which provide the tags, this ordering is only best-effort.
   * Tag authors may change the binding name of their tag or introduce new tags
   * which are not listed here. This should not be assumed to be a comprehensive
   * list.
   */
  RichTextEditor.prototype.TAG_BUTTON_ORDER = [
    'question',
    'question-group',
    'gcb-youtube',
    'insertimage',
    'gcb-googlegroup',
    'gcb-questionnaire',
    'gcb-googledrive',
    'gcb-googledoc',
    'gcb-googlespreadsheet',
    'gcb-include',
    'gcb-code',
    'gcb-math',
    'gcb-markdown',
    'gcb-html5video',
    'gcb-iframe',
    'createlink',
    'text-file-upload-tag',
  ];

  RichTextEditor.prototype.isReady = function() {
    return this.editorIsRendered;
  };
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

    if (this.toolbarSlideInProgress) {
      return;
    }

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
      that.editor.setEditorHTML(value || '');
      that._customTagManager.insertMarkerTags();
    });
  };
  RichTextEditor.prototype.disable = function() {
    var that = this;
    $.when(this.editorIsRendered).then(function() {
      that.editor.set('disabled', true);
      that.editor.get('iframe').setStyle('display', 'block');
    });
  };
  RichTextEditor.prototype._tagButtonCompare = function(button1, button2) {
    function strCmp(a, b) {
      if (a < b) {
        return -1;
      } else if (a === b) {
        return 0;
      } else {
        return 1;
      }
    }
    var index1 = this.TAG_BUTTON_ORDER.indexOf(button1.value);
    var index2 = this.TAG_BUTTON_ORDER.indexOf(button2.value);

    if (index1 > -1 && index2 > -1) {
      return index1 - index2;
    } else if (index1 > -1 && index2 == -1) {
      // If button1 is in the list and button2 is not, then button1 comes first
      return -1;
    } else if (index1 == -1 && index2 > -1) {
      // If button1 is not in the list and button2 is, then button1 comes after
      return 1;
    } else {
      return strCmp(button1.label, button2.label);
    }
  };

  RichTextEditor.prototype._addCustomComponentButtons = function() {
    // Add buttons to the tool bar for each of the CB custom components.
    var that = this;
    var buttonDefs = [
      {
        type: 'push',
        label: 'HTML Link',
        value: 'createlink',
        disabled: false
      },
      {
        type: 'push',
        label: 'Image',
        value: 'insertimage',
        disabled: false
      }
    ];
    for (var i = 0; i < RTE_TAG_DATA.length; i++) {
      var componentData = RTE_TAG_DATA[i];
      if (this.excludedCustomTags.indexOf(componentData.name) >= 0) {
        continue;
      }
      buttonDefs.push({
        type: 'push',
        label: componentData.label,
        value: componentData.name,
        disabled: false
      });
    }
    buttonDefs.sort(this._tagButtonCompare.bind(this));

    for (var i = 0; i < buttonDefs.length; i++) {
      this.editor.toolbar.addButtonToGroup(buttonDefs[i], 'insertitem');
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
        return;
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
      new FrameProxyOpener(window.top),
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
  RichTextEditor.prototype._slideToolbarInOut = function (slideIn) {
    var that = this;
    var toolbar = $(this.editor.toolbar.get('element'));
    var editorContainer =$(this.root).find('.yui-editor-editable-container');
    var editorHeight = editorContainer.height();
    var toolbarHeight = toolbar.find('fieldset').height();

    if (slideIn) {
      toolbar.css('height', toolbarHeight);
      this.editor.set('height', (editorHeight - toolbarHeight) + 'px');
    } else {
      toolbar.css('height', 0);
      this.editor.set('height', (editorHeight + toolbarHeight) + 'px');
      toolbar.removeClass('slid-in');
    }
    this.toolbarSlideInProgress = true;
    editorContainer.addClass('slow-transition');
    this.toolbarSlideFinished = $.Deferred(function(def) {
      setTimeout(function() {
        that.toolbarSlideInProgress = false;
        editorContainer.removeClass('slow-transition');
        if (slideIn) {
          toolbar.addClass('slid-in');
        }
      }, 500);
    });
  };
  RichTextEditor.prototype._onEditorWindowFocus = function() {
    if (! this.toolbarSlideInProgress) {
      this._slideToolbarInOut(true);
    }
  };
  RichTextEditor.prototype._slideOutIsAllowed = function() {
    // A loss of focus can occur when (i) the font name chooser grabs the
    // focus, or (ii) when the image or link editor opens. Don't hide the
    // toolbar in those cases.
    return !this.toolbarSlideInProgress && !this.mouseEntered;
  };
  RichTextEditor.prototype._onEditorWindowBlur = function() {
    if (this._slideOutIsAllowed()) {
      this._slideToolbarInOut(false);
    }
  };

  /**
   * An "editor" component which displays the text in an iframe with the CSS
   * styling for the student view.
   * See TextAreaEditor for the full documentation of the interface.
   *
   * @class
   * @param root {Element} The root element to hold the editor's HTML.
   */
  function PreviewEditor(root) {
    var that = this;
    root.innerHTML =
        '<div class="preview-editor">' +
        '  <div class="ajax-spinner">' +
        '    <div class="background"></div>' +
        '    <span class="spinner md md-settings md-spin"></span>' +
        '  </div>' +
        '  <iframe></iframe>' +
        '</div>';
    this.previewEditorDiv = root.querySelector('div.preview-editor');
    this.iframe = root.querySelector('iframe');
    this.ajaxSpinner = root.querySelector('div.ajax-spinner');

    this.iframeIsLoaded = $.Deferred();
    this.iframeIsLoaded.resolve()

    $(window).on('message', function(evt) {
      if (evt.originalEvent.origin == window.location.origin &&
          evt.originalEvent.source == that.iframe.contentWindow &&
          evt.originalEvent.data == 'preview_editor_loaded') {
        that.iframeIsLoaded.resolve();
        that._hideAjaxSpinner();
      }
    });
  }
  PreviewEditor.prototype.isReady = function() {
    return this.iframeIsLoaded;
  };
  PreviewEditor.prototype.hide = function() {
    this.previewEditorDiv.style.display = 'none';
  };
  PreviewEditor.prototype.show = function() {
    this.previewEditorDiv.style.display = null;
  };
  PreviewEditor.prototype.setSize = function(width, height) {
    if (width) {
      this.previewEditorDiv.style.width = width + 'px';
    }
    this.previewEditorDiv.style.height = height + 'px';
  };
  PreviewEditor.prototype.getValue = function() {
    return this.value;
  };
  PreviewEditor.prototype.setValue = function(value) {
    var that = this;
    if (this.value === value) {
      return;
    }
    this.value = value;
    if (!this.iframe.src) {
      this.iframe.src = 'oeditor/preview';
      this.iframeIsLoaded = $.Deferred();
    }
    $.when(this.iframeIsLoaded).then(function() {
      that._showAjaxSpinner();
      that._reloadIframe(that.value);
      that.iframeIsLoaded = $.Deferred();
    });
  };
  PreviewEditor.prototype._showAjaxSpinner = function(value) {
    this.ajaxSpinner.style.display = null;
  };
  PreviewEditor.prototype._hideAjaxSpinner = function(value) {
    this.ajaxSpinner.style.display = 'none';
  };
  PreviewEditor.prototype._reloadIframe = function(value) {
    var doc = this.iframe.contentWindow.document;
    var form = doc.getElementById('preview-editor-form');
    var xsrf_token = doc.getElementById('xsrf_token');
    var input = doc.getElementById('preview-editor-value');

    xsrf_token.value = PREVIEW_XSRF_TOKEN;
    input.value = value;
    form.submit();
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
    this.lastValueSet = '';
    this.richTextEditorHasBeenSelected = false;
  }
  Y.extend(EditorField, Y.inputEx.Field);

  EditorField.prototype.HTML_EDITOR = 'html';
  EditorField.prototype.RICH_TEXT_EDITOR = 'rte';
  EditorField.prototype.PREVIEW_EDITOR = 'preview';

  EditorField.prototype.HTML_EDITOR_LABEL = 'code';
  EditorField.prototype.RICH_TEXT_EDITOR_LABEL = 'text_format';
  EditorField.prototype.PREVIEW_EDITOR_LABEL = 'visibility';

  EditorField.prototype.setOptions = function(options) {
    EditorField.superclass.setOptions.call(this, options);
    // Don't call this field options as this conflicts with a name in superclass
    this._options = options;
    this.allowResizeWidth = !isNewFormLayout();
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
        '<div class="buttonbar-div"></div>' +
        '<div class="editors-div">' +
        '  <div class="html-div"></div>' +
        '  <div class="rte-div"></div>' +
        '  <div class="preview-div"></div>' +
        '</div>';
    this.editorsDiv = this.fieldContainer.querySelector('.editors-div');
    this.htmlDiv = this.fieldContainer.querySelector('.html-div');
    this.rteDiv = this.fieldContainer.querySelector('.rte-div');
    this.previewDiv = this.fieldContainer.querySelector('.preview-div');

    this.htmlEditor = new HtmlEditor(this.htmlDiv);
    this.richTextEditor = new RichTextEditor(this.rteDiv, this._options);
    this.previewEditor = new PreviewEditor(this.previewDiv);

    // Bind the buttons
    this.tabbar = new TabBar('gcb-toggle-button-bar');
    this.tabbar.addTab(
        this.RICH_TEXT_EDITOR_LABEL, 'material-icons gcb-toggle-button',
        function() {
          that.setEditorType(that.RICH_TEXT_EDITOR);
        });
    this.tabbar.addTab(
        this.HTML_EDITOR_LABEL, 'material-icons gcb-toggle-button',
        function() {
          that.setEditorType(that.HTML_EDITOR);
        });
    this.tabbar.addTab(
        this.PREVIEW_EDITOR_LABEL, 'material-icons gcb-toggle-button',
        function() {
          that.setEditorType(that.PREVIEW_EDITOR);
        });
    var buttonbarDiv = this.fieldContainer.querySelector('.buttonbar-div');
    buttonbarDiv.appendChild(this.tabbar.getRoot());

    // Default mode is HTML editing
    this.activeEditor = this.richTextEditor;
    this.tabbar.selectTabByLabel(this.RICH_TEXT_EDITOR_LABEL);
    this.richTextEditor.show();
    this.htmlEditor.hide();
    this.previewEditor.hide();

    // Bind the resizer
    new Y.YUI2.util.Resize(this.editorsDiv, {
      handles: ['br'],
      minHeight: 100,
      minWidth: 200,
      proxy: true,
      setSize: false
    }).on('resize', function(evt) {
      that._resize(evt.width, evt.height);
    });
    // The computed size of the editorDiv should determine the size of the
    // editors. Poll the div to catch all possible changes.
    setInterval(function() {
      var rect = that.editorsDiv.getBoundingClientRect();
      that.activeEditor.setSize(
          rect.width - 2 /* border */, rect.height - 2 /* border */);
    }, 100);
  };
  EditorField.prototype.setValue = function(value, sendUpdatedEvt) {
    this.lastValueSet = value;
    this.activeEditor.setValue(value);
    if(sendUpdatedEvt !== false) {
      this.fireUpdatedEvt();
    }
  };
  EditorField.prototype.getValue = function() {
    if (this.activeEditor.isReady().state() !== 'resolved') {
      return this.lastValueSet;
    }
    return this.activeEditor.getValue();
  };
  EditorField.prototype.getEditorType = function() {
    if (this.activeEditor === this.htmlEditor) {
      return this.HTML_EDITOR;
    } else if (this.activeEditor === this.richTextEditor) {
      return this.RICH_TEXT_EDITOR;
    } else if (this.activeEditor === this.previewEditor) {
      return this.PREVIEW_EDITOR;
    } else {
      return null;
    }
  };
  EditorField.prototype.setEditorType = function(editorType) {
    var that = this;

    var originEditor = this.activeEditor;
    var targetEditor;
    var targetLabel;

    if (editorType == this.HTML_EDITOR) {
      targetEditor = this.htmlEditor;
      targetLabel = this.HTML_EDITOR_LABEL;
    } else if (editorType == this.RICH_TEXT_EDITOR) {
      targetEditor = this.richTextEditor;
      targetLabel = this.RICH_TEXT_EDITOR_LABEL;
      this.richTextEditorHasBeenSelected = true;
    } else if (editorType == this.PREVIEW_EDITOR) {
      targetEditor = this.previewEditor;
      targetLabel = this.PREVIEW_EDITOR_LABEL;
    }

    $.when(originEditor.isReady(), targetEditor.isReady()).then(function() {
      that._select(targetEditor);
      that.tabbar.selectTabByLabel(targetLabel);
    });
  };
  EditorField.prototype.disable = function() {
    this.richTextEditor.disable();
    this.htmlEditor.disable();
  };
  EditorField.prototype._select = function (editor) {
    var value;
    if (this.activeEditor === this.richTextEditor &&
        editor !== this.richTextEditor &&
        ! this.richTextEditorHasBeenSelected) {
      // In order to avoid automatically round-tripping content through the
      // RTE, we refuse to copy values from the RTE into another editor until
      // the RTE has been actively chosen by the user at least once.
      value = this.lastValueSet;
    } else {
      value = this.activeEditor.getValue();
    }
    var rect = this.editorsDiv.getBoundingClientRect();
    this.activeEditor.hide();
    this.activeEditor = editor;
    this.activeEditor.setValue(value);
    this.activeEditor.setSize(rect.width, rect.height);
    editor.show();
  };
  EditorField.prototype._resize = function(width, height) {
    if (!this.allowResizeWidth) {
      this.editorsDiv.style.height = height + 'px';
      this.activeEditor.setSize(null, height);
    } else {
      this.editorsDiv.style.width = width + 'px';
      this.editorsDiv.style.height = height + 'px';
      this.activeEditor.setSize(width, height);
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
  this._win.frameProxy = new FrameProxy(this._win, 'modal-editor', url,
      getValue, context, submit, cancel);
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
        var type = properties[name].type;
        if (type === "object" || type === "array") {
          continue;
        } else if (type === "text") {
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
