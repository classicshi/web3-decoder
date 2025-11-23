# eth_decoder lib

The eth_decoder library is in charge of most of the work done by the web3 decoder extension. 
You can also use the library from the console, as shown below:

~~~
python libs/eth_decoder.py -h
usage: eth_decoder.py [-h] [-c CHAIN] [--abi ABI] [--api_key API_KEY] {decode_function_input,decode_single,decode_abi,decode_raw_transaction,encode_function_input} ...

positional arguments:
  {decode_function_input,decode_single,decode_abi,decode_raw_transaction,encode_function_input}
                        Commands
    decode_function_input
                        Decode function input from eth_call
    decode_single       Decode ABI type single
    decode_abi          Decode ABI type list
    decode_raw_transaction
                        Decode ABI type list
    encode_function_input
                        Encode function input of contract

options:
  -h, --help            show this help message and exit
  -c CHAIN, --chain CHAIN
                        Chain ID, Default: 1 (Ethereum Mainnet)
  --abi ABI             ABI in JSON format. If not provided it will be obtained from Etherscan if available
  --api_key API_KEY     Blockchain Explorer API Key. If not provided ratelimit to 1req/5s
~~~

## Python Environment Setup to use eth_decoder

There are precompiled packages for Linux, Mac and Windows in the dist folder. 

However, if you want to use directly the python3 library, you may need to do a few extra steps:

## Linux or Mac OS

~~~shell
cd ${WHEREYOUSAVEDTHEEXTENSION}
virtualenv -p python3 venv
source venv/bin/activate
pip install web3 py-evm
~~~

## Windows

1. Download the latest python3 version from:
   https://www.python.org/downloads/
   **DO NOT FORGET checking the "Add Python 3.X to PATH" checkbox!**
2. Download and install the Microsoft C++ Build Tools from: 
   https://visualstudio.microsoft.com/visual-cpp-build-tools/
   Note: You need to check the __"Desktop Development with C++"__ package
3. Open a powershell in the extension folder, and install the python requirements:
   `pip install web3 py-evm`


# DEV: Build standalone executables

From a virtualenv or python3 environment where the extension properly works (see above), 
we used pyinstaller to build the standalone executables:

## Linux

~~~shell
pip install pyinstaller
pyinstaller -n eth_decoder.linux libs/eth_decoder.py
~~~

## Mac OS 

~~~shell
pip install pyinstaller
pyinstaller -n eth_decoder.osx libs/eth_decoder.py
~~~

## Windows

~~~shell
pip install pyinstaller
pyinstaller -n eth_decoder.windows libs/eth_decoder.py
~~~