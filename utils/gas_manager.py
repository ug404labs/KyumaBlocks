import logging
from web3 import Web3
from web3.exceptions import TransactionNotFound

class GasTracker:
    def __init__(self, CHAINSTACK_NODE_URL, faucet_address, faucet_private_key):
        self.web3 = Web3(Web3.HTTPProvider(CHAINSTACK_NODE_URL))
        self.faucet_address = faucet_address
        self.faucet_private_key = faucet_private_key
        if self.web3.is_connected():
            logging.info("Connected to Ethereum network")
            self.chain_id = self.web3.eth.chain_id
            logging.info(f"Chain ID: {self.chain_id}")
        else:
            logging.error("Failed to connect to Ethereum network")
            raise Exception("Failed to connect to Ethereum network")

        # ETH to USD conversion rate (you should update this regularly in a real-world scenario)
        self.eth_to_usd = 3000  # 1 ETH = $3000 USD (example value)

    def send_gas(self, to_address):
        """Sends approximately $0.5 worth of ETH for gas fees from the faucet address."""
        try:
            # Calculate 0.5 USD worth of ETH
            gas_amount_eth = 0.5 / self.eth_to_usd
            gas_amount_wei = self.web3.to_wei(gas_amount_eth, 'ether')

            # Check faucet balance
            faucet_balance = self.web3.eth.get_balance(self.faucet_address)
            if faucet_balance < gas_amount_wei:
                logging.error(f"Insufficient faucet balance. Need {gas_amount_eth} ETH, but only have {self.web3.from_wei(faucet_balance, 'ether')} ETH.")
                return None

            # Get the nonce
            nonce = self.web3.eth.get_transaction_count(self.faucet_address)

            # Estimate gas price
            gas_price = self.web3.eth.gas_price
            gas_limit = 21000  # Standard gas limit for a simple transfer

            # Prepare the transaction
            tx = {
                'nonce': nonce,
                'to': to_address,
                'value': gas_amount_wei,
                'gas': gas_limit,
                'gasPrice': gas_price,
                'chainId': self.chain_id  # Include chainId for EIP-155 compliance
            }

            # Sign the transaction
            signed_tx = self.web3.eth.account.sign_transaction(tx, self.faucet_private_key)

            # Send the transaction
            tx_hash = self.web3.eth.send_raw_transaction(signed_tx.raw_transaction)

            # Wait for the transaction to be mined
            tx_receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)

            logging.info(f"Gas sent successfully. Amount: {gas_amount_eth} ETH. Hash: {tx_hash.hex()}")
            return tx_hash.hex()
        except Exception as e:
            logging.error(f"Error sending gas: {str(e)}")
            return None


    def get_balance(self, address):
        """Returns the ETH balance of the given address."""
        balance_wei = self.web3.eth.get_balance(address)
        return self.web3.from_wei(balance_wei, 'ether')

    def estimate_gas(self, from_address, to_address, data=None):
        """Estimates the gas required for a transaction."""
        try:
            gas_estimate = self.web3.eth.estimate_gas({
                'from': from_address,
                'to': to_address,
                'data': data
            })
            return gas_estimate
        except Exception as e:
            logging.error(f"Error estimating gas: {str(e)}")
            return None

    def ensure_sufficient_gas(self, address, required_gas):
        """Ensures the address has sufficient gas, sending more if needed."""
        balance = self.get_balance(address)
        required_eth = self.web3.from_wei(required_gas * self.web3.eth.gas_price, 'ether')
        if balance < required_eth:
            return self.send_gas(address)
        return True