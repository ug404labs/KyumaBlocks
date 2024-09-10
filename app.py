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

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
provider_url = os.getenv('BASE_PROVIDER_URL')
key = os.getenv('INFURA_API_KEY')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CONTRACT_ADDRESS = os.getenv('CONTRACT_ADDRESS')

# Use SQLite
DB_URL = "sqlite:///users.db"

# Base setup
w3 = Web3(Web3.HTTPProvider(f"{provider_url}{key}"))

# Load contract ABI
try:
    with open('contracts/contract.abi.json', 'r') as abi_file:
        contract_abi = json.load(abi_file)
    contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=contract_abi)
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
    password = Column(String)  # Added password field


engine = create_engine(DB_URL)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Bot states
TERMS, PASSWORD, MAIN_MENU, EARN, BUYER, WALLET, DONATE = range(7)


# Helper functions
def get_user(telegram_id):
    session = Session()
    user = session.query(User).filter_by(telegram_id=str(telegram_id)).first()
    session.close()
    return user


def create_user(telegram_id, wallet_address, password):
    session = Session()
    user = User(telegram_id=str(telegram_id), wallet_address=wallet_address, password=password)
    session.add(user)
    session.commit()
    session.close()
    return user


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if user:
        return await show_main_menu(update, context)

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


async def terms_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'agree':
        account = w3.eth.account.create()
        context.user_data['wallet'] = account.address
        await query.edit_message_text(
            f'🎉 Great! Your wallet has been created.\n\n'
            f'🔐 Wallet address: `{account.address}`\n\n'
            f'Now, let\'s secure your account. Please create a strong password:'
        )
        return PASSWORD
    else:
        await query.edit_message_text('😔 We\'re sorry to see you go. You need to agree to use this system.')
        return ConversationHandler.END


async def set_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text
    wallet_address = context.user_data['wallet']
    user_id = update.effective_user.id

    try:
        tx_hash = contract.functions.registerUser(user_id, wallet_address).transact({'from': w3.eth.accounts[0]})
        w3.eth.wait_for_transaction_receipt(tx_hash)
        create_user(user_id, wallet_address, password)

        await update.message.reply_text(
            '🎊 Congratulations! You have been registered successfully!\n\n'
            '🔑 Your account is now set up and ready to use.\n'
            '🔐 Remember to keep your password safe and never share it with anyone.\n'
            '🌟 Enjoy using our E-Waste Recycling System!'
        )
        return await show_main_menu(update, context)
    except Exception as e:
        logger.error(f"Error in set_password: {e}")
        await update.message.reply_text(f'❌ Registration failed: {str(e)}')
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