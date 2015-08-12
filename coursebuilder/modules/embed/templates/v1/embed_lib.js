(function(jQuery, pageState) {

  var $ = jQuery;

  var ENV = JSON.parse('{{ env | js_string }}');
  var EMBED_CHILD_CSS_URL = ENV['embed_child_css_url'];
  var IN_SESSION = ENV['in_session'];
  var MATERIAL_ICONS_URL = ENV['material_icons_url'];
  var ORIGIN = ENV['origin'];
  var RESOURCE_URI_PREFIX_BOUNDARY = ENV['resource_uri_prefix_boundary'];
  var ROBOTO_URL = ENV['roboto_url'];
  var SIGN_IN_URL = ENV['sign_in_url'];

  var EMBED_TAG_NAME = 'cb-embed';
  var ERROR_CLASS = EMBED_TAG_NAME + '-error';
  var IFRAME_CLASS = EMBED_TAG_NAME + '-frame';
  var IFRAME_CONTENT_CLASS = IFRAME_CLASS + '-content';
  var MATERIAL_ICONS_CLASS = 'material-icons';
  var SIGN_IN_BUTTON_CLASS = EMBED_TAG_NAME + '-sign-in-button';
  var SIGN_IN_CONTAINER_CLASS = EMBED_TAG_NAME + '-sign-in-container';
  var SIGN_IN_CONTENT_CLASS = EMBED_TAG_NAME + '-sign-in-content';
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

  function Frame(parentElement) {
    this._iframe = null;
    this._iframeCanBePopulated = $.Deferred();
    this._parentElement = parentElement;
    this._resizeIntervalId = null;
    this._src = null;
    this._makeIframe();
  }
  Frame.prototype = {
    resize: function() {
      if (this._isLocal()) {
        var target = this._iframe.contents().find('.' + IFRAME_CONTENT_CLASS);
        var htmlTarget = this._iframe.contents().find('html');
        this._resizeLocal(target, htmlTarget);
      } else {
        this._resizeRemote();
      }
    },
    setLocalContent: function(content) {
      this._src = null;
      // In FF, elements added to an iframe before its document is loaded will
      // be discarded. Defer insertion until the iframe is loaded.
      $.when(this._iframeCanBePopulated).then(function() {
        this._populateLocalIframe(content);
      }.bind(this));
    },
    setRemoteSrc: function(src) {
      this._stopLocalResizing();
      this._src = src;
      this._iframe.attr('src', this._src);
    },
    _isLocal: function() {
      return (this._src === null);
    },
    _makeIframe: function() {
      this._iframe = $('<iframe>')
        .attr('class', IFRAME_CLASS)
        .attr('scrolling', 'no')
        .css('height', '0')
        .load(function() {
          this._iframeCanBePopulated.resolve();
        }.bind(this));
      // Insert now so iframe document exists for later accessors.
      this._parentElement.append(this._iframe);
    },
    _makeStylesheetLink: function(url) {
      return $('<link>')
        .attr('href', url)
        .attr('rel', 'stylesheet')
        .attr('type', 'text/css');
    },
    _populateLocalIframe: function(element) {
      var frameContents = this._iframe.contents();
      frameContents.find('head').empty()
          .append(this._makeStylesheetLink(EMBED_CHILD_CSS_URL))
          .append(this._makeStylesheetLink(MATERIAL_ICONS_URL))
          .append(this._makeStylesheetLink(ROBOTO_URL));
      frameContents.find('body').empty()
          .append($('<div>').attr('class', IFRAME_CONTENT_CLASS));
      this._iframe.contents().find('.' + IFRAME_CONTENT_CLASS).append(element);
      this._startLocalResizing();
    },
    _resizeLocal: function(target, htmlTarget) {
      // When we call find() on an element, it pulses in browser inspectors.
      // This function is called in a polling loop. To keep inspectors from
      // strobing, we pass elements in as arguments rather than find()ing them.
      //
      // Additionally, different browsers have different opinions about the size
      // of an iframe's <html> element versus our container. We take the max to
      // avoid truncation.
      var iframeHeight = this._iframe.height();
      var newHeight = Math.max(
        target.outerHeight(true), htmlTarget.outerHeight(true));

      if (iframeHeight !== newHeight) {
        this._iframe.height(newHeight);
      }
    },
    _resizeRemote: function() {
      // Clears height and tells the child to request a resize.
      this._stopLocalResizing();
      this._iframe.css('height', '').css('width', '');
      this._iframe[0].contentWindow.postMessage({action: 'resize'}, '*');
    },
    _startLocalResizing: function() {
      // When resizing local content, there is no good event to listen on to
      // know that the iframe is fully rendered and its size can be reliably
      // sampled. All manner of corner-cases result. For reliability, we poll.
      this._stopLocalResizing();
      var target = this._iframe.contents().find('.' + IFRAME_CONTENT_CLASS);
      var htmlTarget = this._iframe.contents().find('html');
      this._resizeIntervalId = window.setInterval(
        this._resizeLocal.bind(this, target, htmlTarget), 50);
    },
    _stopLocalResizing: function() {
      if (this._resizeIntervalId) {
        window.clearInterval(this._resizeIntervalId);
        this._resizeIntervalId = null;
      }
    }
  };

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
    _handleResizeMessage: function(height, width, sourceWindow) {
      $('.' + IFRAME_CLASS).each(function(unused, iframe) {
        if (iframe.contentWindow == sourceWindow) {
          $(iframe).height(height).width(width);
          return false;
        }
      });
    },
    _handleWindowResize: debounce(function() {
      // Handles window resize events. On Chrome/FF and perhaps other browsers,
      // these fire continually while the window is being resized. The handler
      // may do expensive operations like cross-frame messaging, which performs
      // poorly and must be throttled.
      $.each(this._widgets, function(unused, widget) {
        widget.resize();
      });
    }),
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
            this._handleResizeMessage(data.height, data.width, sourceWindow);
            break;
        }
      }.bind(this));
      $(window).on('resize', this._handleWindowResize.bind(this));
    },
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
    this._frame = new Frame(this._parentElement);
    this._src = this._getParentSrc();
  }
  Widget.prototype = {
    addError: function(error) {
      this._errors.push(error);
    },
    hasErrors: function() {
      return this._errors.length > 0;
    },
    resize: function() {
      this._frame.resize();
    },
    showAuthenticated: function() {
      this._frame.setRemoteSrc(this._src);
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

      this._frame.setLocalContent(div);
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

      this._frame.setLocalContent(container);
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
