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

# Database setup
DB_URL = "sqlite:///users.db"
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

# Web3 setup
web3 = Web3(Web3.HTTPProvider(CHAINSTACK_NODE_URL))
if not web3.is_connected():
    raise Exception("Failed to connect to Ethereum network")

# Load contract ABI
with open('contracts/contract.abi.json', 'r') as abi_file:
    contract_abi = json.load(abi_file)
contract = web3.eth.contract(address=CONTRACT_ADDRESS, abi=contract_abi)

# Initialize GasTracker
gas_tracker = GasTracker(CHAINSTACK_NODE_URL, FAUCET_ADDRESS, FAUCET_PRIVATE_KEY)

# Define conversation states
(TERMS, PASSWORD, MAIN_MENU, EARN, BUYER, WALLET, DONATE, REGISTER, CLAIM_GAS,
 RECYCLE, CREATE_ERRAND, COMPLETE_ERRAND, REGISTER_BUYER, PROCESS_EWASTE, PAY_FOR_EWASTE) = range(15)


# Helper functions
def get_user(telegram_id):
    """Retrieve user from database."""
    session = Session()
    user = session.query(User).filter_by(telegram_id=str(telegram_id)).first()
    session.close()
    return user


def create_user(telegram_id, wallet_address, private_key):
    """Create a new user in the database."""
    session = Session()
    user = User(telegram_id=str(telegram_id), wallet_address=wallet_address, private_key=private_key)
    session.add(user)
    session.commit()
    session.close()
    return user


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the bot and guide user through registration process."""
    user = get_user(update.effective_user.id)
    if user:
        is_registered = contract.functions.users(user.wallet_address).call()[0]
        if is_registered:
            return await show_main_menu(update, context)

        token_balance = contract.functions.balanceOf(user.wallet_address).call()
        eth_balance = web3.eth.get_balance(user.wallet_address)
        eth_balance = float("{:.4f}".format(web3.from_wei(eth_balance, 'ether')))

        await update.message.reply_text(
            f"Welcome back! 👋\n\n"
            f"Your wallet: `{user.wallet_address}`\n"
            f"KBT balance: `{token_balance}`\n"
            f"ETH balance: `{eth_balance}`\n\n"
            f"Ready to make a difference? Let's get you registered on the blockchain!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⛽ Get Free Gas", callback_data='claim_gas')],
                [InlineKeyboardButton("🔑 Register on Blockchain", callback_data='register')]
            ])
        )
        return REGISTER

    await update.message.reply_text(
        "Welcome to KyumaBlocks - Your E-Waste Recycling Partner! ♻️📱\n\n"
        "Before we start, please review our terms:\n\n"
        "1️⃣ We keep your data safe and secure.\n"
        "2️⃣ You're in charge of your account activities.\n"
        "3️⃣ We respect your privacy.\n\n"
        "Ready to join the eco-friendly revolution?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ I Agree", callback_data='agree')],
            [InlineKeyboardButton("❌ I Disagree", callback_data='disagree')]
        ])
    )
    return TERMS
async def register_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Register the user on the blockchain."""
    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)
    wallet_address = user.wallet_address

    try:
        # Estimate gas for the registration
        gas_estimate = contract.functions.registerUser().estimate_gas({'from': wallet_address})

        # Ensure sufficient gas
        if not gas_tracker.ensure_sufficient_gas(wallet_address, gas_estimate):
            await query.edit_message_text(
                "Oops! You don't have enough gas for registration. Let's get you some first.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⛽ Get Free Gas", callback_data='claim_gas')]
                ])
            )
            return REGISTER

        # Proceed with registration
        nonce = web3.eth.get_transaction_count(wallet_address)
        chain_id = web3.eth.chain_id

        transaction = contract.functions.registerUser().build_transaction({
            'chainId': chain_id,
            'gas': int(gas_estimate * 1.2),  # Add 20% buffer
            'gasPrice': web3.eth.gas_price,
            'nonce': nonce,
        })

        signed_txn = web3.eth.account.sign_transaction(transaction, private_key=user.private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_txn.rawTransaction)
        tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        if tx_receipt['status'] == 1:
            await query.edit_message_text(
                "🎉 Congratulations! You're now registered on the blockchain.\n\n"
                "Welcome to KyumaBlocks! Let's start making a difference together."
            )
            return await show_main_menu(update, context)
        else:
            raise Exception("Transaction failed")

    except Exception as e:
        logger.error(f"Error in register_user: {str(e)}")
        await query.edit_message_text(
            f"Oops! Registration didn't work out: {str(e)}\n\n"
            "Let's try again later.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Main Menu", callback_data='main_menu')]
            ])
        )
        return MAIN_MENU


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display the main menu with all available options."""
    keyboard = [
        [InlineKeyboardButton("💰 Earn & Recycle", callback_data='earn')],
        [InlineKeyboardButton("🛒 Buyer Zone", callback_data='buyer')],
        [InlineKeyboardButton("👛 My Wallet", callback_data='wallet')],
        [InlineKeyboardButton("🎁 Donate", callback_data='donate')],
        [InlineKeyboardButton("📊 My Impact", callback_data='my_stats')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = "🏠 Main Menu - What would you like to do today?"

    if update.message:
        await update.message.reply_text(message, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    else:
        user_id = update.effective_user.id if update.effective_user else context.user_data.get('user_id')
        await context.bot.send_message(chat_id=user_id, text=message, reply_markup=reply_markup)

    return MAIN_MENU


async def earn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the Earn & Recycle menu options."""
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("♻️ Recycle E-Waste", callback_data='recycle')],
        [InlineKeyboardButton("📋 Create Task", callback_data='create_errand')],
        [InlineKeyboardButton("📜 Available Tasks", callback_data='list_errands')],
        [InlineKeyboardButton("✅ Complete Task", callback_data='complete_errand')],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("💰 Earn & Recycle - Choose an option:", reply_markup=reply_markup)
    return EARN


async def buyer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the Buyer Zone menu options."""
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("📝 Register as Buyer", callback_data='register_buyer')],
        [InlineKeyboardButton("🔍 Process E-Waste", callback_data='process_ewaste')],
        [InlineKeyboardButton("💳 Pay for E-Waste", callback_data='pay_for_ewaste')],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("🛒 Buyer Zone - What would you like to do?", reply_markup=reply_markup)
    return BUYER


async def recycle_ewaste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guide user through the e-waste recycling process."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Let's recycle some e-waste! 🌱♻️\n\n"
        "Please tell me about the e-waste you want to recycle.\n"
        "Format: description, weight in kg\n\n"
        "Example: Old smartphone, 0.2"
    )
    return RECYCLE


async def process_recycle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the e-waste recycling request."""
    user = get_user(update.effective_user.id)
    try:
        description, weight = update.message.text.split(',')
        weight = float(weight.strip())

        tx = contract.functions.recycleEWaste(description, int(weight * 1000)).build_transaction({
            'from': user.wallet_address,
            'nonce': web3.eth.get_transaction_count(user.wallet_address),
        })
        signed_tx = web3.eth.account.sign_transaction(tx, user.private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            await update.message.reply_text(
                f"🎉 Success! You've recycled {weight}kg of e-waste.\n"
                f"Description: {description}\n\n"
                f"Thank you for making a difference! 🌍"
            )
        else:
            await update.message.reply_text("Oops! The recycling process didn't work. Please try again.")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")
    finally:
        return await show_main_menu(update, context)


async def create_errand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guide user through creating a new task (errand)."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Let's create a new task! 📝\n\n"
        "Please provide a description of the task and the reward amount.\n"
        "Format: description, reward in KBT tokens\n\n"
        "Example: Collect e-waste from local school, 50"
    )
    return CREATE_ERRAND


async def process_create_errand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the task (errand) creation request."""
    user = get_user(update.effective_user.id)
    try:
        description, reward = update.message.text.split(',')
        reward = int(reward.strip())

        user_balance = contract.functions.balanceOf(user.wallet_address).call()
        if user_balance < reward:
            await update.message.reply_text(f"Oops! You don't have enough tokens. Your balance: {user_balance} KBT")
            return await show_main_menu(update, context)

        tx = contract.functions.createErrand(description, reward).build_transaction({
            'from': user.wallet_address,
            'nonce': web3.eth.get_transaction_count(user.wallet_address),
        })
        signed_tx = web3.eth.account.sign_transaction(tx, user.private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            errand_created_event = contract.events.ErrandCreated().process_receipt(receipt)
            if errand_created_event:
                errand_id = errand_created_event[0]['args']['id']
                await update.message.reply_text(
                    f"🎉 Task created successfully!\n\n"
                    f"📌 Task ID: {errand_id}\n"
                    f"💰 Reward: {reward} KBT\n"
                    f"📝 Description: {description}\n\n"
                    f"Someone can now complete this task to earn the reward."
                )
            else:
                await update.message.reply_text(
                    f"✅ Task created successfully, but we couldn't retrieve the ID.\n"
                    f"💰 Reward: {reward} KBT\n"
                    f"📝 Description: {description}"
                )
        else:
            await update.message.reply_text("Oops! Task creation failed. Please try again.")
    except ValueError as ve:
        await update.message.reply_text(f"Invalid input: {str(ve)}\nPlease use the format: description, reward")
    except Exception as e:
        logging.error(f"Error in process_create_errand: {str(e)}")
        await update.message.reply_text(f"An error occurred: {str(e)}")
    finally:
        return await show_main_menu(update, context)


async def list_errands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display a list of available tasks (errands)."""
    query = update.callback_query
    await query.answer()

    try:
        total_errands = contract.functions.getErrandCount().call()
        available_errands = []

        for i in range(total_errands):
            errand = contract.functions.errands(i).call()
            if not errand[4]:  # If not completed
                available_errands.append({
                    'id': i,
                    'description': errand[2],
                    'reward': errand[3]
                })

        if available_errands:
            errand_list = "📋 Available Tasks:\n\n"
            for errand in available_errands:
                errand_list += f"🔢 ID: {errand['id']}\n📝 Task: {errand['description']}\n💰 Reward: {errand['reward']} KBT\n\n"

            await query.edit_message_text(
                errand_list,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back to Earn Menu", callback_data='earn')]
                ])
            )
        else:
            await query.edit_message_text(
                "No tasks available at the moment. Why not create one? 😊",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back to Earn Menu", callback_data='earn')]
                ])
            )
    except Exception as e:
        await query.edit_message_text(
            f"Oops! We couldn't fetch the tasks: {str(e)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Earn Menu", callback_data='earn')]
            ])
        )
        return EARN

async def complete_errand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guide user through completing a task (errand)."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Ready to complete a task? Great! 🎉\n\n"
        "Please enter the ID of the task you've completed."
    )
    return COMPLETE_ERRAND

async def process_complete_errand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the task (errand) completion request."""
    user = get_user(update.effective_user.id)
    try:
        errand_id = int(update.message.text)

        errand = contract.functions.errands(errand_id).call()
        if not errand[0]:
            raise ValueError("This task doesn't exist. Double-check the ID and try again.")
        if errand[4]:
            raise ValueError("This task has already been completed. Try another one!")

        tx = contract.functions.completeErrand(errand_id).build_transaction({
            'from': user.wallet_address,
            'nonce': web3.eth.get_transaction_count(user.wallet_address),
            'gas': 200000,
            'gasPrice': web3.eth.gas_price
        })
        signed_tx = web3.eth.account.sign_transaction(tx, user.private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            reward = errand[3]
            await update.message.reply_text(
                f"🎉 Congratulations! You've completed task {errand_id}.\n"
                f"💰 You've earned {reward} KBT tokens!\n\n"
                f"Keep up the great work! 👏"
            )
        else:
            await update.message.reply_text("Oops! Something went wrong. Please try again.")
    except ValueError as ve:
        await update.message.reply_text(str(ve))
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")
    finally:
        return await show_main_menu(update, context)

async def register_buyer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guide user through the buyer registration process."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Let's get you registered as a buyer! 🛒\n\n"
        "Please provide your name, location, and any additional info.\n"
        "Format: name, location, additional info\n\n"
        "Example: John Doe, New York, Interested in smartphones"
    )
    return REGISTER_BUYER

async def process_register_buyer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the buyer registration request."""
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
            await update.message.reply_text(
                f"🎉 Congratulations, {name.strip()}!\n\n"
                f"You're now registered as a buyer. Welcome aboard! 🚀\n"
                f"You can now process e-waste and contribute to our circular economy."
            )
        else:
            await update.message.reply_text("Oops! Registration failed. Please try again.")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")
    finally:
        return await show_main_menu(update, context)

async def process_ewaste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guide buyer through processing e-waste."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Ready to process some e-waste? Great! 🔧\n\n"
        "Please enter the ID of the e-waste you want to process."
    )
    return PROCESS_EWASTE

async def process_process_ewaste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the e-waste processing request."""
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
            await update.message.reply_text(
                f"✅ E-waste with ID {ewaste_id} has been processed successfully!\n\n"
                f"Thank you for contributing to a cleaner environment. 🌿"
            )
        else:
            await update.message.reply_text("Oops! Processing failed. Please try again.")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")
    finally:
        return await show_main_menu(update, context)

async def pay_for_ewaste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guide buyer through paying for e-waste."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Time to pay for e-waste! 💳\n\n"
        "Please enter the recycler's address and the amount you want to pay.\n"
        "Format: address, amount\n\n"
        "Example: 0x1234...5678, 100"
    )
    return PAY_FOR_EWASTE

async def process_pay_for_ewaste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the payment for e-waste."""
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
            await update.message.reply_text(
                f"✅ Payment successful!\n\n"
                f"You've paid {amount} KBT to {recycler_address.strip()}.\n"
                f"Thank you for supporting our recyclers! 🌟"
            )
        else:
            await update.message.reply_text("Oops! Payment failed. Please try again.")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")
    finally:
        return await show_main_menu(update, context)

async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display user's statistics and impact."""
    query = update.callback_query
    await query.answer()
    user = get_user(query.from_user.id)

    try:
        reputation = contract.functions.getUserReputation(user.wallet_address).call()
        recycled_amount = contract.functions.getUserRecycledAmount(user.wallet_address).call()
        token_balance = contract.functions.balanceOf(user.wallet_address).call()

        stats_message = (
            f"📊 Your Impact Stats:\n\n"
            f"🌟 Reputation: {reputation}\n"
            f"♻️ Total Recycled: {recycled_amount / 1000:.2f} kg\n"
            f"💰 KBT Balance: {token_balance} KBT\n\n"
            f"Wow! You're making a real difference. Keep it up! 🌍👏"
        )

        await query.edit_message_text(
            stats_message,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data='main_menu')]])
        )
    except Exception as e:
        await query.edit_message_text(
            f"Oops! We couldn't fetch your stats: {str(e)}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data='main_menu')]])
        )
    return MAIN_MENU

async def wallet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle wallet-related operations."""
    query = update.callback_query
    await query.answer()
    user = get_user(query.from_user.id)
    balance = contract.functions.balanceOf(user.wallet_address).call()
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Balance", callback_data='refresh_balance')],
        [InlineKeyboardButton("💸 Transfer Tokens", callback_data='transfer_tokens')],
        [InlineKeyboardButton("⛽ Get Free Gas", callback_data='claim_gas')],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"👛 Wallet Menu\n\n"
        f"Current balance: {balance} KBT\n\n"
        f"What would you like to do?",
        reply_markup=reply_markup
    )
    return WALLET

async def transfer_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guide user through token transfer process."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Let's transfer some tokens! 💸\n\n"
        "Please enter the recipient's address and the amount to transfer.\n"
        "Format: address, amount\n\n"
        "Example: 0x1234...5678, 100"
    )
    return WALLET

async def process_transfer_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the token transfer request."""
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
            await update.message.reply_text(
                f"✅ Transfer successful!\n\n"
                f"You've sent {amount} KBT to {recipient.strip()}.\n"
                f"Transaction hash: {tx_hash.hex()}"
            )
        else:
            await update.message.reply_text("Oops! Transfer failed. Please try again.")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")
    finally:
        return await wallet_handler(update, context)

async def donate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle donation process."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("💖 Donate to Project", callback_data='donate_project')],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🎁 Donation Menu\n\n"
        "Your support helps us continue our mission of responsible e-waste management.\n"
        "Every token counts! What would you like to do?",
        reply_markup=reply_markup
    )
    return DONATE

async def donate_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guide user through the donation process."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "You're amazing for wanting to donate! 💖\n\n"
        "Please enter the amount of KBT tokens you'd like to donate to the project."
    )
    return DONATE

async def process_donate_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the donation request."""
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
            await update.message.reply_text(
                f"🎉 Thank you for your generous donation of {amount} KBT!\n\n"
                f"Your support means the world to us and helps create a cleaner future. 🌍"
            )
        else:
            await update.message.reply_text("Oops! The donation didn't go through. Please try again.")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {str(e)}")
    finally:
        return await show_main_menu(update, context)

async def terms_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user's response to terms and conditions."""
    query = update.callback_query
    await query.answer()

    if query.data == 'agree':
        user = get_user(update.effective_user.id)
        if not user:
            account = web3.eth.account.create()
            context.user_data['wallet'] = account.address
            create_user(update.effective_user.id, account.address, account.key.hex())

        await query.edit_message_text(
            f"🎉 Welcome aboard! Your wallet is ready.\n\n"
            f"🔐 Wallet address: `{context.user_data['wallet']}`\n\n"
            f"Let's get you started on your eco-friendly journey!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⛽ Get Free Gas", callback_data='claim_gas')],
                [InlineKeyboardButton("🔑 Register on Blockchain", callback_data='register')]
            ])
        )
        return REGISTER
    else:
        await query.edit_message_text(
            "We're sorry to see you go. 😔\n"
            "If you change your mind about joining our eco-friendly community, feel free to start over!"
        )
        return ConversationHandler.END

async def set_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set user's password."""
    password = update.message.text
    user_id = update.effective_user.id

    try:
        session = Session()
        user = session.query(User).filter_by(telegram_id=str(user_id)).first()
        user.password = password
        session.commit()
        session.close()

        await update.message.reply_text(
            "🎊 Password set successfully!\n\n"
            "🔐 Keep your password safe and secure.\n"
            "🌟 You're all set to start your e-waste recycling journey!"
        )
        return await show_main_menu(update, context)
    except Exception as e:
        logger.error(f"Error in set_password: {e}")
        await update.message.reply_text(f"Oops! We couldn't save your password: {str(e)}")
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation and return to main menu."""
    await update.message.reply_text('Operation cancelled. Returning to the main menu.')
    return await show_main_menu(update, context)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses."""
    query = update.callback_query
    await query.answer()

    handlers = {
        'earn': earn_handler,
        'buyer': buyer_handler,
        'wallet': wallet_handler,
        'donate': donate_handler,
        'recycle': recycle_ewaste,
        'create_errand': create_errand,
        'complete_errand': complete_errand,
        'my_stats': my_stats,
        'main_menu': show_main_menu,
        'list_errands': list_errands,
        'claim_gas': claim_gas,
    }

    handler = handlers.get(query.data)
    if handler:
        return await handler(update, context)
    else:
        await query.edit_message_text(text=f"Sorry, I didn't understand that command.")
        return MAIN_MENU

async def handle_invalid_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle invalid user input."""
    await update.message.reply_text(
        "I didn't quite catch that. Let's head back to the main menu.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data='main_menu')]
        ])
    )
    return MAIN_MENU

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors and exceptions."""
    logger.error(f"Error: {context.error}")
    try:
        if update.effective_message:
            await update.effective_message.reply_text(
                "Oops! Something went wrong. Let's go back to the main menu.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back to Main Menu", callback_data='main_menu')]
                ])
            )
        return MAIN_MENU
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

async def claim_gas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle gas claiming process."""
    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)
    result = gas_tracker.send_gas(user.wallet_address)

    if result:
        await query.edit_message_text(
            f"🎉 Gas claimed successfully!\n\n"
            f"Transaction hash: `{result}`\n\n"
            f"You're now ready to register on the blockchain.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔑 Register on Blockchain", callback_data='register')]
            ])
        )
    else:
        await query.edit_message_text(
            "Oops! We couldn't send you gas right now. Please try again later.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Try Again", callback_data='claim_gas')],
                [InlineKeyboardButton("🔙 Back to Main Menu", callback_data='main_menu')]
            ])
        )
    return REGISTER

def main():
    """Set up and run the bot."""
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            TERMS: [CallbackQueryHandler(terms_response)],
            REGISTER: [CallbackQueryHandler(register_user)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_password)],
            MAIN_MENU: [CallbackQueryHandler(button)],
            EARN: [CallbackQueryHandler(button)],
            BUYER: [CallbackQueryHandler(button)],
            WALLET: [
                CallbackQueryHandler(button),
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_transfer_tokens)
            ],
            DONATE: [
                CallbackQueryHandler(button),
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_donate_project)
            ],
            RECYCLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_recycle)],
            CREATE_ERRAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_create_errand)],
            COMPLETE_ERRAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_complete_errand)],
            REGISTER_BUYER: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_register_buyer)],
            PROCESS_EWASTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_process_ewaste)],
            PAY_FOR_EWASTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_pay_for_ewaste)],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CommandHandler('menu', show_main_menu),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_invalid_input),
            CallbackQueryHandler(button),
        ],
    )

    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)

    application.run_polling()

if __name__ == '__main__':
    main()