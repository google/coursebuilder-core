// Variables required in global scope
var cbShowMsg, cbShowMsgAutoHide;

describe('The skill tagging library', function() {

  beforeEach(function() {
    showMsg = jasmine.createSpy('showMsg');
    showMsgAutoHide = jasmine.createSpy('showMsgAutoHide');

    jasmine.getFixtures().fixturesPath = 'base/';
    loadFixtures('tests/unit/javascript_tests/modules_skill_map/' +
        'lesson_editor/fixture.html');
  });

  afterEach(function() {
    delete SKILL_API_VERSION;
    delete parseAjaxResponse;
    delete showMsg;
    delete showMsgAutoHide;

    // Tidy up any leftover lightboxes
    $(document.body).empty();
  });

  describe('SkillsList', function() {
    var SKILL_LIST_REST_RESPONSE = {
      status: 200,
      xsrf_token: 'valid_xsrf_token',
      payload: JSON.stringify({
        skill_list: [
          {
            id: 's111',
            name: 'rock climing',
            description: 'can climb rocks',
            prerequisite_ids: []
          },
          {
            id: 's222',
            name: 'ice skating',
            description: 'can skate on ice',
            prerequisite_ids: []
          }
        ]
      })
    };

    beforeEach(function() {
      this.skillList = new SkillList();
      this.callback = jasmine.createSpy('callback');
      spyOn($, 'ajax');
    });

    describe('loading the skill map', function() {
      it('GETs from the skill_list REST service', function() {
        this.skillList.load(this.callback);
        expect($.ajax).toHaveBeenCalled();
        var arg = $.ajax.calls[0].args[0];
        expect(arg.type).toEqual('GET');
        expect(arg.url).toEqual('rest/modules/skill_map/skill');
        expect(arg.dataType).toEqual('text');
      });
      it('displays an error if the status is not 200', function() {
        this.skillList.load(this.callback);
        $.ajax.calls[0].args[0].success(JSON.stringify({status: 400}));
        expect(showMsg).toHaveBeenCalled();
        expect(showMsg.calls[0].args[0]).toMatch(/^Unable to load skill map./);
      });
      it('loads a valid skill map', function() {
        this.skillList.load(this.callback);
        $.ajax.calls[0].args[0].success(JSON.stringify(SKILL_LIST_REST_RESPONSE));
        expect(this.callback).toHaveBeenCalled();
        expect(this.skillList.getSkillById('s111')).toEqual({
          id: 's111', name: 'rock climing', description: 'can climb rocks',
          prerequisite_ids: []});
        expect(this.skillList.getSkillById('s222')).toEqual({
          id: 's222', name: 'ice skating', description: 'can skate on ice',
          prerequisite_ids: []});
      });
    });

    describe('adding to the skill map', function() {
      it('PUTs to the skill REST service', function() {
        this.skillList.createOrUpdateSkill(
            this.callback, 'ice skating', 'can skate');
        expect($.ajax).toHaveBeenCalled();
        var arg = $.ajax.calls[0].args[0];
        expect(arg.type).toEqual('PUT');
        expect(arg.url).toEqual('rest/modules/skill_map/skill');
        var request = JSON.parse(arg.data.request);
        var payload = JSON.parse(request.payload);
        expect(payload).toEqual({
          version: '1',
          name: 'ice skating',
          description: 'can skate',
          prerequisites: [],
          locations: []
        });
      });
    });
    it('displays an error if the status is not 200', function() {
      this.skillList.createOrUpdateSkill(
          this.callback, 'ice skating', 'can skate');
      $.ajax.calls[0].args[0].success(JSON.stringify(
          {status: 400, message: 'Server error'}));
      expect(showMsg).toHaveBeenCalled();
      expect(showMsg.calls[0].args[0]).toEqual('Server error');
    });
    it('inserts the skill with key, and issues callback after save', function() {
      this.skillList.createOrUpdateSkill(
          this.callback, 'ice skating', 'can skate');
      var payload = {
        status: 200,
        message: 'OK',
        payload: JSON.stringify({
          key: 'skill001',
          skill: {
            id: 'skill001',
            name: 'ice skating',
            description: 'can skate',
            prerequisite_ids: []
          },
          skill_list: [],
          diagnosis: []
        })
      };
      $.ajax.calls[0].args[0].success(JSON.stringify(payload));
      expect(this.callback).toHaveBeenCalled();
      expect(this.callback.calls[0].args[0]).toEqual({
        id: 'skill001',
        name: 'ice skating',
        description: 'can skate',
        prerequisite_ids: []
      });
      expect(this.callback.calls[0].args[1]).toEqual('OK');
    });
  });

  describe('Lighbox', function() {
    beforeEach(function() {
      this.root = $('#root');
      this.lightbox = new Lightbox();
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
  });

  describe('ItemSelector', function() {

    beforeEach(function() {
      this.root = $('#root');
      this.callback = jasmine.createSpy('callback');
      this.selector = new ItemSelector(this.callback);
      this.root.append(this.selector.element());
      this.selector.add('s1', 'ice skating');
      this.selector.add('s2', 'rock climbing');
    });

    it('is closed initially', function() {
      expect($('div.selector')).toBeHidden();
    });

    it('opens the selector when the add button is clicked', function() {
      $('button.add').click();
      expect($('div.selector')).toBeVisible();
    });

    it('lists the items in the selector', function() {
      expect($('ol.item-list li span').length).toBe(2);
      expect($('ol.item-list li span').eq(0).text()).toBe('ice skating');
      expect($('ol.item-list li span').eq(1).text()).toBe('rock climbing');
    });

    it('filters the list when text is entered', function() {
      $('button.add').click();
      $('input.search').val('ice').keyup();
      expect($('ol.item-list li:visible').length).toBe(1);
      expect($('ol.item-list li:visible').text()).toBe('ice skating');
    });

    it('disables the OK button when no items are selected', function() {
      $('button.add').click();
      expect($('button.select')).toBeDisabled();
    });

    it('enables the OK button when items are selected', function() {
      $('button.add').click();
      $('input[type=checkbox]:first').click();
      expect($('button.select')).not.toBeDisabled();
    });

    it('returns the selected item ids to the callback', function() {
      $('button.add').click();
      $('input[type=checkbox]:first').click();
      $('button.select').click();
      expect(this.callback).toHaveBeenCalled();
      expect(this.callback.calls[0].args[0].length).toBe(1);
      expect(this.callback.calls[0].args[0][0]).toBe('s1');
    });

    it('is disabled when empty', function() {
      this.root = $('#root').empty();
      this.callback = jasmine.createSpy('callback');
      this.selector = new ItemSelector(this.callback);
      this.root.append(this.selector.element());

      expect($('button.add').prop('disabled')).toBe(true);
      this.selector.add('s1', 'ice skating');
      expect($('button.add').prop('disabled')).toBe(false);
    });
  });
});
