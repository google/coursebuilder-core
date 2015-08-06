(function(jQuery, pageState) {

  var $ = jQuery;

  var ENV = JSON.parse('{{ env | js_string }}');
  var IN_SESSION = ENV['IN_SESSION'];
  var ORIGIN = ENV['ORIGIN'];
  var RESOURCE_URI_PREFIX_BOUNDARY = ENV['RESOURCE_URI_PREFIX_BOUNDARY'];
  var SIGN_IN_URL = ENV['SIGN_IN_URL'];

  var EMBED_TAG_NAME = 'cb-embed';
  var ERROR_CLASS = EMBED_TAG_NAME + '-error';
  var IFRAME_CLASS = EMBED_TAG_NAME + '-frame';
  var SIGN_IN_BUTTON_CLASS = EMBED_TAG_NAME + '-sign-in-button';
  var SIGN_IN_CONTAINER_CLASS = EMBED_TAG_NAME + '-sign-in-container';
  var SIGN_IN_CONTENT_CLASS = EMBED_TAG_NAME + '-sign-in-content';

  var MATERIAL_ICONS_CLASS = EMBED_TAG_NAME + '-material-icon';
  var SIGN_IN_ICON_CLASS = EMBED_TAG_NAME + '-icon';

  function debounce(fn, timeoutMillis) {
    var timeoutId;
    var timeoutMillis = timeoutMillis || 125;  // Perception ~= 150ms.

    return function() {
      var that = this;
      var args = arguments;

      clearTimeout(timeoutId);
      timeoutId = setTimeout(function() {
        fn.apply(that, Array.prototype.slice.call(args));
      }, timeoutMillis);
    }
  }

  function Page(state) {
    this._state = state;
    this._widgets = [];
  }
  Page.prototype = {
    render: function() {
      this._bindWidgets();

      if (!this._state.isReady()) {
        this._addError('Required resource not loaded.');
      }

      this._validateWidgets(this._getAllowedCbEmbedSrcPrefix());
      this._registerListeners();

      if (IN_SESSION) {
        this._renderAuthenticated();
      } else {
        this._renderUnauthenticated();
      }
    },
    _addError: function(error) {
      $.each(this._widgets, function(unused, widget) {
        widget.addError(error);
      });
    },
    _bindWidgets: function() {
      $(EMBED_TAG_NAME).each(function(unused, embedElement) {
        this._widgets.push(new Widget($(embedElement)));
      }.bind(this));
    },
    _getAllowedCbEmbedSrcPrefix: function() {
      var embeds = $(EMBED_TAG_NAME);
      if (embeds.length === 0) {
        return '';
      }

      var firstSrc = $(embeds.get(0)).attr('src');
      if (!firstSrc) {
        return '';
      }

      if (firstSrc.indexOf(RESOURCE_URI_PREFIX_BOUNDARY) === -1) {
        return firstSrc;  // Return src verbatim if malformed for error message.
      }

      return firstSrc.substring(
        0, firstSrc.indexOf(RESOURCE_URI_PREFIX_BOUNDARY));
    },
    _registerListeners: function() {
      $(window).on('message', function(event) {
        if (!this._valid(event)) {
          return;
        }

        var data = event.originalEvent.data;
        var sourceWindow = event.originalEvent.source;
        switch(data.action) {
          case 'login':
            this._renderAuthenticated();
            break;
          case 'resize':
            this._resize(data.height, data.width, sourceWindow);
            break;
        }
      }.bind(this));
      $(window).on('resize', this._removeSize);
    },
    _removeSize: debounce(function() {
      // Clears size information so later _resize ticks will set correct values.
      // On Chrome/FF/perhaps some other browsers, resize fires events
      // continuously. This performs poorly, so we throttle it.
      $('.' + IFRAME_CLASS).each(function(unused, iframe) {
        $(iframe).css('height', '').css('width', '');
        iframe.contentWindow.postMessage({action: 'resize'}, '*');
      });
    }),
    _renderAuthenticated: function() {
      $.each(this._widgets, function(unused, widget) {
        if (widget.hasErrors()) {
          widget.showErrors();
          return;
        }

        widget.showAuthenticated();
      });
    },
    _renderUnauthenticated: function() {
      $.each(this._widgets, function(unused, widget) {
        if (widget.hasErrors()) {
          widget.showErrors();
          return;
        }

        widget.showUnauthenticated();
      });
    },
    _resize: function(height, width, sourceWindow) {
      $('.' + IFRAME_CLASS).each(function(unused, iframe) {
        if (iframe.contentWindow == sourceWindow) {
          $(iframe).height(height).width(width);
          return false;
        }
      });
    },
    _valid: function(event) {
      return (event.originalEvent.origin === ORIGIN);
    },
    _validateWidgets: function(allowedCbEmbedSrcPrefix) {
      $.each(this._widgets, function(unused, widget) {
        widget.validate(allowedCbEmbedSrcPrefix);
      });
    }
  }

  function Widget(parentElement) {
    this._errors = [];
    this._parentElement = parentElement;
    this._src = this._getParentSrc();
  }
  Widget.prototype = {
    addError: function(error) {
      this._errors.push(error);
    },
    hasErrors: function() {
      return this._errors.length > 0;
    },
    showAuthenticated: function() {
      this._parentElement.empty().append(
        $('<iframe/>')
          .attr('class', IFRAME_CLASS)
          .attr('scrolling', 'no')
          .attr('src', this._src)
      );
    },
    showErrors: function() {
      var heading = $('<h1>').text('Embed misconfigured; errors:');
      var list = $('<ul>').append($.map(this._errors, function(error) {
        return $('<li>').text(error);
      }));
      var div = $('<div>')
        .attr('class', ERROR_CLASS)
        .append(heading)
        .append(list);

      this._parentElement.empty().append(div);
    },
    showUnauthenticated: function() {
      var container = $(
        '<div>' +
        '  <button>' +
        '    <i>play_arrow</i>' +
        '    <span>Start</span>' +
        '  </button>' +
        '</div>'
      );
      container.addClass(SIGN_IN_CONTAINER_CLASS);
      container.click(function() {
        window.open(SIGN_IN_URL);
      });
      container.find('button').addClass(SIGN_IN_BUTTON_CLASS);
      container.find('i')
        .addClass(MATERIAL_ICONS_CLASS + ' ' + SIGN_IN_ICON_CLASS);
      container.find('span').addClass(SIGN_IN_CONTENT_CLASS);

      this._parentElement.empty().append(container);
    },
    validate: function(allowedCbEmbedSrcPrefix) {
      if (!this._srcMatchesOrigin()) {
        this.addError(
          'Embed src "' + this._src + '" does not match origin "' + ORIGIN +
          '"');
      }

      if (!this._srcMatchesAllowedCbEmbedSrcPrefix(allowedCbEmbedSrcPrefix)) {
        this.addError(
          'Embed src "' + this._src + '" does not match first cb-embed src ' +
          'found, which is from the deployment at "' +
          allowedCbEmbedSrcPrefix + '". All cb-embeds in a single page must ' +
          'be from the same Course Builder deployment.');
      }
    },
    _getParentSrc: function() {
      return this._parentElement.attr('src') || '';
    },
    _srcMatchesAllowedCbEmbedSrcPrefix: function(allowedCbEmbedSrcPrefix) {
      if (this._src && allowedCbEmbedSrcPrefix === '') {
        // The first src found is empty or missing.
        return false;
      }

      return this._src.startsWith(allowedCbEmbedSrcPrefix);
    },
    _srcMatchesOrigin: function() {
      return this._src.startsWith(ORIGIN);
    }
  }

  $(function() {
    new Page(pageState).render();
  });
})(jQuery.noConflict(true), window._GCB_EMBED);
