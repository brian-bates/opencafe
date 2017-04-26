# Copyright 2015 Rackspace
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import requests
import six
from time import time
from warnings import warn

from cafe.common.reporting import cclogging
from cafe.engine.clients.base import BaseClient
from cafe.engine.http.config import HTTPPluginConfig

from requests.packages import urllib3
from requests.exceptions import (
    ConnectionError, HTTPError, Timeout, TooManyRedirects)


urllib3.disable_warnings()


def _log_transaction(log, level=cclogging.logging.DEBUG):

    def _safe_decode(text, incoming='utf-8', errors='replace'):
            """Decodes incoming text/bytes string using `incoming`
               if they're not already unicode.

            :param incoming: Text's current encoding
            :param errors: Errors handling policy. See here for valid
                values http://docs.python.org/2/library/codecs.html
            :returns: text or a unicode `incoming` encoded
                        representation of it.
            """
            if isinstance(text, six.text_type):
                return text

            return text.decode(incoming, errors)

    """ Paramaterized decorator
    Takes a python Logger object and an optional logging level.
    """
    def _decorator(func):
        """Accepts a function and returns wrapped version of that function."""
        def _wrapper(*args, **kwargs):
            """Logging wrapper for any method that returns a requests response.
            Logs requestslib response objects, and the args and kwargs
            sent to the request() method, to the provided log at the provided
            log level.
            """
            logline = '{0} {1}'.format(args, kwargs)

            try:
                log.debug(_safe_decode(logline))
            except Exception as exception:
                # Ignore all exceptions that happen in logging, then log them
                log.error(
                    'Exception occured while logging signature of calling'
                    'method in http client')
                log.exception()

            # Make the request and time it's execution
            response = None
            elapsed = None
            try:
                start = time()
                response = func(*args, **kwargs)
                elapsed = time() - start
            except Exception as exception:
                log.critical('HTTP request failed due to exception')
                log.exception()
                raise exception

            request_body = response.request.body

            # requests lib 1.0.4 removed params from response.request
            request_params = ''
            request_url = response.request.url
            if 'params' in dir(response.request):
                request_params = response.request.params
            elif '?' in request_url:
                request_url, request_params = request_url.split('?', 1)

            request_header = '\n{0}\nREQUEST SENT\n{0}\n'.format('-' * 12)
            logline = ''.join([
                request_header,
                'request method..: {0}\n'.format(response.request.method),
                'request url.....: {0}\n'.format(request_url),
                'request params..: {0}\n'.format(request_params),
                'request headers.: {0}\n'.format(response.request.headers),
                'request body....: {0}\n'.format(request_body)])
            try:
                log.log(level, _safe_decode(logline))
            except Exception as exception:
                # Ignore all exceptions that happen in logging, then log them
                log.log(level, request_header)
                log.error("An exception occured durring logging")
                log.exception()

            response_header = '\n{0}\nRESPONSE RECEIVED\n{0}\n'.format('-' * 17)
            logline = ''.join([
                response_header,
                'response status..: {0}\n'.format(response),
                'response time....: {0}\n'.format(elapsed),
                'response headers.: {0}\n'.format(response.headers),
                'response body....: {0}\n'.format(response.content),
                '-' * 79])
            try:
                log.log(level, _safe_decode(logline))
            except Exception as exception:
                # Ignore all exceptions that happen in logging, then log them
                log.log(level, response_header)
                log.error("An exception occured durring logging")
                log.exception()
            return response
        return _wrapper
    return _decorator


class BaseHTTPClient(BaseClient):
    """Re-implementation of Requests' api.py that removes many assumptions.
    Adds verbose logging.
    Adds support for response-code based exception injection.
    (Raising exceptions based on response code)

    @see: http://docs.python-requests.org/en/latest/api/#configurations
    """
    _log = cclogging.getLogger(__name__)

    def __init__(self):
        self.__config = HTTPPluginConfig()
        super(BaseHTTPClient, self).__init__()

    @_log_transaction(log=_log)
    def request(self, method, url, **kwargs):
        """ Performs <method> HTTP request to <url> using the requests lib"""
        retries = self.__config.retries_on_requests_exceptions

        # We always allow one attempt, retries are configured via EngineConfig
        allowed_attempts = 1 + retries

        # Offsetting xrange range by one to allow proper reporting of which
        # attempt we are on.
        for attempt in six.moves.xrange(1, allowed_attempts + 1):
            try:
                return requests.request(method, url, **kwargs)
            except(ConnectionError, HTTPError, Timeout, TooManyRedirects) as e:
                if retries:
                    warning_string = (
                        'Request Lib Error: Attempt {attempt} of '
                        '{allowed_attempts}\n'.format(
                            attempt=attempt,
                            allowed_attempts=allowed_attempts))
                    warn(warning_string)
                    warn(e)
                    warn('\n')
                    self._log.critical(warning_string)
                    self._log.exception(e)
                else:
                    raise e

    def put(self, url, **kwargs):
        """ HTTP PUT request """
        return self.request('PUT', url, **kwargs)

    def copy(self, url, **kwargs):
        """ HTTP COPY request """
        return self.request('COPY', url, **kwargs)

    def post(self, url, data=None, **kwargs):
        """ HTTP POST request """
        return self.request('POST', url, data=data, **kwargs)

    def get(self, url, **kwargs):
        """ HTTP GET request """
        return self.request('GET', url, **kwargs)

    def head(self, url, **kwargs):
        """ HTTP HEAD request """
        return self.request('HEAD', url, **kwargs)

    def delete(self, url, **kwargs):
        """ HTTP DELETE request """
        return self.request('DELETE', url, **kwargs)

    def options(self, url, **kwargs):
        """ HTTP OPTIONS request """
        return self.request('OPTIONS', url, **kwargs)

    def patch(self, url, **kwargs):
        """ HTTP PATCH request """
        return self.request('PATCH', url, **kwargs)

    @classmethod
    def add_exception_handler(cls, handler):
        """Adds a specific L{ExceptionHandler} to the HTTP client
        @warning: SHOULD ONLY BE CALLED FROM A PROVIDER THROUGH A TEST
                  FIXTURE
        """
        cls._exception_handlers.append(handler)

    @classmethod
    def delete_exception_handler(cls, handler):
        """Removes a L{ExceptionHandler} from the HTTP client
        @warning: SHOULD ONLY BE CALLED FROM A PROVIDER THROUGH A TEST
                  FIXTURE
        """
        if handler in cls._exception_handlers:
            cls._exception_handlers.remove(handler)


class HTTPClient(BaseHTTPClient):
    """
    @summary: Allows clients to inherit all requests-defined RESTful
              verbs. Redefines request() so that keyword args are passed
              through a named dictionary instead of kwargs.
              Client methods can then take parameters that may overload
              request parameters, which allows client method calls to
              override parts of the request with parameters sent directly
              to requests, overriding the client method logic either in
              part or whole on the fly.

    @see: http://docs.python-requests.org/en/latest/api/#configurations
    """

    def __init__(self):
        super(HTTPClient, self).__init__()
        self.default_headers = {}

    def request(
            self, method, url, headers=None, params=None, data=None,
            requestslib_kwargs=None):

        # set requestslib_kwargs to an empty dict if None
        requestslib_kwargs = requestslib_kwargs or {}

        # Set defaults
        params = params or {}
        verify = False

        # If headers are provided by both, headers "wins" over default_headers
        headers = dict(self.default_headers, **(headers or {}))

        # Override url if present in requestslib_kwargs
        if 'url' in requestslib_kwargs:
            url = requestslib_kwargs.get('url', None) or url
            del requestslib_kwargs['url']

        # Override method if present in requestslib_kwargs
        if 'method' in requestslib_kwargs:
            method = requestslib_kwargs.get('method', None) or method
            del requestslib_kwargs['method']

        # The requests lib already removes None key/value pairs, but we force
        # it here in case that behavior ever changes
        for key in requestslib_kwargs.copy():
            if requestslib_kwargs[key] is None:
                del requestslib_kwargs[key]

        # Create the final parameters for the call to the base request()
        # Wherever a parameter is provided both by the calling method AND
        # the requests_lib kwargs dictionary, requestslib_kwargs "wins"
        requestslib_kwargs = dict(
            {'headers': headers, 'params': params, 'verify': verify,
             'data': data}, **requestslib_kwargs)

        # Make the request
        return super(HTTPClient, self).request(
            method, url, **requestslib_kwargs)


class AutoMarshallingHTTPClient(HTTPClient):
    """@TODO: Turn serialization and deserialization into decorators so
    that we can support serialization and deserialization on a per-method
    basis"""
    def __init__(self, serialize_format=None, deserialize_format=None):
        super(AutoMarshallingHTTPClient, self).__init__()
        self.serialize_format = serialize_format
        self.deserialize_format = deserialize_format or self.serialize_format
        self.default_headers = {'Content-Type': 'application/{format}'.format(
            format=serialize_format)}

    def request(
            self, method, url, headers=None, params=None, data=None,
            response_entity_type=None, request_entity=None,
            requestslib_kwargs=None):

        # defaults requestslib_kwargs to a dictionary if it is None
        requestslib_kwargs = requestslib_kwargs or {}

        # set the 'data' parameter of the request to either what's already in
        # requestslib_kwargs, or the deserialized output of the request_entity
        if request_entity is not None:
            requestslib_kwargs = dict(
                {'data': request_entity.serialize(self.serialize_format)},
                **requestslib_kwargs)

        # Make the request
        response = super(AutoMarshallingHTTPClient, self).request(
            method, url, headers=headers, params=params, data=data,
            requestslib_kwargs=requestslib_kwargs)

        # Append the deserialized data object to the response
        response.request.__dict__['entity'] = None
        response.__dict__['entity'] = None

        # If present, append the serialized request data object to
        # response.request
        if response.request is not None:
            response.request.__dict__['entity'] = request_entity

        if response_entity_type is not None:
            response.__dict__['entity'] = response_entity_type.deserialize(
                response.content,
                self.deserialize_format)

        return response
