// embed YouTube API only once
if (typeof(window['gcb_tag_youtube_videos']) == "undefined"){
  // send a milestone event every time this many seconds of video are watched
  var GCB_VIDEO_TRACKING_CHUNK_SEC = 30;

  // video player status
  var gcb_youtube_player_ready = false;

  // list of videos to embed
  var gcb_tag_youtube_uid = 0;
  var gcb_tag_youtube_videos = [];

  function gcbTagYoutubeInit(){
    var tag = document.createElement('script');
    tag.src = 'https://www.youtube.com/iframe_api';
    document.body.appendChild(tag);
  }

  function gcbTagYoutubeEnqueueVideo(video_id, container_id){
    var instance_id = gcb_tag_youtube_uid;
    gcb_tag_youtube_uid++;

    var div_id = 'gcb-tag-youtube-video-' + instance_id;
    var div1 = document.createElement('div');
    div1.className = 'gcb-video-container';
    var div2 = document.createElement('div');
    div2.id = div_id;
    div2.className = "youtube-player";
    div1.appendChild(div2);
    document.getElementById(container_id).appendChild(div1);

    gcb_tag_youtube_videos.push([instance_id, div_id, video_id]);

    gcbTagYoutubeTryEmbedEnqueuedVideos();
  }

  function onYouTubeIframeAPIReady() {
    gcb_youtube_player_ready = true;
    gcbTagYoutubeTryEmbedEnqueuedVideos();
  }

  function gcbTagYoutubeTryEmbedEnqueuedVideos() {
    if (gcb_youtube_player_ready) {
      while(gcb_tag_youtube_videos.length > 0) {
        var tuple = gcb_tag_youtube_videos.shift(0)
        var instance_id = tuple[0]
        var div_id = tuple[1]
        var video_id = tuple[2]
        gcbTagYoutubeEmbedVideo(instance_id, div_id, video_id);
      }
    }
  }

  function gcbTagYoutubeEmbedVideo(instance_id, div_id, video_id){
    // each event has sequential ever increasing index
    var index = 0;

    // last video milestone position
    var last_pos_sec = 0;

    var player;
    player = new YT.Player(div_id, {
      height: '400',
      width: '650',
      videoId: video_id,
      playerVars: { rel: '0' },
      events: {
        'onReady': function (){
          setInterval(function(){
            var current_pos_sec = Math.round(player.getCurrentTime());
            var delta = current_pos_sec - last_pos_sec;

            // send event and update position when milestone reached
            if (delta > GCB_VIDEO_TRACKING_CHUNK_SEC) {
              gcbTagEventAudit({
                  'video_id': video_id,
                  'instance_id': instance_id,
                  'event_id': index,
                  'position': current_pos_sec
              }, 'youtube-milestone');
              index++;
              last_pos_sec = current_pos_sec;
            }

            // also update position if video was rewinded
            if (delta < 0) {
              last_pos_sec = current_pos_sec;
            }
          }, 1000);
        },
        'onStateChange': function(event) {
          var trackable = (event.data == 0) || (event.data == 1);
          if (trackable) {
            var current_pos_sec = Math.round(player.getCurrentTime());
            gcbTagEventAudit({
                'video_id': video_id,
                'instance_id': instance_id,
                'event_id': index,
                'position': current_pos_sec,
                'data': event.data
            }, 'youtube-event');
            index++;
          }
        }
      }
    });
  }

  gcbTagYoutubeInit();
}