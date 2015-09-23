/**
 * Displays histograms for skills competencies analytics using the data
 * from GenerateSkillCompetencyHistograms map-reduce job
 */

/**
 * Skill competencies charts builder.
 *
 * @class
 */
function ChartTable(container, rowSize, data) {
  this._container = container;
  this._rowSize = rowSize;
  this._data = data;
  this._xf = crossfilter(this._data);
  this._units = this._getUnitTitles();
  this._unitIdDim = this._xf.dimension(function(d) {
    return Number(d.unit_id);
  });
  // filters skills sorted by name
  this._skillNameDim = this._xf.dimension(function(d) {
    return d.skill_name;
  });
  // the first unit in the course is selected by default
  this._unitIdDim.filterExact(this._units[0].key[1]);
  this._title_labels = {
    0: 'Low Competency', 1: 'Med. Competency', 2: 'High Competency'
  };
}

ChartTable.prototype = {

  _getUnitTitles: function() {
    // returns [{key: [unit_index, unit_id, unit_title], value: numberOfSkills}]
    var unitTitleDim = this._xf.dimension(function(d) {
      return [Number(d.unit_index), Number(d.unit_id), d.unit_title];
    });
    var units = unitTitleDim.group().reduceCount().top(Infinity);
    unitTitleDim.dispose();
    return units;
  },

  _buildChart: function(skill) {
    // build a skill chart using a local chart cross filter
    var that = this;
    var cf = crossfilter(skill.histogram);
    var competencyDim = cf.dimension(function(d) {
      return Number(d.c);
    });
    var competencyGroup = competencyDim.group().reduceSum(
      function(d) {
        return d.v;
      }
    );
    var max = Math.max.apply(
      null, $.map(
        competencyDim.top(Infinity), function(d) { return d.v; }));
    var chart = dc.barChart('#skill_' + skill.skill_id);
    chart.width(120)
      .height(100)
      .margins({top: 10, right: 10, bottom: 10, left: 25})
      .dimension(competencyDim)
      .group(competencyGroup)
      .brushOn(false)
      .colors(['#74a9cf','#2b8cbe', '#045a8d'])
      .colorAccessor(function(d, i) {
        return i;
      })
      .renderLabel(false)
      .title(function(d) {
        var l = that._title_labels[d.data.key];
        return l + ': ' + d.data.value + ' students';
      })
      .renderTitle(true)
      .gap(1)
      .round(dc.round.floor)
      .elasticY(true)
      .renderHorizontalGridLines(true)
      .x(d3.scale.linear().domain([0, 3]))
      .xAxis()
      .ticks(0);
    chart.yAxis().ticks(3);
    return chart;
  },

  _buildTd: function(skill) {
    var td = $('<td class="hist"></td>');
    var name = $('<div class="name"></div>');
    name.text(skill.skill_name);
    var description = $('<div class="description"></div>');
    description.text(skill.skill_description);
    var chartDiv = $(
      '<div class="histogram">' +
      '</div>');
    chartDiv.attr('id', 'skill_' + skill.skill_id);
    td.append(name);
    td.append(description);
    td.append(chartDiv);
    return td;
  },

  _buildEmptyTd: function() {
    return $('<td></td>');
  },

  _buildRow: function(skills) {
    var tr = $('<tr class="row"></tr>');
    for (var i = 0; i < skills.length; i++) {
      var td = this._buildTd(skills[i]);
      tr.append(td);
    }
    if (skills.length < this._rowSize) {
      for (var j = 0; j < this._rowSize - skills.length; j++) {
        tr.append(this._buildEmptyTd());
      }
    }
    return tr;
  },

  _buildHeader: function() {
    var thead = $('<thead></thead>');
    var tr = $('<tr></tr>');
    for (var i = 0; i < this._rowSize; i++) {
      tr.append('<th></th>');
    }
    thead.append(tr);
    return thead;
  },

  _buildBody: function() {
    var tbody = $('<tbody></tbody>');
    // sort in desc alphabetical order
    var skills = this._skillNameDim.bottom(Infinity);
    for (var i = 0; i < skills.length; i += this._rowSize) {
      var row = this._buildRow(skills.slice(i, i + this._rowSize));
      tbody.append(row);
    }
    return tbody;
  },

  buildTable: function() {
    this._container.empty();
    this._table = $(
      '<table class="skill-competency-table"></table>');
    this._table.append(this._buildBody());
    this._table.appendTo(this._container);
    this._drawCharts();
  },

  /**
   * Draws the histograms for the skills in a unit.
   */
  _drawCharts: function() {
    var skills = this._skillNameDim.bottom(Infinity);
    for (var i = 0; i < skills.length; i++) {
      this._buildChart(skills[i]);
    }
    dc.renderAll();
  },

  _attachUnitHandler: function() {
    var that = this;
    var unitsDiv = $('.units');
    unitsDiv.find('.unit-title').on('click', function (e) {
      var unitId = $(this).data('unit-id');
      that._unitIdDim.filterExact(unitId);
      that.buildTable(that._container);
    });
  },

  buildUnitSelector: function(unitsDiv) {
    for (var i = 0; i < this._units.length; i++) {
      var uid = this._units[i].key[1],
          unitTitle = this._units[i].key[2],
          numSkills = this._units[i].value;

      // build unit selector radiobutton
      var elementId = 'unit_' + uid;
      var radiobutton = $(
        '<input type="radio" name="unit" class="unit-title">');
      radiobutton.prop('id', elementId);
      radiobutton.prop('value', uid);
      radiobutton.data('unit-id', uid);

      // build unit selector label
      var label = $('<label class="unit-label"></label>');
      var spanTitle = $('<span></span>').text(unitTitle);
      label.append(radiobutton);
      label.append(spanTitle).append(' ');
      label.append(
        $('<span class="skill-count"></span>').text('(' + numSkills + ')')
      );
      unitsDiv.append(label);

      // set default unit selection
      if (i == 0) {
        radiobutton.prop('checked', true);
        radiobutton.addClass('selected');
      }

      unitsDiv.append($('<br>'))
    }
    this._attachUnitHandler();
  }
};


/**
 * Export the classes which will be used in global scope.
 */
window.ChartTable = ChartTable;

