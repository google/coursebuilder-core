window.GcbStudentSkillsUiModule = (function($) {
  var module = {}

  // TODO(tujohnson): If no scale argument is given, scale initial drawing
  //                  so that all nodes are visible
  // TODO(tujohnson): Fix line breaking for labels
  // TODO(tujohnson): Add actual links to side panel
  // TODO(tujohnson): Add recentering button
  // TODO(tujohnson): Add node dragging
  // TODO(tujohnson): Add node fading on mouseover
  // TODO(tujohnson): Change node opacity so that edges can be seen behind them
  // TODO(tujohnson): Show path(s) to selected node
  // TODO(tujohnson): Add separate colors for mouseover vs. click
  module.setupGraph = function(data, argX, argY, argScale) {
    var graphContainer, svg, inner, panel, zoom;
    var graph, nodes;
    var defaultColors = {};
    var selectedNode, selectionColor = '#b94431';
    var graphContainerWidth, graphContainerHeight, panelWidth;

    // helpers
    function formatClassName(str) {
      return str.replace(/[^_0-9a-zA-Z\-]/g, '-');
    }

    function findElementByNodeLabel(nodeLabel) {
      // Select all nodes with the given id
      var selector = '.node.' + formatClassName(nodeLabel);
      return $(selector);
    }

    function setColor(node, color) {
      var rect = $(node).find('rect')[0];
      rect.style.fill = color;
    }

    function getLabelForNode(node) {
      return node.textContent.replace('\n', ' ');
    }

    function runRender() {
      graph = new dagreD3.graphlib.Graph().setGraph({});
      graphContainer = d3.select('.graph-container')
          .on('dblclick.zoom', null);
      svg = graphContainer.append('svg:svg')
          .attr('class', 'graph')
          .on('click', onBackgroundClicked)
          .on('dblclick.zoom', null);
      panel = d3.select('.panel');
      inner = svg.append('g');

      // Set up zoom support
      zoom = d3.behavior.zoom();
      zoom.on('zoom', onZoomChanged);
      graphContainer.call(zoom);
      d3.select(window).on("resize", resize);

      // Controllers
      $('.control-zoom a').on('click', onControlZoomClicked);

      // Parse data to create graph
      for (var index = 0; index < data.nodes.length; index++) {
        var label = data.nodes[index].id;
        var color = data.nodes[index].default_color;
        defaultColors[label] = color;
        var labelWithBreaks = label.replace(' ', '\n');
        graph.setNode(label, { shape: "rect",
                               'class': formatClassName(labelWithBreaks),
                               'style': 'fill: ' + color});
      }

      for (var index = 0; index < data.links.length; index++) {
        var source = data.nodes[data.links[index].source];
        var target = data.nodes[data.links[index].target];
        graph.setEdge(source.id, target.id, { shape: "normal" });
      }

      var render = new dagreD3.render();
      render(inner, graph);

      addNodeInteractivity();
    }

    function resize() {
      // Leave space of 100px for margins
      panelWidth = (window.innerWidth - 100) * 0.2;
      graphContainerWidth = (window.innerWidth - 100) * 0.8;
      graphContainerHeight = window.innerHeight - 200;
      $('div.graph-container').height(graphContainerHeight)
          .width(graphContainerWidth);

      $('div.panel').width(panelWidth);
    }

    function shiftGraphAndZoom(x, y, scale) {
      // Center and scale the graph
      // If the graph does not fit in the window, we scale it down so that it's
      // visible
      if (scale < 0) {
        scale = Math.min(1, graphContainerWidth / graph.graph().width,
            graphContainerHeight / graph.graph().height);
      }
      var translateWidth = (graphContainerWidth -
          graph.graph().width * scale) / 2 + x;
      var translateHeight = (graphContainerHeight -
          graph.graph().height * scale) / 2 + y;

      translateAndScale([translateWidth, translateHeight], scale);
    }

    function addNodeInteractivity() {
      // nodes
      nodes = $('.node');
      nodes.on('mouseover', _.bind(onNodeMouseOver, this))
        .on('mouseout', _.bind(onNodeMouseOut, this))
        .on('click', _.bind(onNodeClicked, this));
    }

    function onNodeMouseOver(d) {
      // highlight node
      var node = d.currentTarget;
      setColor(node, selectionColor);
    }

    function onNodeMouseOut(d) {
      // highlight node
      var node = d.currentTarget;
      if(node != selectedNode)
      {
        var label = getLabelForNode(node);
        setColor(node, defaultColors[label]);
      }
    }

    function onControlZoomClicked(e) {
      var elmTarget = $(this);
      var scaleProcentile = 0.20;

      // scale
      var currentScale = zoom.scale();
      var newScale;
      if (elmTarget.hasClass('control-zoom-in')) {
        newScale = currentScale * (1 + scaleProcentile);
      } else {
        newScale = currentScale * (1 - scaleProcentile);
      }
      newScale = Math.max(newScale, 0);

      // translate
      var currTranslate = zoom.translate();

      // We compute how much the width of the graph changes, and shift it so
      // that we remain centered on the same location.
      var scaleDiff = newScale - currentScale;
      var translateShift = [scaleDiff * graph.graph().width / 2,
                            scaleDiff * graph.graph().height / 2];
      var newTranslate = [currTranslate[0] - translateShift[0],
                          currTranslate[1] - translateShift[1]];
      translateAndScale(newTranslate, newScale);

      // suppress navigating to CB home
      return false;
    }

    function onZoomChanged() {
      translateAndScale(d3.event.translate, d3.event.scale);
    }

    function translateAndScale(translate, scale) {
      zoom.translate(translate).scale(scale);
      inner.attr('transform',
          'translate(' +
          zoom.translate() +
          ')' +
          ' scale(' +
          zoom.scale() +
          ')')
    }

    function onNodeClicked(d) {
      // Prevent the click from propagating to the background
      d.stopPropagation();
      var node = d.currentTarget;
      processNodeClick(node);
    }

    function processNodeClick(node) {
      // This is separated into its own function for ease of testing.
      // If we click on the currently selected node, it is deselected.
      // Otherwise, we replace the currently selected node (if there is one)
      // with the one that has just been clicked on.
      if(node != selectedNode) {
        if(selectedNode != null)
        {
          var label = getLabelForNode(selectedNode);
          setColor(selectedNode, defaultColors[label]);
        }
        setColor(node, selectionColor);
        selectedNode = node;
      } else {
        var label = getLabelForNode(node);
        setColor(node, defaultColors[label]);
        selectedNode = null;
      }

      redrawPanel();
    }

    function onBackgroundClicked() {
      // If there is a node selected, we deselect it.
      if(selectedNode)
      {
        var label = getLabelForNode(selectedNode);
        setColor(selectedNode, defaultColors[label]);
        selectedNode = null;
      }
      redrawPanel();
    }

    function redrawPanel() {
      // Sets the info displayed in the side panel.
      // TODO(tujohnson): Put actual links in this panel.
      if (selectedNode == null) {
        d3.select('.panel-links').html('');
      } else {
        d3.select('.panel-links').html('Selected node: ' +
            getLabelForNode(selectedNode));
      }
    }

    runRender();
    resize();

    // Shift according to the given parameters
    shiftGraphAndZoom(argX, argY, argScale);
  };

  return module;
})(jQuery);
