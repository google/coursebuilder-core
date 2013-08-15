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

  beforeEach(function() {
    Y = {};

    frameProxy = {
      getValue: function() {},
      setValue: function() {},
      submit: function() {},
      close: function() {},
      onLoad: function() {}
    };
    env = {
      form: {
        getValue: function() {},
        setValue: function() {}
      },
      onFormLoad: function() {}
    };

    spyOn(frameProxy, 'getValue').andReturn('parent_form_value');
    spyOn(frameProxy, 'setValue');
    spyOn(frameProxy, 'close');
    spyOn(frameProxy, 'submit');
    spyOn(frameProxy, 'onLoad');
    spyOn(env.form, 'getValue').andReturn('form_value');
    spyOn(env.form, 'setValue');
    spyOn(env, 'onFormLoad');

    framedEditorControls = new FramedEditorControls(Y, frameProxy, env);
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
    spyOn(document, 'getElementById').andReturn(formContainer)
    framedEditorControls.populateForm();
    expect(env.form.setValue).toHaveBeenCalledWith('parent_form_value');
    expect(env.onFormLoad).toHaveBeenCalled();

    window.cbHideMsg = _cbHideMsg;
  });
});

describe('FrameProxy', function() {
  var DEFAULT_VALUE = {value: 'one'};
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
      onSubmit: function() {},
      onClose: function() {}
    };
    spyOn(root, 'appendChild');
    spyOn(root, 'removeChild');
    spyOn(document, 'getElementById').andReturn(root);
    spyOn(document, 'createElement').andReturn(iframe);
    spyOn(callbacks, 'onSubmit');
    spyOn(callbacks, 'onClose');

    proxy =  new FrameProxy(
        'rootid',
        'http://url',
        DEFAULT_VALUE,
        DEFAULT_CONTEXT,
        callbacks.onSubmit,
        callbacks.onClose);
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
    expect(callbacks.onSubmit.calls.length).toEqual(0);
    expect(root.removeChild).toHaveBeenCalledWith(iframe);
    expect(root.className).toEqual('hidden');
  });

  it('does not call its callback on close if it was never opened', function() {
    proxy.close();
    expect(callbacks.onClose.calls.length).toEqual(0);
  });

  it('tidies itself and calls its callback on submit', function() {
    proxy.open();
    proxy.submit();
    expect(callbacks.onSubmit).toHaveBeenCalledWith(DEFAULT_VALUE);
    expect(callbacks.onClose.calls.length).toEqual(0);
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
      execCommand: function() {}
    };
    customRteTagIcons = [
      {name: 'tag_1', iconUrl: 'http://www.icon.com/foo_1.png'},
      {name: 'tag_2', iconUrl: 'http://www.icon.com/foo_2.png'}
    ];
    excludedCustomTags = [];
    frameProxyOpener = {
      open: function(url, value, submit, cancel) {}
    };
    serviceUrlProvider = {
      getAddUrl: function() {
        return 'add_url';
      },
      getEditUrl: function(tag) {
        return 'edit_url?' + tag;
      }
    };

    customTagManager = new CustomTagManager(win, editor, customRteTagIcons,
      excludedCustomTags, frameProxyOpener, serviceUrlProvider);
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
    var img = {
      gcbTag: tag,
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
    customTagManager.addCustomTag();

    // Verification
    expect(frameProxyOpener.open).toHaveBeenCalled();
    expect(frameProxyOpener.open.mostRecentCall.args[0]).toEqual('add_url');
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
    expect(frameProxyOpener.open.mostRecentCall.args[0])
        .toEqual('edit_url?tagname');
  });
});
