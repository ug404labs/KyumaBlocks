import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, ConversationHandler, \
    MessageHandler, filters
from web3 import Web3
import json
import logging
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from utils.gas_manager import GasTracker

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CONTRACT_ADDRESS = os.getenv('CONTRACT_ADDRESS')
CHAINSTACK_NODE_URL = os.getenv('CHAINSTACK_NODE_URL')

FAUCET_ADDRESS = os.getenv('FAUCET_ADDRESS')
FAUCET_PRIVATE_KEY = os.getenv('FAUCET_PRIVATE_KEY')

# Use SQLite
DB_URL = "sqlite:///users.db"

# Web3 setup
web3 = Web3(Web3.HTTPProvider(CHAINSTACK_NODE_URL))
if web3.is_connected():
    logger.info("Connected to Ethereum network")
else:
    logger.error("Failed to connect to Ethereum network")
    raise Exception("Failed to connect to Ethereum network")

# Load contract ABI
try:
    with open('contracts/contract.abi.json', 'r') as abi_file:
        contract_abi = json.load(abi_file)
    contract = web3.eth.contract(address=CONTRACT_ADDRESS, abi=contract_abi)
    logger.info(f'Contract loaded: {contract}')
except Exception as e:
    logger.error(f"Error loading contract: {e}")
    raise

# Database setup
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True)
    wallet_address = Column(String)
    balance = Column(Float, default=0.0)
    password = Column(String)
    private_key = Column(String)

engine = create_engine(DB_URL)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


# Initialize GasTracker
gas_tracker = GasTracker(CHAINSTACK_NODE_URL, FAUCET_ADDRESS, FAUCET_PRIVATE_KEY)

# Bot states
TERMS, PASSWORD, MAIN_MENU, EARN, BUYER, WALLET, DONATE, REGISTER, CLAIM_GAS = range(9)

# Helper functions
def get_user(telegram_id):
    session = Session()
    user = session.query(User).filter_by(telegram_id=str(telegram_id)).first()
    session.close()
    return user

def create_user(telegram_id, wallet_address, private_key):
    session = Session()
    user = User(telegram_id=str(telegram_id), wallet_address=wallet_address, private_key=private_key)
    session.add(user)
    session.commit()
    session.close()
    return user

# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user = get_user(update.effective_user.id)
#     if user:
#         token_balance = contract.functions.balanceOf(user.wallet_address).call()
#         eth_balance = web3.eth.get_balance(user.wallet_address)
#         await update.message.reply_text(
#             f'Welcome back! You already have a wallet: `{user.wallet_address}`.\n\n'
#             f'Your Kyuma token balance is: `{token_balance}`\n'
#             f'Your ETH balance is: `{eth_balance}`\n\n'
#             f'Please register on the blockchain to continue.',
#             reply_markup=InlineKeyboardMarkup([
#                 [InlineKeyboardButton("🔑 Register on Blockchain", callback_data='register')]
#             ])
#         )
#         return REGISTER
#
#     await update.message.reply_text(
#         '👋 Welcome to the E-Waste Recycling Bot! ♻️📱\n\n'
#         'Before we begin, please read and agree to our terms and conditions:\n\n'
#         '1. Your data will be stored securely.\n'
#         '2. You are responsible for your account activities.\n'
#         '3. We respect your privacy and will not share your information.\n\n'
#         'Do you agree to these terms?',
#         reply_markup=InlineKeyboardMarkup([
#             [InlineKeyboardButton("✅ I Agree", callback_data='agree')],
#             [InlineKeyboardButton("❌ I Disagree", callback_data='disagree')]
#         ])
#     )
#     return TERMS

async def terms_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'agree':
        user = get_user(update.effective_user.id)
        if not user:
            account = web3.eth.account.create()
            context.user_data['wallet'] = account.address
            create_user(update.effective_user.id, account.address, account.key.hex())

        await query.edit_message_text(
            f'🎉 Your wallet has been created.\n\n'
            f'🔐 Wallet address: `{context.user_data["wallet"]}`\n\n'
            f'Please register on the blockchain to start using the system.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔑 Register on Blockchain", callback_data='register')]
            ])
        )
        return REGISTER
    else:
        await query.edit_message_text('😔 We\'re sorry to see you go. You need to agree to use this system.')
        return ConversationHandler.END
async def register_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = get_user(update.effective_user.id)
    wallet_address = user.wallet_address

    try:
        # Get the nonce and chain ID for the transaction
        nonce = web3.eth.get_transaction_count(wallet_address)
        chain_id = web3.eth.chain_id

        # Build the transaction for registering the user
        transaction = contract.functions.registerUser().build_transaction({
            'chainId': chain_id,
            'gas': 2000000,  # Adjust gas as per your contract requirements
            'gasPrice': web3.eth.gas_price,
            'nonce': nonce,
        })

        # Sign the transaction with the user's private key
        signed_txn = web3.eth.account.sign_transaction(transaction, private_key=user.private_key)

        # Print all attributes of the signed transaction
        logger.info(f"Signed Transaction: {signed_txn}")

        # Send the raw transaction
        tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)

        # Wait for the transaction receipt
        tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        # Check if the transaction was successful
        if tx_receipt['status'] == 1:
            await query.edit_message_text(
                f'🎉 You have been registered successfully on the blockchain!\n\n'
                f'Now, please create a strong password:'
            )
            return PASSWORD
        else:
            raise Exception("Transaction failed")

    except Exception as e:
        logger.error(f"Error in register_user: {e}")
        await query.edit_message_text(
            f'❌ Registration failed: {str(e)}\n\n'
            f'Please make sure your wallet is funded with enough gas and try again.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔑 Try Registering Again", callback_data='register')]
            ])
        )
        return REGISTER


async def set_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text
    user_id = update.effective_user.id

    try:
        session = Session()
        user = session.query(User).filter_by(telegram_id=str(user_id)).first()
        user.password = password
        session.commit()
        session.close()

        await update.message.reply_text(
            '🎊 You have successfully set your password!\n\n'
            '🔑 Remember to keep your password safe.\n'
            '🌟 Enjoy using our E-Waste Recycling System!'
        )
        return await show_main_menu(update, context)
    except Exception as e:
        logger.error(f"Error in set_password: {e}")
        await update.message.reply_text(f'❌ Failed to save your password: {str(e)}')
        return ConversationHandler.END

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 Earn", callback_data='earn'),
         InlineKeyboardButton("🛒 Buyer", callback_data='buyer')],
        [InlineKeyboardButton("👛 My Wallet", callback_data='wallet'),
         InlineKeyboardButton("🎁 Donate", callback_data='donate')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text('🏠 Main Menu - Choose an option:', reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text('🏠 Main Menu - Choose an option:', reply_markup=reply_markup)
    return MAIN_MENU

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'earn':
        keyboard = [
            [InlineKeyboardButton("♻️ Recycle e-waste", callback_data='recycle')],
            [InlineKeyboardButton("🚚 Manage pickups", callback_data='pickups')],
            [InlineKeyboardButton("🔙 Back to main menu", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="💰 Earn Menu:", reply_markup=reply_markup)
        return EARN
    elif query.data == 'buyer':
        keyboard = [
            [InlineKeyboardButton("📢 Post ad", callback_data='post_ad')],
            [InlineKeyboardButton("📋 Manage requests", callback_data='manage_requests')],
            [InlineKeyboardButton("✅ Confirm transaction", callback_data='confirm_transaction')],
            [InlineKeyboardButton("🔙 Back to main menu", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="🛒 Buyer Menu:", reply_markup=reply_markup)
        return BUYER
    elif query.data == 'wallet':
        user = get_user(query.from_user.id)
        balance = contract.functions.balanceOf(user.wallet_address).call()
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh balance", callback_data='refresh_balance')],
            [InlineKeyboardButton("💸 Withdraw", callback_data='withdraw')],
            [InlineKeyboardButton("⛽ Claim gas", callback_data='claim_gas')],
            [InlineKeyboardButton("🔙 Back to main menu", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=f"👛 Wallet Menu\nCurrent balance: {balance} tokens",
                                      reply_markup=reply_markup)
        return WALLET
    elif query.data == 'donate':
        keyboard = [
            [InlineKeyboardButton("💳 Donate credits", callback_data='donate_credits')],
            [InlineKeyboardButton("💰 Donate funds", callback_data='donate_funds')],
            [InlineKeyboardButton("🔙 Back to main menu", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="🎁 Donate Menu:", reply_markup=reply_markup)
        return DONATE
    elif query.data == 'main_menu':
        return await show_main_menu(update, context)

async def earn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'recycle':
        await query.edit_message_text("♻️ Recycling functionality not implemented yet.")
    elif query.data == 'pickups':
        await query.edit_message_text("🚚 Pickup management functionality not implemented yet.")
    return EARN

async def buyer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'post_ad':
        await query.edit_message_text("📢 Ad posting functionality not implemented yet.")
    elif query.data == 'manage_requests':
        await query.edit_message_text("📋 Request management functionality not implemented yet.")
    elif query.data == 'confirm_transaction':
        await query.edit_message_text("✅ Transaction confirmation functionality not implemented yet.")
    return BUYER

async def wallet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'refresh_balance':
        user = get_user(query.from_user.id)
        balance = contract.functions.balanceOf(user.wallet_address).call()
        await query.edit_message_text(f"👛 Updated balance: {balance} tokens")
    elif query.data == 'withdraw':
        await query.edit_message_text("💸 Withdrawal functionality not implemented yet.")
    elif query.data == 'claim_gas':
        await query.edit_message_text("⛽ Gas claiming functionality not implemented yet.")
    return WALLET

async def donate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'donate_credits':
        await query.edit_message_text("💳 Credit donation functionality not implemented yet.")
    elif query.data == 'donate_funds':
        await query.edit_message_text("💰 Fund donation functionality not implemented yet.")
    return DONATE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('🛑 Operation cancelled. Feel free to start over when you\'re ready!')
    return ConversationHandler.END

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            TERMS: [CallbackQueryHandler(terms_response)],
            REGISTER: [CallbackQueryHandler(register_user)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_password)],
            MAIN_MENU: [CallbackQueryHandler(button)],
            EARN: [CallbackQueryHandler(earn_handler)],
            BUYER: [CallbackQueryHandler(buyer_handler)],
            WALLET: [CallbackQueryHandler(wallet_handler)],
            DONATE: [CallbackQueryHandler(donate_handler)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == '__main__':
    main()