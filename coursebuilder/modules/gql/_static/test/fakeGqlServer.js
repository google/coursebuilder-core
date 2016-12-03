/**
 * Provides a fake server to mock XHR requests to the GQL service in test.
 *
 * Usage:
 *   Import this file into your test page. It will add a single object,
 *   fakeGqlServer,into global scope. Use as in the following example:
 *
 *     beforeEach(function() {
 *       // Set up the server
 *       fakeGqlServer.setUp();
 *     });
 *     it('mocks the GQL service', function() {
 *       // Add query/response pairs to the server's repertoire
 *       var query = '{allCourses {edges {node {id title}}}}';
 *       var response = {
 *         allCourses: {
 *           edges: [
 *             {node: {id: 'course-1', title: 'Course 1'}},
 *             {node: {id: 'course-2', title: 'Course 2'}}
 *           ]
 *         }
 *       };
 *       fakeGqlServer.addResponse(query, response);
 *
 *       // Perform an action and send a response from the fake server
 *       doSomethingThatMakesAnXHR();
 *       fakeGqlServer.respond();
 *
 *       // Assert expectations about the results...
 *     });
 *     afterEach(function() {
 *       // Tidy up the server
 *       fakeGqlServer.tearDown();
 *     });
 */
 window.fakeGqlServer = {
  GQL_URL_REGEX: /.*\/modules\/gql\/query\?q=(.*)/,
  setUp: function() {
    this._responseTable = {};
    this._server = sinon.fakeServer.create();
    this._server.respondWith(
      'GET',
      this.GQL_URL_REGEX,
      this._handleRequest.bind(this));
  },
  addResponse: function(query, response, expanded_gcb_tags) {
    if (expanded_gcb_tags) {
      query += '&expanded_gcb_tags=' + encodeURIComponent(expanded_gcb_tags);
    }
    this._responseTable[this._hashQuery(query)] = response;
  },
  _hashQuery: function(query) {
    // TODO(jorr): This quick and easy hash should be improved
    return query.replace(/\s/g, '');
  },
  _getQuery: function(url) {
    var matches = url.match(this.GQL_URL_REGEX);
    if (matches.length != 2) {
      throw new Error('URL did not match expected GQL path: ' + url);
    }
    return decodeURIComponent(matches[1]);
  },
  _handleRequest: function(request) {
    var query = this._getQuery(request.url);
    var data = this._responseTable[this._hashQuery(query)];
    if (!data) {
      throw new Error('No response found matching query: ' + query);
    }

    var headers = { 'Content-Type': 'application/javascript' };
    var body = ')]}\'' + JSON.stringify({data: data});
    request.respond(200, headers, body);
  },
  respond: function() {
    this._server.respond();
  },
  tearDown: function() {
    this._server.restore();
  }
};
