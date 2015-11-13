describe('The student skill widget', function() {

  beforeEach(function() {
    var that = this;
    gcbCanRecordStudentEvents = true;
    gcbAudit = jasmine.createSpy('gcbAudit');
    now = function() { return that.currentTimeMs; };

    jasmine.getFixtures().fixturesPath = 'base/';
    loadFixtures(
        'modules/skill_map/javascript_tests/student_skill_widget/fixture.html');

    jasmine.clock().install();
    $.fx.off = true;

    this.detailsPanel = $('div.skill-panel div.skill-details');
    this.button = $('div.skill-panel .open-control button');
    this.filterLi = $('div.skills-in-this-lesson li.skill:eq(3)');

    init();
  });

  afterEach(function() {
    jasmine.clock().uninstall();
    $(document.body).empty();
  });

  it('opens/closes when the arrow is clicked', function() {
    expect(this.detailsPanel).toBeHidden();
    expect(this.button).toHaveClass('md-keyboard-arrow-down');

    this.button.click();
    jasmine.clock().tick(500);

    expect(this.detailsPanel).not.toBeHidden();
    expect(this.button).toHaveClass('md-keyboard-arrow-up');

    this.button.click();
    jasmine.clock().tick(500);

    expect(this.detailsPanel).toBeHidden();
    expect(this.button).toHaveClass('md-keyboard-arrow-down');
  });

  it('fires events when it is opened or closed', function() {
    // Click once to open
    this.button.click();
    jasmine.clock().tick(500);
    expect(gcbAudit.calls.argsFor(0)).toEqual(
        [true, {type: 'open', isOpened: true}, 'skill-panel', true]);

    // Click again to close
    this.button.click();
    jasmine.clock().tick(500);
    expect(gcbAudit.calls.argsFor(1)).toEqual(
        [true, {type: 'open', isOpened: false}, 'skill-panel', true]);
  });

  it('highlights dependencies when open and a skill is clicked', function() {
    function cardNames(selector) {
      return $(selector).map(function() {
        return $(this).text();
      }).get();
    }

    // Click once to open
    this.button.click();
    jasmine.clock().tick(500);

    expect($('div.skill-panel .skill-card.highlighted').length).toBe(0);
    expect($('div.skill-panel .skill-card.shaded').length).toBe(0);

    this.filterLi.click();

    expect(cardNames('.depends-on .skill-card.highlighted div.name')).toEqual(
      ['Search results', 'Query']
    );
    expect(cardNames('.depends-on .skill-card.shaded div.name').length).toBe(3);

    expect(cardNames('.leads-to .skill-card.highlighted div.name')).toEqual(
      ['Filter by similarity', 'Time range query', 'Filter by color']
    );
    expect(cardNames('.leads-to .skill-card.shaded div.name').length).toBe(5);
  });

  it('does nothing when closed and a skill is clicked', function() {
    this.filterLi.click();

    expect($('div.skill-panel .skill-card.highlighted').length).toBe(0);
    expect($('div.skill-panel .skill-card.shaded').length).toBe(0);
  });


  it('removes highlights when something else is clicked', function() {
    // Click once to open
    this.button.click();
    jasmine.clock().tick(500);

    expect($('div.skill-panel .skill-card.highlighted').length).toBe(0);
    expect($('div.skill-panel .skill-card.shaded').length).toBe(0);

    // After click everything is either highlighted or shaded
    this.filterLi.click();
    expect($('.skill-card.highlighted').length).toBe(5);
    expect($('.skill-card.shaded').length).toBe(8);

    // After mouseout nothing is highlighted or shaded
    $('div.lesson-title').click();
    expect($('div.skill-panel .skill-card.highlighted').length).toBe(0);
    expect($('div.skill-panel .skill-card.shaded').length).toBe(0);
  });

  it('fires an event when a skill is clicked', function() {
    // Expect nothing happens if the widget is closed
    expect(gcbAudit.calls.count()).toBe(0);
    this.filterLi.click();
    expect(gcbAudit.calls.count()).toBe(0);

    // Click once to open
    this.button.click();
    jasmine.clock().tick(500);

    var skillId = 6350779162034176;
    expect(this.filterLi).toHaveData('skillId', skillId);

    // Expect one event from opening the widget
    expect(gcbAudit.calls.count()).toBe(1);

    this.filterLi.click();
    // Now expect a second event
    expect(gcbAudit.calls.count()).toBe(2);
    expect(gcbAudit.calls.argsFor(1)).toEqual(
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
    jasmine.clock().tick(500);

    expect($('.skill-panel-tooltip').length).toBe(0);

    filterByColorCardDescription.mouseover();
    expect($('.skill-panel-tooltip').length).toBe(1);
    expect($('.skill-panel-tooltip').text()).toEqual(
      'Filter by color: Filter images by color.');
  });
});
