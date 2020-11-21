import json
import logging
import requests
import time
import urllib3

from quotecast.constants.endpoint import Endpoint
from quotecast.constants.headers import Headers
from quotecast.pb.quotecast_pb2 import (
    Metadata,
    Quotecast,
    Request,
)
from typing import Union


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# pylint: disable=no-member

def build_session(
    headers:dict=None,
)->requests.Session:
    """ Setup a requests.Session object.

    Arguments:
    headers {dict} -- Headers to used for the Session.

    Returns:
    {requests.Session} -- Session object with the right headers.
    """

    session = requests.Session()

    if isinstance(headers, dict) :
        session.headers.update(headers)
    else:
        session.headers.update(Headers.get_headers())

    return session

def build_logger():
    return logging.getLogger(__name__)

def get_session_id(
    user_token:int,
    session:requests.Session=None,
    logger:logging.Logger=None,
)->str:
    """ Retrieve "session_id".
    This "session_id" is used by most Degiro's trading endpoint.

    Returns:
        str -- Session id
    """

    if logger is None:
        logger = build_logger()
    if session is None:
        session = build_session()
    
    url = Endpoint.URL
    url = f'{url}/request_session'
    version = Endpoint.VERSION
    
    parameters = {'version': version, 'userToken': user_token}
    data = '{"referrer":"https://trader.degiro.nl"}'

    request = requests.Request(
        method='POST',
        url=url,
        data=data,
        params=parameters
    )
    prepped = session.prepare_request(request=request)

    try:
        response = session.send(request=prepped, verify=False)
        response_dict = response.json()
    except Exception as e:
        logger.fatal(e)
        return False
    
    logger.info('get_session_id:response_dict: %s', response_dict)

    if 'sessionId' in response_dict:
        return response_dict['sessionId']
    else:
        return None

def fetch_data(
    session_id:str,
    session:requests.Session=None,
    logger:logging.Logger=None,
)->Quotecast:
    """
    Fetch data from the feed.

    Parameters :
    session_id {str} -- API's session id.

    Returns:
    Quotecast:
        quotecast.json_data : raw JSON data string.
        quotecast.metadata.response_datetime : reception timestamp.
        quotecast.metadata.request_duration : request duration.
    """

    if logger is None:
        logger = build_logger()
    if session is None:
        session = build_session()
    
    url = Endpoint.URL
    url = f'{url}/{session_id}'

    request = requests.Request(method='GET', url=url)
    prepped = session.prepare_request(request=request)

    start_ns = time.perf_counter_ns()
    response = session.send(request=prepped, verify=False)
    # We could have used : response.elapsed.total_seconds()
    duration_ns = time.perf_counter_ns() - start_ns

    if response.text == '[{"m":"sr"}]' :
        raise BrokenPipeError('A new "session_id" is required.')

    quotecast = Quotecast()
    quotecast.json_data = response.text
    # There is no "date" header returned
    # We could have used : response.cookies._now
    quotecast.metadata.response_datetime.GetCurrentTime()
    quotecast.metadata.request_duration.FromNanoseconds(duration_ns)

    logger.debug(
        'fetch_data:json_data.response_json: %s',
        quotecast.json_data
    )
    logger.debug(
        'fetch_data:metadata.response_datetime: %s',
        quotecast.metadata.response_datetime.ToJsonString()
    )
    logger.debug(
        'fetch_data:metadata.request_duration: %s',
        quotecast.metadata.request_duration
    )

    return quotecast

def subscribe(
    request:Request,
    session_id:str,
    raw:bool=False,
    session:requests.Session=None,
    logger:logging.Logger=None,
)->Union[Request, int]:
    """ Subscribe/unsubscribe to a feed from Degiro's QuoteCast API.
    Parameters :
    session_id {str} -- API's session id.

    Returns :
    {bool} -- Whether or not the subscription succeeded.
    """

    if logger is None:
        logger = build_logger()
    if session is None:
        session = build_session()
    
    url = Endpoint.URL
    url = f'{url}/{session_id}'
    vwd_id = request.vwd_id
    label_list = request.label_list

    if request.action == Request.Action.SUBSCRIBE:
        action = 'req'
    elif request.action == Request.Action.UNSUBSCRIBE:
        action = 'rel'
    else:
        raise AttributeError('Unknown "request.action".')
    
    data = list()
    for label in label_list:
        data.append(f'{action}({vwd_id}.{label})')
    data = '{"controlData":"' + ';'.join(data) + ';"}'

    session_request = requests.Request(method='POST', url=url, data=data)
    prepped = session.prepare_request(request=session_request)

    logger.debug('subscribe:payload: %s', data)
    
    try:
        response_raw = session.send(request=prepped, verify=False)
        request.status_code = response_raw.status_code

        if raw == True:
            response = response_raw.status_code
        else:
            response = request
    except Exception as e:
        logger.fatal(e)
        return False

    logger.debug(
        'subscribe:response.text: %s',
        response_raw.text
    )
    logger.debug(
        'subscribe:response.status_code: %s',
        response_raw.status_code
    )

    return response