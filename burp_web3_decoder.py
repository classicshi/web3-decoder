import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'libs'))
try:
    import eth_decoder.bootstrap 
except:
    pass
from burp import IBurpExtender
from burp import IMessageEditorTabFactory
from burp import IMessageEditorTab
from burp import IRequestInfo
from java.lang import System
import logging
import json
import traceback
from subprocess import check_output
from thread import start_new_thread

logging.basicConfig()
logger = logging.getLogger(__name__)

# Cache for ABI function return types
abi_return_cache = {}

# Mapping of hostnames to blockchain chain identifiers
hostname_chain_map = {}


def get_eth_decoder_location():
    """
    Tries to get the eth_decoder library "executable" location, by checking:
    1. In a virtualenv if it exists
    2. Directly executing the library (if prerequisites are installed it will work)
    3. From one of the precompiled binaries (Windows, Linux and OSX)
    :return: the command
    """
    # 1. Check if there is a virtualenv created and it works
    # venv/bin/python libs/eth_decoder.py
    # If you want to set up a virtualenv instead of using one of the precompiled binaries, you can:
    #   cd ${WHEREYOUSAVEDTHEEXTENSION}
    #   virtualenv -p python3 venv
    #   source venv/bin/activate
    #   pip install -r libs/requirements.txt
    venv_python = os.path.join(os.getcwd(), 'venv', 'bin', 'python')
    if os.access(venv_python, os.X_OK):
        try:
            command_l = [venv_python, os.path.join(os.getcwd(), 'libs', 'eth_decoder.py')]
            test_eth_decoder(command_l)
            return command_l
        except:
            pass

    # 2. Try to execute directly python without virtualenv
    try:
        command_l = ['python3', os.path.join(os.getcwd(), 'libs', 'eth_decoder.py')]
        test_eth_decoder(command_l)
        return command_l
    except:
        pass


    # 3. If virtualenv does not work, check with precompiled binaries
    DIST_LOCATION = os.path.join(os.getcwd(), 'libs', 'dist')
    system = System.getProperty('os.name')
    if system == "Linux":
        binary_name = 'eth_decoder.linux'
        binary_path = os.path.join(DIST_LOCATION, binary_name, binary_name)
        os.chmod(binary_path, 0755)
    elif system.startswith("Mac "):
        binary_name = 'eth_decoder.osx'
        binary_path = os.path.join(DIST_LOCATION, binary_name, binary_name)
        os.chmod(binary_path, 0755)
    elif system.startswith("Windows "):
        binary_name = 'eth_decoder.windows'
        binary_path = os.path.join(DIST_LOCATION, binary_name, binary_name + '.exe')
    else:
        raise RuntimeError("Cannot detect platform to choose binary: " + system)

    try:
        test_eth_decoder([binary_path])
        return [binary_path]
    except:
        logger.error('Cannot find a virtualenv or precompiled binary for eth_decoder')
        raise

def test_eth_decoder(command_l):
    """
    Test that the eth_decoder works

    :param command_l: command to launch program in list format, eg. ['./libs/dist/eth_decoder.windows'] or ['./venv/bin/python','libs/eth_decoder.py']
    :return: True if works as expected, with an exception otherwise
    """

    command_args = [
            '--abi',
            '[{"constant": true, "inputs": [], "name": "formula", "outputs": [{"name": "", "type": "address"}], "payable": false, "stateMutability": "view", "type": "function"}]',
            'decode_function_input',
            '0x7bed314446f3bffbc27775df2c6b439f3a376055',
            '0x4b75f54f'
    ]

    try:
        decoded_tx_json = check_output(command_l + command_args)

        if json.loads(decoded_tx_json)['function'] != "formula()":
            raise RuntimeError('Test of eth decoder failed: \n' + decoded_tx_json)
        return True
    except Exception:
        raise

# This contains the location of the decoder binary or program. e.g:
# ['./libs/dist/eth_decoder.windows'] or ['./venv/bin/python','libs/eth_decoder.py']
DECODER_COMMAND_L = get_eth_decoder_location()
print('Command used to use python3 eth_decoder module: ' + ' '.join(DECODER_COMMAND_L))


def _load_chains():
    """
    This function expects to find a chains.json file in the "current" folder
    :return:
    """
    with open('chains.json', 'r') as f:
        return json.load(f)


def _load_api_keys():
    """
    This function expects to find a .api_keys.json file in the "current" folder
    :return:
    """
    with open('.api_keys.json', 'r') as f:
        return json.load(f)

CHAINS = _load_chains()
API_KEYS = _load_api_keys()


def get_blockchain_explorer(chain_id):
    if str(chain_id) not in CHAINS:
        raise RuntimeError('Chain ID not supported: %s' % chain_id)

    return CHAINS[str(chain_id)]['explorer']


def get_api_key_name(chain_id):
    blockchain_explorer_name = get_blockchain_explorer(chain_id).split(".")[-2].upper()
    return '%s_API' % blockchain_explorer_name


def get_api_key(chain_id):
    """ Given a Chain ID, retrieves the API key from an environment variable
     if this API was not initialized with a key
     The key is based on the hostname of the Blockchain explorer:
       api.etherscan.io -> ETHERSCAN_API
       bscscan.com -> BSCSCAN_API
    """
    # Get API key from environment variable based on Chain ID
    api_key_name = get_api_key_name(chain_id)
    api_key = os.getenv(api_key_name)
    if api_key is not None:
        return api_key
    else:
        # Get API key from .api_keys.json file
        if api_key_name in API_KEYS:
            return API_KEYS[api_key_name]
    return ''


class BurpExtender(IBurpExtender, IMessageEditorTabFactory):
    #
    # implement IBurpExtender
    #

    def registerExtenderCallbacks(self, callbacks):
        # keep a reference to our callbacks object
        self._callbacks = callbacks

        # obtain an extension helpers object
        self._helpers = callbacks.getHelpers()

        # set our extension name
        callbacks.setExtensionName("Web3 Decoder")

        # register ourselves as a message editor tab factory
        callbacks.registerMessageEditorTabFactory(self)

        return

    #
    # implement IMessageEditorTabFactory
    #
    def createNewInstance(self, controller, editable):
        # create a new instance of our custom editor tab
        return EthJSONRPCInputTab(self, controller, editable, self._callbacks, self._helpers)


#
# class implementing IMessageEditorTab
#
class EthJSONRPCInputTab(IMessageEditorTab):
    def __init__(self, extender, controller, editable, callbacks, helpers):
        self._extender = extender
        self._editable = editable
        self._callbacks = callbacks
        self._helpers = helpers

        # create an instance of Burp's text editor, to display our deserialized data
        self._txtInput = extender._callbacks.createTextEditor()
        self._txtInput.setEditable(editable)
        return

    def getTabCaption(self):
        """
        This method returns the caption that should appear on the custom tab when it is displayed.
        Note: Burp invokes this method once when the tab is first generated,
         and the same caption will be used every time the tab is displayed.

        :return: The caption that should appear on the custom tab when it is displayed.
        """
        return "Web3"

    def getUiComponent(self):
        """
        This method returns the component that should be used as the contents of the custom tab when it is displayed.
        Note: Burp invokes this method once when the tab is first generated,
         and the same component will be used every time the tab is displayed.
        :return: The component that should be used as the contents of the custom tab when it is displayed.
        """
        return self._txtInput.getComponent()

    def isEnabled(self, content, isRequest):
        """
        The hosting editor will invoke this method before it displays a new HTTP message,
        so that the custom tab can indicate whether it should be enabled for that message.
        :param content: The message that is about to be displayed, or a zero-length array if the existing message is to
         be cleared.
        :param isRequest:  Indicates whether the message is a request or a response.
        :return: The method should return true if the custom tab is able to handle the specified message,
         and so will be displayed within the editor. Otherwise, the tab will be hidden while this message is displayed.
        """
        # enable this tab for requests containing a data parameter
        #return isRequest and not self._extender._helpers.getRequestParameter(content, "token") is None
        if isRequest:
            request_info = self._extender._helpers.analyzeRequest(content)
            body = content[request_info.getBodyOffset():]
            body_str = self._extender._helpers.bytesToString(body)
            if request_info.getContentType() == IRequestInfo.CONTENT_TYPE_JSON:
                json_body = json.loads(body_str, strict=False)
                return ('jsonrpc' in json_body and 'method' in json_body
                       and json_body['method'] in ('eth_call', 'eth_sendRawTransaction')
                       and 'params' in json_body)
        else:
            response_info = self._extender._helpers.analyzeResponse(content)
            body = content[response_info.getBodyOffset():]
            body_str = self._extender._helpers.bytesToString(body)
            if response_info.getStatedMimeType() == 'JSON':
                json_body = json.loads(body_str, strict=False)
                return ('jsonrpc' in json_body
                        and 'id' in json_body
                        and 'result' in json_body
                        )

        return False


    def setMessage(self, content, isRequest):
        """
        The hosting editor will invoke this method to display a new message or to clear the existing message.
        This method will only be called with a new message if the tab has already returned true to a call to isEnabled()
        with the same message details.
        :param content: The message that is to be displayed, or null if the tab should clear its contents and disable
         any editable controls.
        :param isRequest: Indicates whether the message is a request or a response.
        :return: None
        """
        start_new_thread(self._setMessage, (content, isRequest))


    def _setMessage(self, content, isRequest):
        self._txtInput.setEditable(False)

        if (content is None):
            # clear our display
            self._txtInput.setText(None)
            self._txtInput.setEditable(False)

        else:
            if isRequest:
                #
                # JSON-RPC REQUESTS
                #
                request_info = self._extender._helpers.analyzeRequest(content)
                body = content[request_info.getBodyOffset():]
                body_str = self._extender._helpers.bytesToString(body)
                if request_info.getContentType() == IRequestInfo.CONTENT_TYPE_JSON:
                    json_body = json.loads(body_str, strict=False)
                    # print json_body['params']

                    #
                    # eth_call
                    #
                    if json_body['method'] == 'eth_call':
                        params = [i for i in json_body['params'] if isinstance(i, dict)]
                        chain_id = self._get_chain_id(request_info)
                        provider = self._get_provider_url(request_info)
                        decoded_tx_json = self.decode_tx_input(chain_id, params[0]['to'], params[0]['data'], provider)
                        self._txtInput.setText(self._extender._helpers.stringToBytes(decoded_tx_json))

                        # Save the output type from the ABI to use it later when decoding the result
                        request_id = json_body['id']
                        decoded_tx = json.loads(decoded_tx_json, strict=False)

                        # Set the field editable
                        self._txtInput.setEditable(True)
                        try:
                            global abi_return_cache
                            abi_return_cache[request_id] = decoded_tx['abi']['outputs']
                            # print request_id, abi_return_cache[request_id]
                        except Exception:
                            #logger.error(traceback.format_exc())
                            pass

                    #
                    # eth_sendRawTransaction
                    #
                    elif json_body['method'] == 'eth_sendRawTransaction':

                        # raw_tx = json_body['params'][0]
                        # decoded_raw_tx_json = self.decode_raw_tx(raw_tx)
                        # self._txtInput.setText(self._extender._helpers.stringToBytes(decoded_raw_tx_json))

                        decoded_tx_list = []
                        for raw_tx in json_body['params']:
                            chain_id = self._get_chain_id(request_info)
                            provider = self._get_provider_url(request_info)
                            decoded_raw_tx_json = self.decode_raw_tx(chain_id, raw_tx, provider)
                            decoded_raw_tx = json.loads(decoded_raw_tx_json, strict=False)
                            decoded_tx_list.append(decoded_raw_tx)

                        decoded_tx_list_json = json.dumps(decoded_tx_list, indent=2)
                        self._txtInput.setText(self._extender._helpers.stringToBytes(decoded_tx_list_json))

            else:
                #
                # JSON-RPC RESPONSES
                #
                response_info = self._extender._helpers.analyzeResponse(content)
                body = content[response_info.getBodyOffset():]
                body_str = self._extender._helpers.bytesToString(body)
                if response_info.getStatedMimeType() == 'JSON':
                    json_body = json.loads(body_str, strict=False)
                    request_id = json_body['id']
                    global abi_return_cache
                    #print request_id, abi_return_cache[request_id], json_body['result']
                    if request_id in abi_return_cache:
                        types = []
                        for output in abi_return_cache[request_id]:
                            types.append(output['type'])
                        decoded_return_json = self.decode_list_abi(types, json_body['result'])
                        # print decoded_return_json
                        self._txtInput.setText(self._extender._helpers.stringToBytes(decoded_return_json))
                    else:
                        message = {'error': "Analyze Request before analyzing the response",
                                   'result': json_body['result']}
                        self._txtInput.setText(self._extender._helpers.stringToBytes(json.dumps(message, indent=2)))

        # remember the displayed content
        self._currentMessage = content
        return


    def getMessage(self):

        # determine whether the user modified the deserialized data
        if (self._txtInput.isTextModified()):
            try:
                # Reserialize the data
                json_data_str = self._helpers.bytesToString(self._txtInput.getText())
                result = self.encode_function_input(json_data_str)
                res_dict = json.loads(result)
                if 'data' in res_dict:
                    data = res_dict['data']
                else:
                    raise Exception('No data: ' + str(res_dict))

                request_info = self._extender._helpers.analyzeRequest(self._currentMessage)
                body = self._currentMessage[request_info.getBodyOffset():]
                body_str = self._extender._helpers.bytesToString(body)
                if request_info.getContentType() == IRequestInfo.CONTENT_TYPE_JSON:
                    json_body = json.loads(body_str, strict=False)
                    for param in json_body['params']:
                        if isinstance(param, dict) and 'data' in param:
                            param['data'] = data

                            new_body_str = json.dumps(json_body, indent=2)
                            new_body = self._extender._helpers.stringToBytes(new_body_str)
                            headers = request_info.getHeaders()
                            new_request = self._helpers.buildHttpMessage(headers, new_body)
                            return new_request

            except Exception as e:
                logger.error(traceback.format_exc())

            return self._currentMessage

            # update the request with the new data field
            # new_req_str = self._extender._helpers.bytesToString(self._currentMessage).replace(self.jwt, jwt_token)
            # new_req = self._extender._helpers.stringToBytes(new_req_str)
            # return new_req
        else:
            return self._currentMessage


    def isModified(self):
        return self._txtInput.isTextModified()

    def getSelectedData(self):
        return self._txtInput.getSelectedText()

    def _get_provider_url(self, request_info):
        headers = request_info.getHeaders()
        host_header = [h for h in headers if h.startswith('Host:') or h.startswith('host:')][0]
        host = host_header.split(':', 1)[1].strip()
        if ':' in host:
            port = int(host.split(':')[1])
            is_https = str(port).endswith('443')
        else:
            port = 443
            is_https = True
        proto = 'https' if is_https else 'http'
        path = headers[0].split(' ')[1]
        url = '%s://%s:%s%s' % (proto, host, port, path)
        return url

    def _get_chain_id(self, request_info):
        self._get_provider_url(request_info)
        headers = request_info.getHeaders()
        host_header = [h for h in headers if h.startswith('Host:') or h.startswith('host:')][0]
        host = host_header.split(':', 1)[1].strip()
        if ':' in host:
            port = int(host.split(':')[1])
            is_https = str(port).endswith('443')
        else:
            port = 443
            is_https = True

        if host in hostname_chain_map:
            return hostname_chain_map[host]
        else:
            # Retrieve chain ID
            body = '{"method":"eth_chainId","id":1337,"jsonrpc":"2.0"}'
            proto = 'https' if is_https else 'http'
            path = headers[0].split(' ')[1]
            url = '%s://%s:%s%s' % (proto, host, port, path)



            new_headers = [header for header in headers if header.startswith('POST ')
                                                        or header.startswith('Host:')
                                                        or header.startswith('Content-Type:')
                                                        or header.startswith('User-Agent:')
                                                        or header.startswith('Accept:')
                                                        or header.startswith('Referer:')
                                                        or header.startswith('Origin:')]



            try:
                body_bytes = self._helpers.stringToBytes(body)
                req_bytes = self._helpers.buildHttpMessage(new_headers, body_bytes)
                service = self._helpers.buildHttpService(host, port, is_https)
                request_response = self._callbacks.makeHttpRequest(service, req_bytes)
                response_bytes = request_response.getResponse()
                response_info = self._helpers.analyzeResponse(response_bytes)
                response_body = response_bytes[response_info.getBodyOffset():]
                body_str = self._helpers.bytesToString(response_body)

                chain_id_hex = json.loads(body_str)['result']
                chain_id = str(int(chain_id_hex, 16))
                print('Chain id (%s): %s' %(host, chain_id) )
                hostname_chain_map[host] = chain_id
                if chain_id == '1337':
                    msg = 'WARNING: Chain ID 1337 is usually Ganache. ' \
                          'If you are forking another network, copy its chain ID with --chain.chainId'
                    print(msg)
                    self._callbacks.issueAlert(msg)
                try:
                    if chain_id not in CHAINS:
                        msg = 'ERROR: Chain ID %s not supported! See the chains.json file for supported chains' % chain_id
                        print(msg)
                        self._callbacks.issueAlert(msg)
                    elif len(get_api_key(chain_id)) == 0:
                        msg = ('No %s set in .api_keys.json, '
                               'API requests to %s will be limited to 1req/5s') \
                              % (get_api_key_name(chain_id), get_blockchain_explorer(chain_id))
                        print(msg)
                        self._callbacks.issueAlert(msg)
                except:
                    logger.error(traceback.format_exc())
                    pass
                hostname_chain_map[host] = chain_id
                return chain_id
            except:
                msg = 'Error trying to obtain Chain ID of %s ETH-RPC Endpoint. Defaulting to ETH Mainnet (1)' % (url)
                print(msg)
                self._callbacks.issueAlert(msg)
                logger.error(traceback.format_exc())
                return '1'

    def decode_tx_input(self, chain_id, address, data, provider):
        try:
            return check_output(DECODER_COMMAND_L + ['--chain', chain_id, '--provider', provider, 'decode_function_input', address, data])
        except Exception:
            logger.error(traceback.format_exc())
            return None

    def decode_single_abi(self, type, data):
        try:
            return check_output(DECODER_COMMAND_L + ['decode_function_input', type, data])
        except Exception:
            logger.error(traceback.format_exc())
            return None

    def decode_list_abi(self, types, data):
        try:
            types_json = json.dumps(types)
            return check_output(DECODER_COMMAND_L + ['decode_abi', types_json, data])
        except Exception:
            logger.error(traceback.format_exc())
            return None

    def decode_raw_tx(self, chain_id, raw_tx, provider):
        try:
            return check_output(DECODER_COMMAND_L + ['--chain', chain_id, '--provider', provider, 'decode_raw_transaction', raw_tx])
        except Exception:
            logger.error(traceback.format_exc())
            return None

    def encode_function_input(self, json_data_str):
        try:
            return check_output(DECODER_COMMAND_L + ['encode_function_input', json_data_str])
        except Exception:
            logger.error(traceback.format_exc())
            return None
