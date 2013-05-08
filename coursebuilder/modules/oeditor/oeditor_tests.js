describe("the tests for propertyCount", function () {

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

describe('tests for FramedEditorControls', function() {
  var framedEditorControls, frameProxy, env;

  beforeEach(function() {
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

    framedEditorControls = new FramedEditorControls(frameProxy, env);
  });

  describe('tests for the save button', function() {
    var saveButton;

    beforeEach(function() {
      saveButton = framedEditorControls.getSaveButton();
    });

    it('is a link with value "Save"', function() {
      expect(saveButton.type).toEqual('link');
      expect(saveButton.value).toEqual('Save');
    });

    it('sets the form value and submits on click', function() {
      saveButton.onClick();
      expect(frameProxy.setValue).toHaveBeenCalledWith('form_value');
      expect(frameProxy.submit).toHaveBeenCalled();
    });
  });

  describe('tests for the close button', function() {
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

describe('the tests for FrameProxy', function() {
  var DEFAULT_VALUE = {value: 'one'};
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
