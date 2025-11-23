import json
import logging
from functools import lru_cache
from typing import List, Any, Tuple

from eth_abi import decode_single, decode_abi, encode_abi
from eth_typing import ChecksumAddress

from eth_utils import encode_hex

from hexbytes import HexBytes
from web3 import Web3
from web3._utils.abi import abi_to_signature
from web3.eth import Contract

from .etherscan import EtherscanAPI
from .etherscan.etherscan_api import ABINotFoundException

try:
    from eth.vm.forks.arrow_glacier.transactions import ArrowGlacierTransactionBuilder as TransactionBuilder
    DECODE_RAW_TRANSACTIONS=True
except:
    DECODE_RAW_TRANSACTIONS=False

logger = logging.getLogger(__name__)


class FunctionInputDecodeException(Exception):
    pass


class EthereumDecoder:
    def __init__(self, w3: Web3, etherscan_api: EtherscanAPI):
        """
        Ethereum transactions and calls decoder

        :param w3: web3.Web3 initialized object
        :param etherscan_api: .etherscan.EtherscanAPI initialized object (can be initialized for other block explorers)
        """
        self.w3 = w3
        self.etherscan_api = etherscan_api

    @lru_cache(maxsize=None)
    def get_contract(self, contract_address: ChecksumAddress, abi: dict = None) -> Contract:
        """
        Given a contract address and optionally an ABI, will create a Web3 Contract

        :param contract_address: ChecksumAddress of the contract
        :param abi: Optional, ABI dictionary, if None, will be downloaded from Block Explorer if Available
        :return: Initialized web3.eth.Contract
        """
        if abi is None:
            abi = self.etherscan_api.get_abi(contract_address)
            if abi is None:
                self.get_contract.cache_clear()
                return None

        contract = self.w3.eth.contract(address=contract_address, abi=abi)
        return contract

    def is_proxy(self, contract: Contract) -> bool:
        """Checks if it is an implementation of Delegate Proxy https://eips.ethereum.org/EIPS/eip-897
        :param contract: web3.eth.Contract object
        :return: True if it detects a proxy, False otherwise
        """
        try:
            if (contract.get_function_by_signature('implementation()')
                    and contract.get_function_by_signature('proxyType()')):
                implementation_address = contract.functions.implementation().call()
                if implementation_address is not None:
                    return True
        except:
            pass
        return False

    def get_proxy_implementation(self, contract: Contract) -> Contract:
        """
        Gets the contract of the proxy implementation, given a contract initialized to a proxy address

        :param contract: web3.eth.Contract object initialized with a proxy address
        :return: web3.eth.Contract object initialized with the implementation
        """
        implementation_address = contract.functions.implementation().call()
        return self.get_contract(Web3.toChecksumAddress(implementation_address))

    def is_multicall(self, data: str) -> bool:
        """
        Returns if the transaction data sent as an argument is a multicall aggregate function
        :param data: data input
        :return: True if starts with selector of "aggregate((address,bytes)[])"
        """
        # Web3.keccak(text='aggregate((address,bytes)[])')[:4] == '0x252dba42'
        return data.startswith('0x252dba42')  # aggregate((address,bytes)[]) selector

    def decode_multicall_function(self, contract_address: ChecksumAddress, data: str, abi=None) -> Tuple['ContractFunction', dict, list]:
        """
        Decodes all functions inside a multicall aggregate() function

        :param contract_address: Address of the multicall function
        :param data: data to be decoded
        :param abi: ABI (if None each ABI will be downloaded from block explorer)
        :return: Tuple with ContractFunction of multicall, arguments of multicall, and list of decoded functions
        """
        multicall_abi =[{'constant': False,
                         'inputs': [{'components': [{'name': 'target', 'type': 'address'},
                                                    {'name': 'callData', 'type': 'bytes'}],
                                    'name': 'calls',
                                     'type': 'tuple[]'}],
                         'name': 'aggregate',
                         'outputs': [{'name': 'blockNumber', 'type': 'uint256'},
                                     {'name': 'returnData', 'type': 'bytes[]'}],
                         'payable': False,
                         'stateMutability': 'nonpayable',
                         'type': 'function'}]
        decoded_calls = []
        try:
            multicall_contract = self.get_contract(contract_address, abi=abi)
        except ABINotFoundException:
            multicall_contract = None

        if multicall_contract is None:
            multicall_contract = self.w3.eth.contract(address=contract_address, abi=multicall_abi)
        function, args = multicall_contract.decode_function_input(data)
        if 'calls' in args:
            for call in args['calls']:
                call_address = call[0]
                call_data = call[1]
                try:
                    call_function, call_args = self.decode_function_input(call_address, call_data)
                    function_abi = self.get_abi_by_signature(call_address, call_data, abi=abi)
                    signature = abi_to_signature(function_abi)
                    decoded_calls.append({'to': call_address, 'function': signature, 'args': call_args})
                except Exception as e:
                    decoded_calls.append([None, {'error': str(e)}])
        return function, args, decoded_calls

    def decode_function_input(self, contract_address: ChecksumAddress, data: str, abi=None) -> Tuple['ContractFunction', dict]:
        """
        Decode the function given an address and the function input

        :param contract_address: Address of the contract
        :param data: data to be decoded
        :param abi: ABI (if None each ABI will be downloaded from block explorer)
        :return: web3 ContractFunction and arguments
        """
        contract = self.get_contract(contract_address, abi=abi)
        try:
            function, args = contract.decode_function_input(data)
            return function, args
        except ValueError as e:
            if self.is_proxy(contract):
                contract = self.get_proxy_implementation(contract)
                try:
                    function, args = contract.decode_function_input(data)
                    return function, args
                except ValueError as e:
                    raise FunctionInputDecodeException(f'Cannot decode: {e}')
            else:
                raise FunctionInputDecodeException(f'Cannot decode: {e}')

    def get_abi_by_signature(self, contract_address: ChecksumAddress, data: str, abi=None) -> 'ABIFunction':
        """
        Gets the ABI of the function called given a contract address and the function input data
        :param contract_address: Address of the contract
        :param data: data to be decoded
        :param abi: ABI (if None each ABI will be downloaded from block explorer)
        :return: ABI of the function
        """
        contract = self.get_contract(contract_address, abi=abi)
        return contract.get_function_by_selector(HexBytes(data)[:4]).abi

    def decode_full_function(self, contract_address: ChecksumAddress, data: str, abi=None) -> dict:
        """
        Decode a function given an address and the function input, will check if it is a proxy, multicall, etc

        :param contract_address: Address of the contract
        :param data: data to be decoded
        :param abi: ABI (if None each ABI will be downloaded from block explorer)
        :return: The decoded function
        """
        contract = self.get_contract(contract_address, abi=abi)

        if self.is_proxy(contract):
            contract = self.get_proxy_implementation(contract)
            proxy = True
        else:
            proxy = False

        multicall = False
        decoded_calls = []
        if self.is_multicall(data):
            try:
                function, args, decoded_calls = self.decode_multicall_function(contract.address, data)
                multicall = True
            except (FunctionInputDecodeException, ABINotFoundException) as e:
                return {'error': str(e)}
        else:
            try:
                function, args = self.decode_function_input(contract.address, data, abi=abi)
            except (FunctionInputDecodeException, ABINotFoundException) as e:
                return {'error': str(e)}

        function_abi = self.get_abi_by_signature(contract.address, data, abi=abi)
        signature = abi_to_signature(function_abi)

        decoded_fun = {'to': contract_address, 'function': signature, 'args': args, 'abi': function_abi}

        if proxy:
            decoded_fun['proxy_implementation'] = contract.address

        if multicall:
            decoded_fun['decoded_calls'] = decoded_calls

        return decoded_fun

    def decode_raw_transaction(self, raw_tx: str) -> dict:
        """
        Decodes a raw transaction and present the information in a dictionary. Does not decode function input

        :param raw_tx: transaction data
        :return: dictionary with decoded transaction information
        """
        if not DECODE_RAW_TRANSACTIONS:
            raise RuntimeError('pyethash used by py-evm couldnt be installed on Windows :(')
        decoded_tx = TransactionBuilder().decode(HexBytes(raw_tx))
        transaction = {
            'chain_id': decoded_tx.chain_id,
            'nonce': decoded_tx.nonce,
            'gas': decoded_tx.gas,
            'to': Web3.toChecksumAddress(encode_hex(decoded_tx.to)),
            'from': Web3.toChecksumAddress(encode_hex(decoded_tx.sender)),
            'value': decoded_tx.value,
            'data': encode_hex(decoded_tx.data),
            'r': decoded_tx.r,
            's': decoded_tx.s,
        }

        if decoded_tx.type_id is None or decoded_tx.type_id == 0:
            # Legacy Transaction
            transaction['gas_price'] = decoded_tx.gas_price
            transaction['v'] = decoded_tx.v

        elif decoded_tx.type_id == 2:
            # EIP-1559 Transaction
            transaction['max_fee_per_gas'] = decoded_tx.max_fee_per_gas
            transaction['max_priority_fee_per_gas'] = decoded_tx.max_priority_fee_per_gas
            transaction['access_list'] = decoded_tx.access_list
            transaction['y_parity'] = decoded_tx.y_parity
        return transaction

    def decode_full_raw_transaction(self, raw_tx: str, abi=None):
        """
        Decodes a raw transaction and present the information in a dictionary, decoding function input

        :param raw_tx: transaction data
        :param abi: ABI (if None each ABI will be downloaded from block explorer)
        :return: dictionary with decoded transaction information
        """
        transaction = self.decode_raw_transaction(raw_tx)
        transaction['decoded_function'] = self.decode_full_function(contract_address=transaction['to'],
                                                                    data=transaction['data'],
                                                                    abi=abi)
        return transaction

    def encode_eth_call(self, decoded_function_json: str) -> str:
        """ Like the encode_eth_call function below but using web3 lib instead of eth-abi"""
        decoded_function = json.loads(decoded_function_json)

        abi = decoded_function['abi']
        to = decoded_function['to']
        function_signature = decoded_function['function']
        function_arguments = decoded_function['args']

        contract = self.w3.eth.contract(address=Web3.toChecksumAddress(to), abi=[abi])
        data = contract.get_function_by_signature(function_signature)(**function_arguments).buildTransaction()['data']
        return data


def encode_eth_call(decoded_function_json: str) -> str:
    """
    Received a JSON with the function ABI, to, args and function, and reencodes it

    :param decoded_function_json: JSON data like:
        {
          "to": "0xF0cC626f04F0149F1f4ad3746B2589D6FA198B45",
          "function": "spendableBalanceOf(address)",
          "args": {
            "_holder": "0x6C5930C71b07b9DA314cDC454543FB8BFAbeD4cb"
          },
          "abi": {
            "constant": true,
            "inputs": [
              {
                "name": "_holder",
                "type": "address"
              }
            ],
            "name": "spendableBalanceOf",
            "outputs": [
              {
                "name": "",
                "type": "uint256"
              }
            ],
            "payable": false,
            "stateMutability": "view",
            "type": "function"
          },
          "proxy_implementation": "0xde3A93028F2283cc28756B3674BD657eaFB992f4"
        }
    :return: The encoded data call to send via eth_call
    """
    decoded_function = json.loads(decoded_function_json)

    abi = decoded_function['abi']
    to = decoded_function['to']
    function_signature = decoded_function['function']
    function_arguments = decoded_function['args']

    selector = Web3.keccak(text=function_signature)[:4]
    args_list = []
    types_list = []
    for input in abi['inputs']:
        types_list.append(input['type'])
        args_list.append(function_arguments[input['name']])

    encoded_args = HexBytes(encode_abi(types_list, args_list))
    data = HexBytes(selector + encoded_args).hex()
    return data


def decode_single_abi(type: str, data: str):
    return decode_single(type, HexBytes(data))


def decode_list_abi(types: List[str], data: str):
    return decode_abi(types, HexBytes(data))


def prepare_for_json(o: Any) -> Any:
    if isinstance(o, bytes):
        return encode_hex(o)
    elif isinstance(o, dict):
        for k, v in o.items():
            o[k] = prepare_for_json(v)
        return o
    elif isinstance(o, list):
        return [prepare_for_json(i) for i in o]
    elif isinstance(o, tuple):
        return [prepare_for_json(i) for i in o]
    else:
        return o




