function gcbTagHtml5TrackVideo(instanceId) {
  var index = 0;
  var video = $('#' + instanceId)[0];
  var eventLogger = function(event) {
    var dataDict = {
      'instance_id': instanceId,
      'event_id': index,
      'position': video.currentTime,
      'rate': video.playbackRate,
      'default_rate': video.defaultPlaybackRate,
      'event_type': event.type
   }
    gcbTagEventAudit(dataDict, 'html5video-event');
    index += 1;
  };

  $(video).on([
    'loadstart',  // The user agent begins looking for media data
    'loadeddata', // Can render at the current position for the first time.
    'abort',  // The user agent stops fetching [...] but not due to an error.
    'error',  // An error occurs while fetching the media data.
    'play',  // Play requested.
    'pause',  // Pause requested.
    'playing',  // Playback is ready to start after pause or delay
    'waiting',  // Playback stopped because the next frame is not available
    // 'seeking' causes far too many events when position wiper is moved.
    'seeked',  // The current playback position was changed.
    'ended',  // The end of the media resource was reached.
    'ratechange',  // Playback rate or default rate have changed.
    ].join(' '), eventLogger);

}
