# E-Waste Recycling Telegram Bot

![E-Waste Recycling Bot Logo](assets/BW.png)

## Overview

The E-Waste Recycling Telegram DApp is a blockchain-based solution designed to incentivize and manage electronic waste recycling. This bot allows users to recycle e-waste, create and complete errands, and participate in a token-based economy built around responsible e-waste management.

## Our Team

- **Nessa**: Our hard-working idea generator and project visionary.
- **Oliseg Gegnesis**: Full-stack developer bringing our ideas to life.
- **Zuka Robinah**: Smart contract developer ensuring our blockchain integration is secure and efficient.

Together, we're committed to making e-waste recycling accessible, rewarding, and impactful.

## Features

- User registration and wallet creation
- E-waste recycling with token rewards
- Errand creation and completion system
- Buyer registration and e-waste processing
- Token transfers and donations
- User statistics tracking

For testing, go to https://t.me/KyumaBlocksBot

## Technologies Used

- Python
- Telegram Bot API
- Web3.py for Ethereum blockchain interaction
- SQLAlchemy for database management
- SQLite as the database

## Prerequisites

- Python 3.7+
- Pip (Python package manager)
- A Telegram Bot Token (obtain from BotFather on Telegram)
- An Ethereum node URL (e.g., Infura, Chainstack)
- A deployed smart contract for the E-Waste Recycling system

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/ug404labs/KyumaBlocks.git 
   cd KyumaBlocks
   ```

2. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

3. Set up your environment variables:
   Create a `.env` file in the root directory with the following content:
   ```
   CONTRACT_ADDRESS=0xC10BFa336871A11c94CA247079a1D5f02960098d
   TELEGRAM_BOT_TOKEN=[get from @botfather on telegram, do new Bot]
   CHAINSTACK_NODE_URL=https://base-sepolia.core.chainstack.com/eb5714d1abf67cbead7ac0c113eaf494
   GAS_WALLET_KEY=290f9c1982d819789f6fba4e7d5686a107bd8d12e745b49775f84f1e207ef128
   FAUCET_ADDRESS=0xd231f75dE9338929Ea8F420Adce359Ae88EF4C74
   FAUCET_PRIVATE_KEY=290f9c1982d819789f6fba4e7d5686a107bd8d12e745b49775f84f1e207ef128
   ```

## Usage

If the faucet is empty, create a wallet account and send Base Sepolia testnet tokens.

Rename `.env.example` to `.env`
Get bot token from BotFather and put it in the `.env` file for the bot token.

To start the bot, run:

```
python app.py
```

It would be cool to use a virtual environment, but it's not required.

Users can interact with the bot on Telegram by searching for your bot's username and starting a conversation.

## Main Commands

- `/start`: Initiates the bot and guides new users through the registration process
- `/menu`: Displays the main menu with all available options

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.

## Acknowledgments

- OpenZeppelin for smart contract libraries
- Telegram for the Bot API
- The Ethereum community for blockchain resources