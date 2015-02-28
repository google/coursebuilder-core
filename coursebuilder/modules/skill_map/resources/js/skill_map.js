var SKILL_API_VERSION = '1';

/**
 * Parses JSON string that starts with an XSSI prefix.
 */
function parseJson(s) {
  // XSSI prefix. Must be kept in sync with models/transforms.py.
  var xssiPrefix = ")]}'";
  return JSON.parse(s.replace(xssiPrefix, ''));
}

var parseAjaxResponse = parseJson;
var showMsg = cbShowMsg;
var showMsgAutoHide = cbShowMsgAutoHide;

