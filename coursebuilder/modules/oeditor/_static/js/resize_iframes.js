// Defer execution to jQuery ready.
jQuery(function($) {
  // Resize child frames to the size of their contents every 75ms.
  setInterval(function() {
    $('iframe.gcb-needs-resizing').each(function(elem) {
      try {
        $(this).height($(this).contents().height());
      } catch(error) {
        // Eat errors, which are likely caused by the iframe child changing to
        // a domain that makes cross-frame operations impossible.
        // TODO(johncox): add a renderer layer to patch over this for
        // iframes containing ContentChunk payloads (for example, by making all
        // links open in a target=_blank).
      }
    });
  }, 75);
});
