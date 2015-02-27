describe('The student skill widget', function() {

  beforeEach(function() {
    var that = this;
    gcbCanPostEvents = true;
    gcbAudit = jasmine.createSpy('gcbAudit');
    now = function() { return that.currentTimeMs; };

    jasmine.getFixtures().fixturesPath = 'base/';
    loadFixtures('tests/unit/javascript_tests/modules_skill_map/' +
        'student_skill_widget/fixture.html');

    jasmine.Clock.useMock();
    $.fx.off = true;

    this.detailsPanel = $('div.skill-panel div.skill-details');
    this.button = $('div.skill-panel .open-control button');
    this.filterLi = $('div.skills-in-this-lesson li.skill:eq(3)');

    init();
  });

  it('opens/closes when the arrow is clicked', function() {
    expect(this.detailsPanel).toBeHidden();
    expect(this.button).toHaveClass('md-keyboard-arrow-down');

    this.button.click();
    jasmine.Clock.tick(500);

    expect(this.detailsPanel).not.toBeHidden();
    expect(this.button).toHaveClass('md-keyboard-arrow-up');

    this.button.click();
    jasmine.Clock.tick(500);

    expect(this.detailsPanel).toBeHidden();
    expect(this.button).toHaveClass('md-keyboard-arrow-down');
  });

  it('fires events when it is opened or closed', function() {
    // Click once to open
    this.button.click();
    jasmine.Clock.tick(500);
    expect(gcbAudit.calls[0].args).toEqual(
        [true, {type: 'open', isOpened: true}, 'skill-panel', true]);

    // Click again to close
    this.button.click();
    jasmine.Clock.tick(500);
    expect(gcbAudit.calls[1].args).toEqual(
        [true, {type: 'open', isOpened: false}, 'skill-panel', true]);
  });

  it('highlights dependencies when a skill is hovered', function() {
    function cardNames(selector) {
      return $(selector).map(function() {
        return $(this).text();
      }).get();
    }

    expect($('div.skill-panel .skill-card.highlighted').length).toBe(0);
    expect($('div.skill-panel .skill-card.shaded').length).toBe(0);

    this.filterLi.mouseover();

    expect(cardNames('.depends-on .skill-card.highlighted div.name')).toEqual(
      ['Search results', 'Query']
    );
    expect(cardNames('.depends-on .skill-card.shaded div.name').length).toBe(3);

    expect(cardNames('.leads-to .skill-card.highlighted div.name')).toEqual(
      ['Filter by similarity', 'Time range query', 'Filter by color']
    );
    expect(cardNames('.leads-to .skill-card.shaded div.name').length).toBe(5);
  });


  it('removes highlights when a skill is left', function() {
    expect($('div.skill-panel .skill-card.highlighted').length).toBe(0);
    expect($('div.skill-panel .skill-card.shaded').length).toBe(0);

    // After mouseover everything is either highlighted or shaded
    this.filterLi.mouseover();
    expect($('.skill-card.highlighted').length).toBe(5);
    expect($('.skill-card.shaded').length).toBe(8);

    // After mouseout nothing is highlighted or shaded
    this.filterLi.mouseout();
    expect($('div.skill-panel .skill-card.highlighted').length).toBe(0);
    expect($('div.skill-panel .skill-card.shaded').length).toBe(0);
  });

  it('fires an event when a skill is hovered for long', function() {
    var skillId = 6350779162034176;
    expect(this.filterLi).toHaveData('skillId', skillId);

    this.currentTimeMs = 0;
    expect(gcbAudit).not.toHaveBeenCalled();

    // A hover of less than 1000ms does not trigger event
    this.filterLi.mouseover();
    this.currentTimeMs += 900;
    this.filterLi.mouseout();
    expect(gcbAudit).not.toHaveBeenCalled();

    // Even if multiple hovers total over 1000ms, still not event
    this.filterLi.mouseover();
    this.currentTimeMs += 900;
    this.filterLi.mouseout();
    expect(gcbAudit).not.toHaveBeenCalled();

    // But if a single hover is over 1000ms, then event
    this.filterLi.mouseover();
    this.currentTimeMs += 1100;
    this.filterLi.mouseout();
    expect(gcbAudit).toHaveBeenCalled();

    expect(gcbAudit.calls[0].args).toEqual(
        [
          true,
          {type: 'skill-hover', skillId: skillId},
          'skill-panel',
          true
        ]);
  });

  it('displays skill description when a skill is hovered', function() {
    var filterBySimilarityLi = $('div.skills-in-this-lesson li.skill:eq(2)');
    expect(filterBySimilarityLi.text().trim()).toBe('Filter by similarity');

    expect($('.skill-panel-tooltip').length).toBe(0);

    filterBySimilarityLi.mouseover();
    expect($('.skill-panel-tooltip').length).toBe(1);
    expect($('.skill-panel-tooltip').text()).toEqual(
      'Filter by similarity: Filter images by similarity.');
  });

  it('displays skill info tooltip when a skill card is hovered', function() {
    var filterByColorCardDescription =
        $('.depends-on li.skill-card:eq(2) .description');
    expect(filterByColorCardDescription.text().trim()).toBe(
        'Filter images by color.');

    // Click to open the widget
    this.button.click();
    jasmine.Clock.tick(500);

    expect($('.skill-panel-tooltip').length).toBe(0);

    filterByColorCardDescription.mouseover();
    expect($('.skill-panel-tooltip').length).toBe(1);
    expect($('.skill-panel-tooltip').text()).toEqual(
      'Filter by color: Filter images by color.');
  });
});
