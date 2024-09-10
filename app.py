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

TERMS, PASSWORD, MAIN_MENU, EARN, BUYER, WALLET, DONATE, REGISTER, CLAIM_GAS, RECYCLE, CREATE_ERRAND, COMPLETE_ERRAND, REGISTER_BUYER, PROCESS_EWASTE, PAY_FOR_EWASTE = range(15)


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if user:
        # Check if user is registered on the blockchain
        is_registered = contract.functions.users(user.wallet_address).call()[0]
        if is_registered:
            return await show_main_menu(update, context)

        token_balance = contract.functions.balanceOf(user.wallet_address).call()
        eth_balance = web3.eth.get_balance(user.wallet_address)
        eth_balance = float("{:.4f}".format(web3.from_wei(eth_balance, 'ether')))

        await update.message.reply_text(
            f'Welcome back! You already have a wallet: `{user.wallet_address}`.\n\n'
            f'Your Kyuma token balance is: `{token_balance}`\n'
            f'Your ETH balance is: `{eth_balance}`\n\n'
            f'Please register on the blockchain to continue.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⛽ Claim Gas", callback_data='claim_gas')],
                [InlineKeyboardButton("🔑 Register on Blockchain", callback_data='register')]
            ])
        )
        return REGISTER

    await update.message.reply_text(
        '👋 Welcome to the E-Waste Recycling Bot! ♻️📱\n\n'
        'Before we begin, please read and agree to our terms and conditions:\n\n'
        '1. Your data will be stored securely.\n'
        '2. You are responsible for your account activities.\n'
        '3. We respect your privacy and will not share your information.\n\n'
        'Do you agree to these terms?',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ I Agree", callback_data='agree')],
            [InlineKeyboardButton("❌ I Disagree", callback_data='disagree')]
        ])
    )
    return TERMS

async def register_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)
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

        # Send the raw transaction
        tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)

        # Wait for the transaction receipt
        tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        # Check if the transaction was successful
        if tx_receipt['status'] == 1:
            await query.edit_message_text(
                f'🎉 You have been registered successfully on the blockchain!\n\n'
                f'Welcome to the E-Waste Recycling System. You can now start using the main features.'
            )
            return await show_main_menu(update, context)
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
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 Earn", callback_data='earn'),
         InlineKeyboardButton("🛒 Buyer", callback_data='buyer')],
        [InlineKeyboardButton("👛 My Wallet", callback_data='wallet'),
         InlineKeyboardButton("🎁 Donate", callback_data='donate')],
        [InlineKeyboardButton("♻️ Recycle E-Waste", callback_data='recycle'),
         InlineKeyboardButton("📋 Create Errand", callback_data='create_errand')],
        [InlineKeyboardButton("✅ Complete Errand", callback_data='complete_errand'),
         InlineKeyboardButton("📊 My Stats", callback_data='my_stats')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = '🏠 Main Menu - Choose an option:'

    if update.message:
        await update.message.reply_text(message, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    else:
        user_id = update.effective_user.id if update.effective_user else context.user_data.get('user_id')
        await context.bot.send_message(chat_id=user_id, text=message, reply_markup=reply_markup)

    return MAIN_MENU


async def main_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await show_main_menu(update, context)


async def earn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("♻️ Recycle E-Waste", callback_data='recycle')],
        [InlineKeyboardButton("📋 Create Errand", callback_data='create_errand')],
        [InlineKeyboardButton("✅ Complete Errand", callback_data='complete_errand')],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("💰 Earn Menu - Choose an option:", reply_markup=reply_markup)
    return EARN


async def buyer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("📝 Register as Buyer", callback_data='register_buyer')],
        [InlineKeyboardButton("🔍 Process E-Waste", callback_data='process_ewaste')],
        [InlineKeyboardButton("💳 Pay for E-Waste", callback_data='pay_for_ewaste')],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("🛒 Buyer Menu - Choose an option:", reply_markup=reply_markup)
    return BUYER


async def recycle_ewaste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Please enter the description and weight of the e-waste you want to recycle.\nFormat: description,weight")
    return RECYCLE


async def process_recycle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    try:
        description, weight = update.message.text.split(',')
        weight = int(weight.strip())

        tx = contract.functions.recycleEWaste(description, weight).build_transaction({
            'from': user.wallet_address,
            'nonce': web3.eth.get_transaction_count(user.wallet_address),
        })
        signed_tx = web3.eth.account.sign_transaction(tx, user.private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            await update.message.reply_text(
                f"Successfully recycled {weight} units of e-waste. Thank you for recycling!")
        else:
            await update.message.reply_text("Transaction failed. Please try again.")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")
    return await show_main_menu(update, context)


async def create_errand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please enter the errand description and reward amount.\nFormat: description,reward")
    return CREATE_ERRAND


async def process_create_errand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    try:
        description, reward = update.message.text.split(',')
        reward = int(reward.strip())

        tx = contract.functions.createErrand(description, reward).build_transaction({
            'from': user.wallet_address,
            'nonce': web3.eth.get_transaction_count(user.wallet_address),
        })
        signed_tx = web3.eth.account.sign_transaction(tx, user.private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            await update.message.reply_text(f"Successfully created an errand with a reward of {reward} tokens.")
        else:
            await update.message.reply_text("Transaction failed. Please try again.")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")
    return await show_main_menu(update, context)


async def complete_errand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please enter the ID of the errand you want to complete.")
    return COMPLETE_ERRAND


async def process_complete_errand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    try:
        errand_id = int(update.message.text)

        tx = contract.functions.completeErrand(errand_id).build_transaction({
            'from': user.wallet_address,
            'nonce': web3.eth.get_transaction_count(user.wallet_address),
        })
        signed_tx = web3.eth.account.sign_transaction(tx, user.private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            await update.message.reply_text(f"Successfully completed errand {errand_id}.")
        else:
            await update.message.reply_text("Transaction failed. Please try again.")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")
    return await show_main_menu(update, context)


async def register_buyer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Please enter your name, location, and additional info to register as a buyer.\nFormat: name,location,additional_info")
    return REGISTER_BUYER


async def process_register_buyer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    try:
        name, location, additional_info = update.message.text.split(',')

        tx = contract.functions.registerBuyer(name.strip(), location.strip(),
                                              additional_info.strip()).build_transaction({
            'from': user.wallet_address,
            'nonce': web3.eth.get_transaction_count(user.wallet_address),
        })
        signed_tx = web3.eth.account.sign_transaction(tx, user.private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            await update.message.reply_text(f"Successfully registered as a buyer.")
        else:
            await update.message.reply_text("Transaction failed. Please try again.")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")
    return await show_main_menu(update, context)


async def process_ewaste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please enter the ID of the e-waste you want to process.")
    return PROCESS_EWASTE




async def process_process_ewaste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    try:
        ewaste_id = int(update.message.text)

        tx = contract.functions.processEWaste(ewaste_id).build_transaction({
            'from': user.wallet_address,
            'nonce': web3.eth.get_transaction_count(user.wallet_address),
        })
        signed_tx = web3.eth.account.sign_transaction(tx, user.private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            await update.message.reply_text(f"Successfully processed e-waste with ID {ewaste_id}.")
        else:
            await update.message.reply_text("Transaction failed. Please try again.")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")
    return await show_main_menu(update, context)


async def pay_for_ewaste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Please enter the recycler's address and the amount you want to pay.\nFormat: address,amount")
    return PAY_FOR_EWASTE


async def process_pay_for_ewaste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    try:
        recycler_address, amount = update.message.text.split(',')
        amount = int(amount.strip())

        tx = contract.functions.payForEWaste(recycler_address.strip(), amount).build_transaction({
            'from': user.wallet_address,
            'nonce': web3.eth.get_transaction_count(user.wallet_address),
        })
        signed_tx = web3.eth.account.sign_transaction(tx, user.private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            await update.message.reply_text(f"Successfully paid {amount} tokens to {recycler_address}.")
        else:
            await update.message.reply_text("Transaction failed. Please try again.")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")
    return await show_main_menu(update, context)


async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = get_user(query.from_user.id)

    try:
        reputation = contract.functions.getUserReputation(user.wallet_address).call()
        recycled_amount = contract.functions.getUserRecycledAmount(user.wallet_address).call()
        token_balance = contract.functions.balanceOf(user.wallet_address).call()

        stats_message = (
            f"🏆 Your Stats:\n\n"
            f"🌟 Reputation: {reputation}\n"
            f"♻️ Total Recycled: {recycled_amount} units\n"
            f"💰 Token Balance: {token_balance} KBT"
        )

        await query.edit_message_text(stats_message, reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data='main_menu')]]))
    except Exception as e:
        await query.edit_message_text(f"An error occurred while fetching your stats: {str(e)}",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data='main_menu')]]))
    return MAIN_MENU


async def wallet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = get_user(query.from_user.id)
    balance = contract.functions.balanceOf(user.wallet_address).call()
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh balance", callback_data='refresh_balance')],
        [InlineKeyboardButton("💸 Transfer tokens", callback_data='transfer_tokens')],
        [InlineKeyboardButton("⛽ Claim gas", callback_data='claim_gas')],
        [InlineKeyboardButton("🔙 Back to main menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=f"👛 Wallet Menu\nCurrent balance: {balance} KBT tokens",
                                  reply_markup=reply_markup)
    return WALLET


async def transfer_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Please enter the recipient's address and the amount of tokens to transfer.\nFormat: address,amount")
    return WALLET


async def process_transfer_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    try:
        recipient, amount = update.message.text.split(',')
        amount = int(amount.strip())

        tx = contract.functions.transfer(recipient.strip(), amount).build_transaction({
            'from': user.wallet_address,
            'nonce': web3.eth.get_transaction_count(user.wallet_address),
        })
        signed_tx = web3.eth.account.sign_transaction(tx, user.private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            await update.message.reply_text(f"Successfully transferred {amount} tokens to {recipient}.")
        else:
            await update.message.reply_text("Transaction failed. Please try again.")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")
    return await wallet_handler(update, context)


async def donate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("💖 Donate to project", callback_data='donate_project')],
        [InlineKeyboardButton("🔙 Back to main menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text="🎁 Donate Menu:", reply_markup=reply_markup)
    return DONATE


async def donate_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please enter the amount of tokens you want to donate to the project.")
    return DONATE


async def process_donate_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    try:
        amount = int(update.message.text)
        project_address = CONTRACT_ADDRESS  # Donate to the contract address

        tx = contract.functions.transfer(project_address, amount).build_transaction({
            'from': user.wallet_address,
            'nonce': web3.eth.get_transaction_count(user.wallet_address),
        })
        signed_tx = web3.eth.account.sign_transaction(tx, user.private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            await update.message.reply_text(f"Thank you for your donation of {amount} tokens to the project!")
        else:
            await update.message.reply_text("Transaction failed. Please try again.")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")
    return await show_main_menu(update, context)
async def terms_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'agree':
        user = get_user(update.effective_user.id)
        if not user:
            account = web3.eth.account.create()
            context.user_data['wallet'] = account.address
            create_user(update.effective_user.id, account.address, account.key)

        await query.edit_message_text(
            f'🎉 Your wallet has been created.\n\n'
            f'🔐 Wallet address: `{context.user_data["wallet"]}`\n\n'
            f'You can claim some gas to get started, or register on the blockchain.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⛽ Claim Gas", callback_data='claim_gas')],
                [InlineKeyboardButton("🔑 Register on Blockchain", callback_data='register')]
            ])
        )
        return REGISTER
    else:
        await query.edit_message_text('😔 We\'re sorry to see you go. You need to agree to use this system.')
        return ConversationHandler.END

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
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('🛑 Operation cancelled. Returning to the main menu.')
    return await show_main_menu(update, context)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'earn':
        return await earn_handler(update, context)
    elif query.data == 'buyer':
        return await buyer_handler(update, context)
    elif query.data == 'wallet':
        return await wallet_handler(update, context)
    elif query.data == 'donate':
        return await donate_handler(update, context)
    elif query.data == 'recycle':
        return await recycle_ewaste(update, context)
    elif query.data == 'create_errand':
        return await create_errand(update, context)
    elif query.data == 'complete_errand':
        return await complete_errand(update, context)
    elif query.data == 'my_stats':
        return await my_stats(update, context)
    elif query.data == 'main_menu':
        return await show_main_menu(update, context)
    else:
        await query.edit_message_text(text=f"Sorry, I didn't understand that command.")
        return MAIN_MENU


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
            WALLET: [
                CallbackQueryHandler(wallet_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_transfer_tokens)
            ],
            DONATE: [
                CallbackQueryHandler(donate_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_donate_project)
            ],
            RECYCLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_recycle)],
            CREATE_ERRAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_create_errand)],
            COMPLETE_ERRAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_complete_errand)],
            REGISTER_BUYER: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_register_buyer)],
            PROCESS_EWASTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_process_ewaste)],
            PAY_FOR_EWASTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_pay_for_ewaste)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('menu', main_menu_command))

    application.run_polling()


if __name__ == '__main__':
    main()