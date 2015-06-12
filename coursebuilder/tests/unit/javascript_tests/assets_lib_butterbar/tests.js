describe('ButterBar', function() {
  var popup, message, close, butterBar;

  beforeEach(function() {
    jasmine.getFixtures().fixturesPath = 'base/';
    loadFixtures(
        'tests/unit/javascript_tests/assets_lib_butterbar/fixture.html');
    popup = $('#gcb-butterbar-top').get(0);
    message = $('#gcb-butterbar-message').get(0);
    close = $('#gcb-butterbar-close').get(0);
    butterBar = new ButterBar(popup, message, close);
  });

  it('can display text', function() {
    butterBar.showMessage('Hello, World');
    expect(message.textContent).toBe('Hello, World');
    expect(message.innerText).toBe('Hello, World');
    expect(popup.className).toContain('shown');
  });
  it('can be hidden', function() {
    butterBar.hide();
    expect(popup.className).not.toContain('shown');
    butterBar.showMessage('Hello, World!');
    butterBar.hide();
    expect(popup.className).not.toContain('shown');
  });
  it('hides automatically when called with cbShowMsgAutoHide', function() {
    window.clearTimeout = jasmine.createSpy('window.clearTimeout');
    window.setTimeout = jasmine.createSpy('window.setTimeout').and.callFake(
      cbHideMsg);
    cbShowMsgAutoHide('Hello, World!');
    expect(window.clearTimeout).not.toHaveBeenCalled();
    expect(window.setTimeout).toHaveBeenCalledWith(cbHideMsg, 5000);
    expect(popup.className).not.toContain('shown');
  });
  it('restarts timeout when cbShowMsgAutoHide is called twice', function() {
    window.clearTimeout = jasmine.createSpy('window.clearTimeout');
    window.setTimeout = jasmine.createSpy('window.setTimeout')
        .and.returnValue(101);
    cbShowMsgAutoHide('Hello, World!');
    cbShowMsgAutoHide('Hello, World!');
    expect(window.clearTimeout).toHaveBeenCalledWith(101);
    expect(window.setTimeout.calls.count()).toBe(2);
  });
});
