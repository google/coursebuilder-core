describe('deepEquals', function() {
  it('matches objects which are equal', function() {
    var a = {
      'a': [1, 2, 3],
      'b': {'c': 'C', 'd': null}
    };
    var b = {
      'b': {'d': null, 'c': 'C'},
      'a': [1, 2, 3]
    };
    expect(deepEquals(a, b)).toBe(true);
  });
  it('distinguishes objects are which are different deep down', function() {
    var a = {
      'a': [1, 2, 3],
      'b': {'c': 'C', 'd': {'e': 5}} // the difference is in 'e'
    };
    var b = {
      'b': {'d': {'e': 4}, 'c': 'C'}, // the difference is in 'e'
      'a': [1, 2, 3]
    };
    expect(deepEquals(a, b)).toBe(false);
  });

  describe("propertyCount", function () {
    it("counts the object's own members", function () {
      var ob = {
        a: 0,
        b: "two",
        c: [1, 2, 3]
      };
      expect(propertyCount(ob)).toBe(3);
    });

    it("doesn't count the superclass's members", function () {
      function f () {};
      f.prototype.a = "super property";
      var ob = new f();
      expect(ob.a).toBe("super property");
      expect(propertyCount(ob)).toBe(0);
    });
  });
});

describe('maybePerformAction', function() {

  beforeEach(function() {
    this.action = jasmine.createSpy('action');
  });
  it('executes the action when no decider is provided', function() {
    maybePerformAction(null, this.action);
    expect(this.action.calls.any()).toEqual(true);
  });
  it('executes the action when the decider returns true', function() {
    maybePerformAction(function() {return true}, this.action);
    expect(this.action.calls.any()).toEqual(true);
  });
  it('does not execute the action when the decider returns false', function() {
    maybePerformAction(function() {return false}, this.action);
    expect(this.action.calls.any()).toEqual(false);
  });
  it('excecutes the action when decider returns a promise, after it is resolved', function() {
    var promise = $.Deferred();
    maybePerformAction(function() {return promise}, this.action);
    expect(this.action.calls.any()).toEqual(false);
    promise.resolve();
    expect(this.action.calls.any()).toEqual(true);
  });
});

describe('setQuestionDescriptionIfEmpty', function() {
  beforeEach(function() {
    var that = this;
    this.description = '';
    this.question = 'question text';
    // Mock the InputEx form object with two fields, description and question
    // which are backed by this.description and this.question.
    this.quForm = {
      _description: {
        getValue: function() { return that.description },
        setValue: function(value) { that.description = value }
      },
      _question: {
        getValue: function() { return that.question }
      },
      getFieldByName: function(name) { return this['_' + name] }
    };
  });
  it('does nothing if the description is already set', function() {
    this.description = 'already set';
    setQuestionDescriptionIfEmpty(this.quForm);
    expect(this.description).toEqual('already set');
  });
  it('sets the description to question text', function() {
    this.question = 'question text';
    setQuestionDescriptionIfEmpty(this.quForm);
    expect(this.description).toEqual('question text');
  });
  it('sets the description to plain question text', function() {
    this.question = '<p>question <b>text</b></p>';
    setQuestionDescriptionIfEmpty(this.quForm);
    expect(this.description).toEqual('question text');});
  it('set the description to truncated question text', function() {
    this.question =
        'question text question text question text question text ' +
        'question text question text question text question text ' +
        'question text question text question text question text ' +
        'question text question text question text question text ';
    setQuestionDescriptionIfEmpty(this.quForm);
    expect(this.description).toEqual(
        'question text question text question text question text q...');
  });
});

describe('parseJson', function() {
  it('strips off XSSI prefix if it\'s present', function() {
    var json = ')]}\'{"a": 2}';
    var parsed = parseJson(json);
    expect(parsed.a).toBe(2);
  });
  it('parses JSON correctly even without the XSSI prefix', function() {
    var json = '{"a": 2}';
    var parsed = parseJson(json);
    expect(parsed.a).toBe(2);
  });
});

describe('FramedEditorControls', function() {
  var framedEditorControls, Y, frameProxy, env;

  function maybePerformAction(decider, action) {
    action();
  };

  beforeEach(function() {
    var that = this;
    Y = {
      all: function(selector) {
        return {
          removeClass: function(className) {}
        };
      },
      one: function(selector) {
        return {
          on: function(event, action) {}
        };
      }
    };

    frameProxy = {
      init: function() {},
      getValue: function() {},
      setValue: function() {},
      submit: function() {},
      close: function() {},
      onLoad: function() {},
      onBackgroundClick: function(callback) {
        that.backgroundClick = callback;
      }
    };
    env = {
      form: {
        getValue: function() {},
        setValue: function() {},
        validate: function() { return true }
      },
      schema: {},
      onFormLoad: function() {}
    };

    spyOn(frameProxy, 'init');
    spyOn(frameProxy, 'getValue').and.returnValue('parent_form_value');
    spyOn(frameProxy, 'setValue');
    spyOn(frameProxy, 'close');
    spyOn(frameProxy, 'submit');
    spyOn(frameProxy, 'onLoad');
    spyOn(env.form, 'getValue').and.returnValue('form_value');
    spyOn(env.form, 'setValue');
    spyOn(env, 'onFormLoad');

    this.alertIfNotSavedChanges = jasmine.createSpy('alertIfNotSavedChanges');
    this.confirm = spyOn(window, 'confirm');

    framedEditorControls = new FramedEditorControls(Y, frameProxy, env,
        maybePerformAction, this.alertIfNotSavedChanges);
  });

  describe('the save button', function() {
    var saveButton;

    beforeEach(function() {
      saveButton = framedEditorControls.getSaveButton();
    });

    it('is a link with value "Save"', function() {
      expect(saveButton.type).toEqual('submit-link');
      expect(saveButton.value).toEqual('Save');
    });

    it('sets the form value and submits on click', function() {
      saveButton.onClick();
      expect(frameProxy.setValue).toHaveBeenCalledWith('form_value');
      expect(frameProxy.submit).toHaveBeenCalled();
    });
  });

  describe('the close button', function() {
    var closeButton;

    beforeEach(function() {
      closeButton = framedEditorControls.getCloseButton();
    });

    it('is a link with value "Close"', function() {
      expect(closeButton.type).toEqual('link');
      expect(closeButton.value).toEqual('Close');
    });

    it('closes the iframe on click', function() {
      closeButton.onClick();
      expect(frameProxy.close).toHaveBeenCalled();
    });

    it('does not ask for confirmation if the form has not changed', function() {
      this.alertIfNotSavedChanges.and.returnValue(null);
      closeButton.onClick();
      expect(this.confirm).not.toHaveBeenCalled();
      expect(frameProxy.close).toHaveBeenCalled();
    });

    it('asks for confirmation if the form has changed', function() {
      var message = 'Values have changed'
      this.alertIfNotSavedChanges.and.returnValue(message);
      this.confirm.and.returnValue(false);
      closeButton.onClick();
      expect(this.confirm.calls.argsFor(0)[0]).toContain(message);
      expect(frameProxy.close).not.toHaveBeenCalled();
    });

    it('closes if confirmation given when the form has changed', function() {
      var message = 'Values have changed'
      this.alertIfNotSavedChanges.and.returnValue(message);
      this.confirm.and.returnValue(true);
      closeButton.onClick();
      var confirmMessage = this.confirm.calls.argsFor(0)[0];
      expect(confirmMessage).toContain(message);
      expect(confirmMessage).toContain('Are you sure you want to close?');
      expect(frameProxy.close).toHaveBeenCalled();
    });

    it('closes on a background click', function() {
      this.alertIfNotSavedChanges.and.returnValue(null);
      this.backgroundClick();
      expect(this.confirm).not.toHaveBeenCalled();
      expect(frameProxy.close).toHaveBeenCalled();
    });
  });

  it("doesn't have a delete button", function() {
    expect(framedEditorControls.getDeleteButton()).toBeNull();
  });

  it('populates the form from the parent frame', function() {
    var _cbHideMsg = window.cbHideMsg;
    window.cbHideMsg = function() {};

    var formContainer = {
      style: {}
    }
    spyOn(document, 'getElementById').and.returnValue(formContainer)
    framedEditorControls.populateForm();
    expect(frameProxy.init).toHaveBeenCalledWith(env.schema);
    expect(env.form.setValue).toHaveBeenCalledWith('parent_form_value');
    expect(env.onFormLoad).toHaveBeenCalled();

    window.cbHideMsg = _cbHideMsg;
  });
});

describe('FrameProxy', function() {
  var DEFAULT_VALUE = {value: 'one'};
  var DEFAULT_SCHEMA = {'properties' : {}};
  var DEFAULT_CONTEXT = {};
  var proxy, root, iframe, callbacks;

  beforeEach(function() {
    root = {
      appendChild: function() {},
      removeChild: function() {}
    };
    iframe = {
      contentWindow: {
        document: {
          body: {}
        }
      },
      style: {}
    };
    callbacks = {
      getValue: function() {},
      onSubmit: function() {},
      onClose: function() {}
    };
    spyOn(root, 'appendChild');
    spyOn(root, 'removeChild');
    spyOn(document, 'getElementById').and.returnValue(root);
    spyOn(document, 'createElement').and.returnValue(iframe);
    spyOn(callbacks, 'getValue').and.returnValue(DEFAULT_VALUE);
    spyOn(callbacks, 'onSubmit');
    spyOn(callbacks, 'onClose');

    proxy =  new FrameProxy(
        window,
        'rootid',
        'http://url',
        callbacks.getValue,
        DEFAULT_CONTEXT,
        callbacks.onSubmit,
        callbacks.onClose);
    proxy.init(DEFAULT_SCHEMA);
  });

  it('opens an iframe', function() {
    proxy.open();

    expect(document.getElementById).toHaveBeenCalledWith('rootid');
    expect(document.createElement).toHaveBeenCalledWith('iframe');
    expect(root.appendChild).toHaveBeenCalledWith(iframe);
  });

  it('can retrieve its value', function() {
    expect(proxy.getValue()).toBe(DEFAULT_VALUE);
  });

  it('can set its value', function() {
    var value = {a: 'b'};
    proxy.setValue(value);
    expect(proxy.getValue()).toBe(value);
  });

  it('adjusts its height on load', function() {
    proxy.open();
    iframe.contentWindow.document.body.clientHeight = 100;
    expect(iframe.style.height).toBeUndefined();
    expect(iframe.style.marginTop).toBeUndefined();

    proxy.onLoad();
    expect(iframe.style.height).toBe('150px'); // height = 50px + padding
    expect(iframe.style.marginTop).toBe('-75px'); // move up by half height
  });

  it('tidies itself and calls its callback on close', function() {
    proxy.open();
    proxy.close();
    expect(callbacks.onClose).toHaveBeenCalled();
    expect(callbacks.onSubmit.calls.count()).toEqual(0);
    expect(root.removeChild).toHaveBeenCalledWith(iframe);
    expect(root.className).toEqual('hidden');
  });

  it('does not call its callback on close if it was never opened', function() {
    proxy.close();
    expect(callbacks.onClose.calls.count()).toEqual(0);
  });

  it('tidies itself and calls its callback on submit', function() {
    proxy.open();
    proxy.submit();
    expect(callbacks.onSubmit)
        .toHaveBeenCalledWith(DEFAULT_VALUE, DEFAULT_SCHEMA);
    expect(callbacks.onClose.calls.count()).toEqual(0);
    expect(root.removeChild).toHaveBeenCalledWith(iframe);
    expect(root.className).toEqual('hidden');
  });
});

describe('CustomTagManager', function() {
  var customTagManager, win, editor, customRteTagIcons, excludedCustomTags,
      frameProxyOpener, serviceUrlProvider;

  beforeEach(function() {
    win = {
      document: {
        body: {},
        getElementsByTagName: function() {
          return [];
        }
      }
    };
    editor = {
      execCommand: function() {},
      getEditorHTML: function() { return ''; },
      _putUndo: function() {}
    };
    customRteTagIcons = [
      {name: 'tag_1', iconUrl: 'http://www.icon.com/foo_1.png'},
      {name: 'tag_2', iconUrl: 'http://www.icon.com/foo_2.png'}
    ];
    frameProxyOpener = {
      open: function(url, value, submit, cancel) {}
    };
    serviceUrlProvider = {
      getEditUrl: function(tag) {
        return 'edit_url?' + tag;
      }
    };

    customTagManager = new CustomTagManager(win, editor, customRteTagIcons,
      frameProxyOpener, serviceUrlProvider);
  });

  it('replaces a tag with marker images', function() {
    // Mocking
    var tag = {
      parentNode: {
        replaceChild: function() {}
      }
    };
    spyOn(tag.parentNode, 'replaceChild');
    win.document.getElementsByTagName = function(tagName) {
      return tagName == 'tag_1' ? [tag] : [];
    };
    var img = {
      style: {}
    };
    win.document.createElement = function(name) {
      if (name == 'img') {
        return img;
      }
    };

    // Testing
    customTagManager.insertMarkerTags();

    // Verification
    expect(tag.parentNode.replaceChild).toHaveBeenCalledWith(img, tag);
    expect(img.src).toEqual('http://www.icon.com/foo_1.png');
    expect(img.className).toEqual('gcbMarker');
  });


  it('restores tags from marker images', function() {
    // Mocking
    var tag = {};
    customTagManager._markerTagElements.push(tag);
    var img = {
      id: 'markerTag-0',
      parentNode: {
        replaceChild: function() {}
      }
    };
    spyOn(img.parentNode, 'replaceChild');
    win.document.querySelectorAll = function(selector) {
      return selector == '.gcbMarker' ? [img] : [];
    };

    // Testing
    customTagManager.removeMarkerTags();

    // Verification
    expect(img.parentNode.replaceChild).toHaveBeenCalledWith(tag, img);
  });


  it('removes marker images with no stored tags', function() {
    // Mocking
    var img = {
      parentNode: {
        removeChild: function() {}
      }
    };
    spyOn(img.parentNode, 'removeChild');
    win.document.querySelectorAll = function(selector) {
      return selector == '.gcbMarker' ? [img] : [];
    };

    // Testing
    customTagManager.removeMarkerTags();

    // Verification
    expect(img.parentNode.removeChild).toHaveBeenCalled();
  });

  it('opens a lightbox to add a tag', function() {
    // Mocking
    spyOn(frameProxyOpener, 'open');

    // Testing
    customTagManager.addCustomTag('gcb-math');

    // Verification
    expect(frameProxyOpener.open).toHaveBeenCalled();
    expect(frameProxyOpener.open.calls.mostRecent().args[0])
        .toEqual('edit_url?gcb-math');
  });

  it('opens a lightbox to edit a tag', function() {
    // Mocking
    var node = {
      tagName: 'tagName',
      attributes: [
        {name: 'name_1', value: 'value_1'},
        {name: 'name_2', value: 'value_2'}
      ]
    };
    spyOn(frameProxyOpener, 'open');

    // Testing
    customTagManager._editCustomTag(node);

    // Verification
    expect(frameProxyOpener.open).toHaveBeenCalled();
    expect(frameProxyOpener.open.calls.mostRecent().args[0])
        .toEqual('edit_url?tagname');
  });
});

describe('URL Validation', function() {
  it('doesn\'t match ambiguous URLs', function() {
    expect('foo.bar'.match(URL_VALIDATION_REGEX)).toBeNull();
    expect('foo.bar/baz'.match(URL_VALIDATION_REGEX)).toBeNull();
    expect('foo.bar.baz'.match(URL_VALIDATION_REGEX)).toBeNull();
    expect('foo.bar.baz/qux'.match(URL_VALIDATION_REGEX)).toBeNull();
  });

  it('matches relative URLs', function() {
    expect("foo".match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect("foo/bar".match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect("foo/bar.baz".match(URL_VALIDATION_REGEX)).not.toBeNull();
  });

  it('matches absolute URLs', function() {
    expect('/foo'.match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect('/foo/bar'.match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect('/foo.bar'.match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect('/foo.bar/baz'.match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect('/foo.bar/baz.qux'.match(URL_VALIDATION_REGEX)).not.toBeNull();

    expect('//foo'.match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect('//foo/bar'.match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect('//foo.bar'.match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect('//foo.bar/baz'.match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect('//foo.bar/baz.qux'.match(URL_VALIDATION_REGEX)).not.toBeNull();

    expect('http://foo'.match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect('http://foo/bar'.match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect('http://foo.bar'.match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect('http://foo.bar/baz'.match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect('http://foo.bar/baz.qux'.match(URL_VALIDATION_REGEX)).not.toBeNull();

    expect('https//foo'.match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect('https//foo/bar'.match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect('https//foo.bar'.match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect('https//foo.bar/baz'.match(URL_VALIDATION_REGEX)).not.toBeNull();
    expect('https//foo.bar/baz.qux'.match(URL_VALIDATION_REGEX)).not.toBeNull();
  });
});
