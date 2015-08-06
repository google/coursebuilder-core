(function() {

  var currentSize = {
    height: -1,
    width: -1
  }

  function getHeight() {
    return Math.max(
        document.documentElement.offsetHeight,
        document.documentElement.scrollHeight);
  }

  function getWidth() {
    return Math.max(
        document.documentElement.offsetWidth,
        document.documentElement.scrollWidth);
  }

  function maybeResize() {
    var height = getHeight();
    var width = getWidth();
    if (currentSize.height === height && currentSize.width === width) {
      return;
    }

    currentSize = {
      height: height,
      width: width
    }
    var data = {
      action: 'resize',
      height: height,
      width: width
    }
    window.parent.postMessage(data, '*');
  }

  function onMessage(event) {
    if (event.source !== window.parent) {
      return;
    }
    if (event.data.action === 'resize') {
      currentSize = {};
    }
  }

  function main() {
    setInterval(maybeResize, 50);
    window.addEventListener('message', onMessage, false);
  }

  main();
})();
