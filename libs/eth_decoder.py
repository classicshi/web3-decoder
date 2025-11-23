import eth_decoder.bootstrap
import json
import os
import traceback

from web3 import Web3
from eth_decoder import EtherscanAPI
from eth_decoder.decoder import decode_single_abi, decode_list_abi, EthereumDecoder, prepare_for_json, encode_eth_call


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--chain', type=int, default=1,
                        help='Chain ID, Default: 1 (Ethereum Mainnet)')
    parser.add_argument('--abi', default=None,
                        help='ABI in JSON format. If not provided it will be obtained from Etherscan if available')
    parser.add_argument('--provider',
                        help='Web3 HTTP Provider')
    parser.add_argument('--api_key', default='',
                        help='Blockchain Explorer API Key. If not provided ratelimit to 1req/5s')

    subparsers = parser.add_subparsers(dest='command', help='Commands')
    call_parser = subparsers.add_parser("decode_function_input", help='Decode function input from eth_call')
    call_parser.add_argument('address', help='Contract Address')
    call_parser.add_argument('data', help='Hexadecimal string of RLP encoded data')

    single_parser = subparsers.add_parser("decode_single", help='Decode ABI type single')
    single_parser.add_argument('type', help='Type of data. e.g. "uint256[]"')
    single_parser.add_argument('data', help='Hexadecimal string of RLP encoded data')

    abi_parser = subparsers.add_parser("decode_abi", help='Decode ABI type list')
    abi_parser.add_argument('types', help='Type of data. String in JSON format e.g. ["address","uint256[]"]')
    abi_parser.add_argument('data', help='Hexadecimal string of RLP encoded data')

    raw_parser = subparsers.add_parser("decode_raw_transaction", help='Decode ABI type list')
    raw_parser.add_argument('raw', help='Hexadecimal string of raw transaction')

    encode_parser = subparsers.add_parser("encode_function_input", help='Encode function input of contract')
    encode_parser.add_argument('json_data', help='JSON string with the transaction details')

    args = parser.parse_args()
    try:
        if args.command == 'decode_function_input':
            if args.provider is None or args.provider == '':
                args.provider = os.getenv('WEB3_PROVIDER_URI')
            w3 = Web3(Web3.HTTPProvider(args.provider))
            etherscan_api = EtherscanAPI(chain_id=args.chain, api_key=args.api_key)
            decoder = EthereumDecoder(w3=w3, etherscan_api=etherscan_api)
            decoded_fun = decoder.decode_full_function(contract_address=Web3.toChecksumAddress(args.address),
                                                       data=args.data, abi=args.abi)
            # print(decoded_fun)
            print(json.dumps(prepare_for_json(decoded_fun), indent=2))

        elif args.command == 'decode_single':
            print(json.dumps(prepare_for_json(decode_single_abi(args.type, args.data)), indent=2))

        elif args.command == 'decode_abi':
            types = json.loads(args.types)
            print(json.dumps(prepare_for_json(decode_list_abi(types, args.data)), indent=2))

        elif args.command == 'decode_raw_transaction':
            if args.provider is None or args.provider == '':
                args.provider = os.getenv('WEB3_PROVIDER_URI')
            w3 = Web3(Web3.HTTPProvider(args.provider))
            etherscan_api = EtherscanAPI(chain_id=args.chain, api_key=args.api_key)
            decoder = EthereumDecoder(w3=w3, etherscan_api=etherscan_api)
            decoded_fun = decoder.decode_full_raw_transaction(raw_tx=args.raw, abi=args.abi)
            print(json.dumps(prepare_for_json(decoded_fun), indent=2))

        elif args.command == 'encode_function_input':
            data = encode_eth_call(args.json_data)
            print(json.dumps({'data': data}))

    except Exception as e:
        print(json.dumps({'error': str(e), 'stacktrace': traceback.format_exc()}, indent=2))


if __name__ == '__main__':
    main()
