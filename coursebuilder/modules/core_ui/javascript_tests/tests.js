describe('Core UI', function() {

  beforeEach(function() {
    cbShowMsg = jasmine.createSpy('showMsg');
    cbShowMsgAutoHide = jasmine.createSpy('showMsgAutoHide');
    cbHideMsg = jasmine.createSpy('hideMsg');

    jasmine.getFixtures().fixturesPath = 'base/';
    loadFixtures('modules/core_ui/javascript_tests/fixture.html');
  });

  afterEach(function() {
    delete cbShowMsg;
    delete cbShowMsgAutoHide;
    delete cbHideMsg;

    // Tidy up any leftover lightboxes
    $(document.body).empty();
  });

  describe('Lighbox', function() {
    beforeEach(function() {
      this.root = $('#root');
      this.lightbox = new gcb.Lightbox();
    });

    it('adds hidden lighbox to the DOM when bound', function() {
      expect(this.root.find('div.lightbox').length).toEqual(0);
      this.lightbox.bindTo(this.root);
      expect(this.root.find('div.lightbox').length).toEqual(1);
      expect(this.root.find('div.lightbox')).toBeHidden();
    });

    it('becomes visible when shown', function() {
      this.lightbox.bindTo(this.root).show();
      expect(this.root.find('div.lightbox')).toBeVisible();
    });

    it('is removed when closed', function() {
      this.lightbox.bindTo(this.root).show().close();
      expect(this.root.find('div.lightbox').length).toEqual(0);
    });

    it('closes when background is clicked', function() {
      this.lightbox.bindTo(this.root).show();
      expect(this.root.find('div.lightbox').length).toEqual(1);
      this.root.find('.lightbox .background').click();
      expect(this.root.find('div.lightbox').length).toEqual(0);
    });
  });

});
