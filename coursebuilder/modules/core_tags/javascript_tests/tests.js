// GoogleDriveTagParent refers to top, but karma tests run inside of an iframe.
// Bind top to window so this difference doesn't cause breakage.
// TODO(johncox): get rid of this when we write real tests using iframs.
top = window;

describe('core tags module', function() {

  window.cb_global = {
    schema: {
      properties: {
        'document-id': {
          '_inputex': {
            'api-key': 'api-key-value',
            'client-id': 'client-id-value',
            'type-id': 'type-id-value',
            'xsrf-token': 'xsrf-token-value'
          }
        }
      }
    }
  };
  window.disableAllControlButtons = function() {};
  window.enableAllControlButtons = function() {};

  describe('parent and child frame tests', function() {
    // TODO(johncox): tests.
    it('runs an empty test', function() {
      // Jasmine requires at least one test
    })
  });

});
