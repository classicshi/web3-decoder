import json
import logging
import urllib.request
import os
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class ABINotFoundException(Exception):
    pass


class EtherscanAPI:
    ABI_CACHES_DIR = '.abi_caches'

    def __init__(self, chain_id: int, api_key: str = ''):
        """
        :param chain_id: Chain ID, Used to differentiate between Blockchain Explorers
        :param api_key: Etherscan API key. If not provided, there is a rate limit of 1/5 seconds
        """
        self.chain_id = chain_id
        self.api_key = api_key

        self.chains = self._load_chains()
        self.api_keys = self._load_api_keys()

    def _load_chains(self):
        """
        This function expects to find a chains.json file in the "current" folder
        :return:
        """
        with open('chains.json', 'r') as f:
            return json.load(f)

    def _load_api_keys(self):
        with open('.api_keys.json', 'r') as f:
            return json.load(f)

    @lru_cache(maxsize=None)
    def get_abi(self, eth_address: str, cache: bool = True) -> Optional[dict]:
        """
        Obtains the ABI of a verified ETH contract
        :param eth_address: Contract Address
        :param cache: If True, will save/retrieve the ABI to/from disk
        :return: ABI in dict format, ready to use with Web3
        """

        if cache:
            abi = self.get_abi_from_disk(eth_address)
            if abi is not None:
                return abi

        blockchain_explorer = self.get_blockchain_explorer()
        api_key = self.get_api_key()
        url = f"https://{blockchain_explorer}/api?module=contract&action=getabi&address={eth_address}&apikey={api_key}"
        # print(url)
        response = urllib.request.urlopen(
            url
        )
        if response.status == 200:
            content = response.read().decode('utf-8')
            json_resp = json.loads(content)
            if json_resp['status'] == '1':
                abi = json_resp['result']
                if cache:
                    self.save_abi_to_disk(eth_address, abi)
                return abi
            else:
                # logger.warning(f'ABI for {eth_address} not found: {json_resp["result"]}')
                self.get_abi.cache_clear()
                raise ABINotFoundException(f'ABI for {eth_address} not found: {json_resp["result"]}')

        return None

    def get_api_key(self) -> str:
        """ Given a Chain ID, retrieves the API key from an environment variable
         if this API was not initialized with a key
         The key is based on the hostname of the Blockchain explorer:
           api.etherscan.io -> ETHERSCAN_API
           bscscan.com -> BSCSCAN_API
        """
        if len(self.api_key) > 0:
            return self.api_key
        else:
            # Get API key from environment variable based on Chain ID
            blockchain_explorer_name = self.get_blockchain_explorer().split(".")[-2].upper()
            api_key_name = f'{blockchain_explorer_name}_API'
            api_key = os.getenv(api_key_name)
            if api_key is not None:
                return api_key
            else:
                # Get API key from .api_keys.json file
                if api_key_name in self.api_keys:
                    return self.api_keys[api_key_name]

    def get_blockchain_explorer(self) -> str:
        if str(self.chain_id) not in self.chains:
            raise RuntimeError(f'Chain ID not supported: {self.chain_id}')

        return self.chains[str(self.chain_id)]['explorer']

    def _get_abi_path(self, contract_address: str) -> str:
        return os.path.join(self.ABI_CACHES_DIR, f'{self.chain_id}_{contract_address.lower()}.abi')

    def save_abi_to_disk(self, contract_address: str, abi: dict):
        """
        Saves the ABI to disk
        :param contract_address: Contract Address
        :param abi: ABI to save
        :return: None
        """
        self._create_abi_caches_dir()
        # Replace the file
        file_path = self._get_abi_path(contract_address)
        with open(file_path, 'w') as f:
            json.dump(abi, f, indent=2)

    def get_abi_from_disk(self, contract_address: str) -> Optional[dict]:
        """
        Loads ABI from disk if it was saved before
        :param contract_address: adress to lookup
        :return: ABI if it was saved. None otherwise
        """
        file_path = self._get_abi_path(contract_address)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    abi = json.load(f)
                    return abi
            except Exception as e:
                logger.error(f'Error while loading file {file_path}: {e}')
        return None

    def _create_abi_caches_dir(self):
        """ Creates the caches dir if it does not exist """
        if not os.path.exists(self.ABI_CACHES_DIR):
            os.makedirs(self.ABI_CACHES_DIR)
