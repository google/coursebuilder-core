(function(angular) {
  var GRAPHQL_REST_HANDLER_URL = '/modules/gql/query';

  var GRAPHQL_NOT_ENABLED_WARNING = 'The GraphQL service is not enabled on ' +
      'this Course Builder instance. In order to enable the service, set the' +
      '"GraphQL" flag to "true" in ' +
      'Dashboard > Settings > Advanced site settings';
  var SERVER_ERROR = 'The query could not be processed because of a server ' +
      'error.';

  var USER_QUERY = '{currentUser {' +
      'loggedIn email ' +
      'loginUrl(destUrl: "__here__") ' +
      'logoutUrl(destUrl: "__here__")}}';

  // TODO(jorr): Add a picker for multiple sample queries
  var SAMPLE_QUERY = '{\n' +
      '  allCourses {\n' +
      '    edges {\n' +
      '      node {id title}\n' +
      '    }\n' +
      '  }\n' +
      '}\n';

  function cbLogin() {
    function controller($scope, $window, cbGraphQL) {
      var query = USER_QUERY.replace(/__here__/g, $window.location);
      cbGraphQL.query(query).then(function(response) {
        $scope.user = response.currentUser;
      });
    }
    return {
      restrict: 'E', // directive applies to elements only
      templateUrl: 'cbLogin.directive.html',
      controller: controller
    };
  }

  function cbGraphQL($q, $http) {
    function query(q) {
      return $q(function(resolve, reject) {

        function onSuccess(response) {
          resolve(response.data.data);
        }
        function onError(response) {
          if (response.status == 404) {
            reject([GRAPHQL_NOT_ENABLED_WARNING]);
          } else if (response.data && response.data.errors) {
            reject(response.data.errors);
          } else {
            reject([SERVER_ERROR]);
          }
        }

        $http({
          method: 'GET',
          url: GRAPHQL_REST_HANDLER_URL,
          params: {q: q},
          responseType: 'text'
        }).then(onSuccess, onError);
      });
    }
    return {query: query};
  }

  function queryCtl($scope, cbGraphQL) {
    function doQuery() {
      $scope.data = null;
      $scope.errorList = null;
      cbGraphQL.query($scope.query).then(function(data) {
        $scope.data = JSON.stringify(data, null, 4);
      }, function(errorList) {
        $scope.errorList = errorList;
      });
    }
    $scope.doQuery = doQuery;
    $scope.query = SAMPLE_QUERY;
  }

  angular.module('cbAngular', ['ngMaterial'])
      .directive('cbLogin', cbLogin)
      .factory('cbGraphQL', cbGraphQL)
      .controller('QueryCtl', queryCtl);

  angular.bootstrap(document, ['cbAngular']);
})(angular);
