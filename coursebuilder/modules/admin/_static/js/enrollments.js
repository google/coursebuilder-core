// Called back from framework with data.enrollments.{data, crossfilter}
function enrollments(data) {
  // All event types by date for select-the-date lower graph.
  var timeline = data.enrollments.crossfilter.dimension(function(row) {
    return new Date(row.timestamp_millis);
  });
  var totalGroup = timeline.group().reduceSum(function(row) {
    return row.add + row.drop;
  });
  var minDate = new Date(timeline.bottom(1)[0].timestamp_millis);
  var maxDate = new Date(timeline.top(1)[0].timestamp_millis);
  var midDate = new Date((minDate - 0) + (maxDate - minDate) / 2);

  // Set up a chart that's used to pick the date range to show in detail.
  // No Y-axis label, as chart is very short vertically.
  var chooseRangeChart = dc.barChart('#time-scale-chart');
  chooseRangeChart
    .width(900)
    .height(100)
    .dimension(timeline)
    .group(totalGroup)
    .x(d3.time.scale().domain([minDate, maxDate]))
    .xUnits(d3.time.days)
    .xAxisLabel('Time Range')
    .centerBar(true)
    .gap(1)
    .brushOn(true);
  chooseRangeChart.yAxis().tickValues([]);

  // Separate groupings for items that are adds/drops so
  // we can build a stacked line chart of these.
  var addItems = timeline.group().reduceSum(function(row) {
    // Add drop count to get stacked value back to 0 baseline.  Dc doesn't
    // seem to understand multiple non-stacked groups.  Sad.
    return row.add;
  })
  .order(function(row) {
    return row.timestamp_millis;
  });

  var dropItems = timeline.group().reduceSum(function(row) {
    return -row.drop;
  })
  .order(function(row) {
    return row.timestamp_millis;
  });

  // Pretty graph showing frequency of add/drop items.  No mouse
  // selection enabled so x,y hover shows actual data value.
  notificationChart = dc.compositeChart('#enrollments-chart');
  notificationChart
    .width(900)
    .height(200)
    .dimension(timeline)
    .rangeChart(chooseRangeChart)
    .x(d3.time.scale().domain([minDate, maxDate]))
    .renderHorizontalGridLines(true)
    .legend(dc.legend().x(750).y(10).itemHeight(13).gap(5))
    .brushOn(false)
    .zoomOutRestrict(true)
    .compose([
      dc.lineChart(notificationChart).group(addItems, 'Enrollments'),
      dc.lineChart(notificationChart).group(dropItems, 'Unenrollments')
        .colors(['#ff7f0e'])  // D3 gets legend colors right, but not for line.
    ]);

  // Arrange to have our Y-axis labelled with few enough tick marks that we
  // don't wind up having tick marks labeled for non-integer quantities of
  // enrollments.
  var counts = data.enrollments.crossfilter.dimension(function(row) {
    return row.add + row.drop;
  });

  var topCount = counts.top(1)[0]
  var maxTicks = topCount.add + topCount.drop
  var numTicks = Math.min(10, maxTicks);
  notificationChart.yAxis().ticks(numTicks);

  dc.renderAll();

  // Set the range chart to a nontrivial selection, so as to show the
  // selection and drag handles for maximum discoverability that that's
  // what that chart is for.
  chooseRangeChart.filter([midDate, maxDate]);
}
