describe('ButterBar', function() {
  var popup, message, butterBar;

  beforeEach(function() {
    popup = {}; // mock
    message = {}; // mock
    butterBar = new ButterBar(popup, message);
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
});
