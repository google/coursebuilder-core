window.GcbStudentSkillsUiModule = (function($) {
  var module = {}

  // TODO(tujohnson): Add line breaking for labels
  // TODO(tujohnson): Change node opacity so that edges can be seen behind them
  module.setupGraph = function(data, argX, argY, argScale) {
    var graphContainer, svg, inner, panel, zoom;
    var graph, nodes;
    var defaultColors = {};
    var skills = {}, edges = {}, reverseEdges = {};
    // Green for completed skills, yellow for in progress, gray if not started
    var progress = {};
    var progressColors = {'completed': '#00cc00', 'in_progress': '#cccc00',
      'no_progress': '#ccc'};
    var selectedNode;
    var selectionColor = '#b94431';
    var graphContainerWidth, graphContainerHeight, panelWidth;

    function formatClassName(str) {
      // Special characters are converted to hyphens. Underscores are also
      // converted, so that we can use them as separators for edge classes.
      // TODO(tujohnson): Karma test to check that this happens correctly?
      return str.replace(/[^0-9a-zA-Z\-]/g, '-');
    }

    function getEdgeClass(sourceId, targetId) {
      // The source and target ID's will have any underscores converted to
      // hyphens, so this will be unique.
      return formatClassName(sourceId) + '_' + formatClassName(targetId);
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
      return node.textContent.replace('\n', '-');
    }

    function runRender() {
      graph = new dagreD3.graphlib.Graph().setGraph({});
      graphContainer = d3.select('.graph-container')
          .on('dblclick.zoom', null);
      svg = graphContainer.append('svg:svg')
          .attr('class', 'graph')
          .on('click', onBackgroundClicked)
          .on('dblclick.zoom', null)
          .on('dragstart', onBackgroundDragged);
      panel = d3.select('.panel');
      inner = svg.append('g');

      // Set up zoom support
      zoom = d3.behavior.zoom();
      zoom.on('zoom', onZoomChanged);

      graphContainer.call(zoom)
          .on('dblclick.zoom', null);
      d3.select(window).on("resize", resize);

      // Controllers
      $('.control-zoom a').on('click', onControlZoomClicked);

      // Add nodes to graph
      for (var index = 0; index < data.nodes.length; index++) {
        var label = data.nodes[index].id;
        progress[label] = data.nodes[index].progress;
        var color = progressColors[progress[label]];
        skills[label] = data.nodes[index]['skill'];

        // Initialize empty lists of edges
        edges[label] = [];
        reverseEdges[label] = [];
        graph.setNode(label, { shape: 'rect',
                               class: formatClassName(label),
                               style: 'fill: ' + color});
      }

      // Add edges to graph
      for (var index = 0; index < data.edges.length; index++) {
        var source = data.nodes[data.edges[index].source];
        var target = data.nodes[data.edges[index].target];
        edges[source.id].push(target.id);
        reverseEdges[target.id].push(source.id);
        graph.setEdge(source.id, target.id, { shape: 'normal',
                      'class': getEdgeClass(source.id, target.id)});
      }

      var render = new dagreD3.render();
      render(inner, graph);

      // Add highlight to nodes for current lesson
      for (var index = 0; index < data.nodes.length; index++) {
        node = data.nodes[index]
        if(node['highlight']) {
          $('.graph .node.' + formatClassName(node.id)).addClass('highlight');
        }
      }

      addNodeInteractivity();
    }

    function resize() {
      // Dimensions for .skill-card are based on the sizes defined in
      // modules/skill_map/_static/css/common.css. If you change it here, please
      // update the CSS there as well.
      var innerWidth = $('div.container').width();
      panelWidth = 200;
      panelHeight = 250;

      // Add 50px for margins
      graphContainerWidth = innerWidth - (panelWidth + 50);
      graphContainerHeight = Math.max(graph.graph().height + 50, panelHeight);
      $('div.graph-container').height(graphContainerHeight)
          .width(graphContainerWidth);
      $('div.panel').width(panelWidth);
    }

    function shiftGraphAndZoom(x, y, scale) {
      // If auto-scaling is on, we scale the graph down so that it takes up 95%
      // of the constraining dimension.
      if (scale < 0) {
        var fill = 0.95;
        scale = Math.min(1, fill * graphContainerWidth / graph.graph().width,
            fill * graphContainerHeight / graph.graph().height);
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
      nodes.on('mouseout', _.bind(onNodeMouseOut, this))
        .on('click', _.bind(onNodeClicked, this));
    }

    function onNodeMouseOut(d) {
      // highlight node
      var node = d.currentTarget;
      if(node != selectedNode) {
        var label = getLabelForNode(node);
        setColor(node, progressColors[progress[label]]);
      } else {
        setColor(node, selectionColor);
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
      // If we click on the currently selected node, it is deselected.
      // Otherwise, we replace the currently selected node (if there is one)
      // with the one that has just been clicked on.
      if(node != selectedNode) {
        if(selectedNode != null)
        {
          var label = getLabelForNode(selectedNode);
          setColor(selectedNode, progressColors[progress[label]]);
          addHighlights(label, false);
        }
        var newLabel = getLabelForNode(node);
        setColor(node, selectionColor);
        addHighlights(newLabel, true);
        selectedNode = node;
      } else {
        var label = getLabelForNode(node);
        setColor(node, progressColors[progress[label]]);
        addHighlights(label, false);
        selectedNode = null;
      }

      drawSkillCardInPanel();
    }

    function addHighlights(label, toHighlight) {
      setPathClass(label, true, toHighlight);
      setPathClass(label, false, toHighlight);
    }

    function setPathClass(nodeLabel, searchDown, toHighlight) {
      // Resets the class of either the ancestor or descendant edges for the
      // given node, based on the value of searchDown. Highlighting is turned
      // on if toHighlight is true, and off if it is false.
      var edgeSet, highlightClass;
      if (searchDown) {
        edgeSet = edges;
        highlightClass = 'descendant';
      } else {
        edgeSet = reverseEdges;
        highlightClass = 'ancestor';
      }

      for(var index = 0; index < edgeSet[nodeLabel].length; index++) {
        if(searchDown) {
          var edgeClass = '.edgePath.' + getEdgeClass(nodeLabel,
              edgeSet[nodeLabel][index]);
        } else {
          var edgeClass = '.edgePath.' + getEdgeClass(edgeSet[nodeLabel][index],
              nodeLabel);
        }

        if (toHighlight) {
          $(edgeClass + ' path.path').addClass(highlightClass);
          $(edgeClass + ' marker').addClass(highlightClass);
        } else {
          $(edgeClass + ' path.path').removeClass(highlightClass);
          $(edgeClass + ' marker').removeClass(highlightClass);
        }

        // Recursive depth-first search
        setPathClass(edgeSet[nodeLabel][index], searchDown, toHighlight);
      }
    }

    function onBackgroundDragged(d) {
      // Prevent drag from firing a click event on the background and
      // deselecting nodes.
      d3.event.stopPropagation();
      d3.event.preventDefault();
    }

    function onBackgroundClicked() {
      // If there is a node selected, we deselect it.
      if (!d3.event.defaultPrevented && selectedNode)
      {
        var label = getLabelForNode(selectedNode);
        setColor(selectedNode, progressColors[progress[label]]);
        setPathClass(label, false, false);
        setPathClass(label, true, false);
        selectedNode = null;
        drawSkillCardInPanel();
      }
    }

    function drawSkillCardInPanel() {
      if (selectedNode == null) {
        $('.panel-links .skill-card .name').attr('class', 'name');
        $('.panel-links .skill-card .name').text('');
        $('.panel-links .skill-card .description .content').text('');
        $('.panel-links .skill-card .locations .lessons').html('');
        $('.panel-links .skill-card').hide();
      } else {
        label = getLabelForNode(selectedNode);
        skill = skills[label];
        $('.panel-links .skill-card .name').addClass(skill.score_level);
        $('.panel-links .skill-card .name').text(skill.name);
        $('.panel-links .skill-card .description .content').text(
            skill.description);

        // Clear all except default text
        defaultItem = $('.panel-links .skill-card .locations .lessons .empty');
        $('.panel-links .skill-card .locations .lessons')
            .html(defaultItem)
        if(skill.lessons.length > 0) {
          // If we have lessons to show, hide default text
          $('.panel-links .skill-card .locations .lessons .empty').hide();
          for(var index = 0; index < skill.lessons.length; index++) {
            var lesson = skill.lessons[index];
            var newLink = $('<a/>');
            newLink.attr('href', lesson.href)
                .text(lesson.label + ' ' + lesson.description);
            var newItem = $('<li/>');
            newItem.append(newLink);
            $('.panel-links .skill-card .locations .lessons').append(newItem);
          }
        } else {
          // Otherwise, show default text
          $('.panel-links .skill-card .locations .lessons .empty').show();
        }

        $('.panel-links .skill-card').show();
      }
    }

    runRender();
    resize();

    // Shift according to the given parameters
    shiftGraphAndZoom(argX, argY, argScale);
  };

  return module;
})(jQuery);
