# Copyright 2014 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Generic webapp2 handler for REST data sources."""

__author__ = 'Mike Gainer (mgainer@google.com)'

from common import catch_and_log
from common import crypto
from controllers import utils
from models import roles
from models import transforms
from models.data_sources import utils as data_sources_utils


class _AbstractRestDataSourceHandler(
    utils.ApplicationHandler, utils.RESTHandlerMixin):
    """Webapp2 handler for REST data sources.

    This class must be derived from to override the get_data_source_class()
    method.  This should be done only from analytics.py's registration-time
    functions which take care of registering URLs to serve REST resources
    (which is why this class is marked private).

    The responsibilities of this class are to provide a standardized interface
    which accepts URL parameters to identify resources, and JSON output to
    feed external clients.  It is expected that a very common use case for
    clients is the visual display of information on dashboard pages.  This,
    however, should in no way preclude the use of this interface to gain
    access to paginated versions of data held within CourseBuilder.

    Data source types supported are defined by the
    base_types.AbstractRestDataSource and base_types.ContextManager
    interface, which this class uses to accomplish its task.

    All AbstractRestDataSource URLs have one parameter in common:
      page_number=<N>: Specify which page of data is wanted.  This is
          zero-based.  Not all AbstractRestDataSource implementations have an
          easy way to know which is the last page until its data is fetched.
          Further, the "last" page may not always be last -- over time,
          more data may accumulate in the store being accessed.
          If this value is not provided, it is assumed to be zero.
    """

    @classmethod
    def get_data_source_class(cls):
        raise NotImplementedError(
            '_RestDataSourceHandler is a base class; derived classes '
            'must implement the get_data_source_class() method to tell the '
            'base class the type of the DB table it is to wrap.')

    def get(self):
        self.post()

    def post(self):
        """Returns a JSON response with a page of data and meta-information.

        The object contains the following fields:
        data:  Data objects from the object.
        log:  Entries made with a base_types.Log object.  These contain:
          timestamp:  Stringified version of the GMT time of the event
          level:  one of 'severe', 'warning', or 'info'
          message:  A string describing the event.
        schema:  A JSON schema describing the names and types of objects
          in the 'data' payload.
        params:  A dictionary containing an echo of the context parameters
          passed in.  These are specific to the sub-type of REST data source.
        source_context:  Any context that the REST data source wishes to
          retain across multiple calls to the same REST object.  It is
          not strictly required to re-send this into subsequent requests
          (as a parameter named 'source_context'), but doing so will provide
          significant performance improvements.  Note that if you are sending
          a 'source_context' parameter, it is not necessary to re-specify
          the set of parameters defining your query each time; these are
          retained in the context.  If you pass parameters which do not
          exactly match those in the source_context, the source_context
          is not used, and a new version with your new parameters is returned.
        """

        if (not roles.Roles.is_super_admin() and
            not roles.Roles.is_course_admin(self.app_context)):
            self.response.set_status(403)
            self.response.write('Forbidden')
            return

        catch_and_log_ = catch_and_log.CatchAndLog()
        data_source_class = self.get_data_source_class()
        context_class = data_source_class.get_context_class()
        page_number = int(self.request.get('page_number') or '0')

        output = {}
        source_context = None
        schema = None
        jobz = None
        with catch_and_log_.consume_exceptions('Building parameters'):
            source_context = self._get_source_context(
                data_source_class.get_default_chunk_size(), catch_and_log_)
        with catch_and_log_.consume_exceptions('Getting data schema'):
            schema = data_source_class.get_schema(
                self.app_context, catch_and_log_, source_context)
            for data_filter in data_source_class.get_filters():
                schema.update(data_filter.get_schema())
            output['schema'] = schema
        with catch_and_log_.consume_exceptions('Loading required job output'):
            jobz = data_sources_utils.get_required_jobs(
                data_source_class, self.app_context, catch_and_log_)
        if source_context and schema and jobz is not None:
            with catch_and_log_.consume_exceptions('Fetching results data'):
                data, page_number = data_source_class.fetch_values(
                    self.app_context, source_context, schema, catch_and_log_,
                    page_number, *jobz)
                output['data'] = data
                output['page_number'] = page_number
            with catch_and_log_.consume_exceptions('Encoding context'):
                output['source_context'] = self._encode_context(source_context)
                output['params'] = context_class.get_public_params_for_display(
                    source_context)
        output['log'] = catch_and_log_.get()
        output['source'] = data_source_class.get_name()

        self.response.headers['Content-Type'] = (
            'application/javascript; charset=utf-8')
        self.response.headers['X-Content-Type-Options'] = 'nosniff'
        self.response.headers['Content-Disposition'] = 'attachment'
        self.response.write(transforms.JSON_XSSI_PREFIX +
                            transforms.dumps(output))

    def _encode_context(self, source_context):
        """Save context as opaque string for use as arg to next call."""
        context_class = self.get_data_source_class().get_context_class()
        context_dict = context_class.save_to_dict(source_context)
        plaintext_context = transforms.dumps(context_dict)
        return crypto.EncryptionManager.encrypt_to_urlsafe_ciphertext(
            plaintext_context)

    def _get_source_context(self, default_chunk_size, catch_and_log_):
        """Decide whether to use pre-built context or make a new one.

        Callers to this interface may provide source-specific parameters to
        indicate what portion of the data source they are interested in, or
        pass in a pre-built context (as returned from _encode_context, above)
        returned by a previous request, or both.

        The preference is to use the encoded context, as long as it is
        provided and it is compatible with the individual source selection
        arguments which may be present.  This is done because the context
        may contain additional information that allows more efficient
        processing.

        Args:
          default_chunk_size: Recommended maximum number of data items
              in a page from the data_source.
          catch_and_log_: An object which is used to convert exceptions
              into messages returned to our REST client, and can also be
              used for informational annotations on progress.
        Returns:
          context object common to many functions involved in generating
          a data flow's JSON result.
        """
        context_class = self.get_data_source_class().get_context_class()
        new_context = context_class.build_from_web_request(self.request,
                                                           default_chunk_size)
        existing_context = None
        with catch_and_log_.consume_exceptions('Problem decrypting context'):
            existing_context = self._get_existing_context(context_class)

        ret = None
        if new_context and not existing_context:
            catch_and_log_.info('Creating new context for given parameters')
            ret = new_context
        elif existing_context and not new_context:
            catch_and_log_.info('Continuing use of existing context')
            ret = existing_context
        elif not new_context and not existing_context:
            catch_and_log_.info('Building new default context')
            ret = context_class.build_blank_default(self.request,
                                                    default_chunk_size)
        elif not context_class.equivalent(new_context, existing_context):
            catch_and_log_.info(
                'Existing context and parameters mismatch; discarding '
                'existing and creating new context.')
            ret = new_context
        else:
            catch_and_log_.info(
                'Existing context matches parameters; using existing context')
            ret = existing_context
        return ret

    def _get_existing_context(self, context_class):
        """Obtain and decode existing context, if present."""
        context_param = self.request.get('source_context')
        if not context_param:
            return None

        plaintext_context = (
            crypto.EncryptionManager.decrypt_from_urlsafe_ciphertext(
                str(context_param)))
        dict_context = transforms.loads(plaintext_context)
        return context_class.build_from_dict(dict_context)
