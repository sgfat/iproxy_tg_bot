import asyncio
import logging
import os
import sys
from http import HTTPStatus
from logging.handlers import RotatingFileHandler
from typing import Dict, List

import requests
import telegram
import telegram.error
from telegram import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, CallbackContext, Application, ContextTypes, ApplicationBuilder, \
    CallbackQueryHandler
from dotenv import load_dotenv

from exceptions import NoAPIAnswerError, BotSendMessageError, JSONError, APIRequestError

load_dotenv()

IPROXY_TOKEN = os.getenv('IP_TOKEN')
TELEGRAM_TOKEN = os.getenv('TG_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TG_CHAT')

RETRY_PERIOD = 1800
ENDPOINT = 'https://api.iproxy.online/v1/connections?with_statuses=1'
HEADERS = {'Authorization': f'{IPROXY_TOKEN}'}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
fileHandler = RotatingFileHandler(
    'main.log', maxBytes=5000000, backupCount=5
)
streamHandler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    '%(asctime)s, %(levelname)s, %(lineno)d, %(message)s, %(name)s'
)
fileHandler.setFormatter(formatter)
streamHandler.setFormatter(formatter)
logger.addHandler(fileHandler)
logger.addHandler(streamHandler)

interrupt_event = asyncio.Event()

def check_tokens():
    """Checking main tokens."""
    logger.debug('Checking tokens')
    tokens = {
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'IPROXY_TOKEN': IPROXY_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }
    for token, token_value in tokens.items():
        if token_value is None:
            logger.critical(f"Can't find token:{token}")
            return False
    logger.debug('All tokens OK')
    return True


async def send_message(bot, message, **kwargs):
    """Send message to Telegram."""
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, **kwargs)
    except telegram.error.TelegramError as error:
        raise BotSendMessageError(f'Send message failure: {error}') from error
    else:
        logger.debug(f'Bot send message: "{message}"')


def get_api_answer():
    """Sending request to API."""
    logger.debug('Sending request to API')
    requests_params = {'url': ENDPOINT, 'headers': HEADERS}
    try:
        response = requests.get(**requests_params)
    except Exception as error:
        raise APIRequestError(f'Error with request to API: {error}') from error
    else:
        if response.status_code != HTTPStatus.OK:
            raise NoAPIAnswerError(
                "Can't get response from API."
                f'Error code: {response.status_code}')
        logger.debug('Get response from API')
    try:
        return response.json()
    except Exception as error:
        raise JSONError(f'Error with JSON: {error}') from error


def check_response(response: Dict[str, List]) -> List:
    """Checking response from API."""
    logger.debug('Checking response from API')
    if not isinstance(response, dict):
        raise TypeError('Response is not Dict type.')
    if 'result' not in response:
        raise KeyError('No key "result" in response.')
    if not isinstance(response['result'], list):
        raise TypeError('Response["result"] is not List type.')
    if not response['result']:
        raise ValueError('Response["result"] is empty.')
    return response['result']


def parse_status(data: List[Dict]) -> List:
    """Parsing online keys from response."""
    logger.debug('Parsing status of devices')
    devices = []
    for item in data:
        online = item.get('online', None)
        if online is None:
            logger.error(f'No key "online" in item: {item["name"]}')
            continue
        if not online:
            logger.info('Device offline')
            devices.append(item['name'])
    return devices


def parse_ips(data: List[Dict]) -> Dict:
    """Parsing ips from response."""
    logger.debug('Parsing ips')
    current_ips = {}
    for item in data:
        current_ips[item['id']] = item.get('externalIp', None)
        if current_ips[item['id']] is None:
            logger.error(f'No key "externalIp" in item: {item["name"]}')
            continue
    return current_ips


async def check_devices(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    logger.debug('check_devices started')
    last_ips = {}
    await send_message(context.bot, 'Checking devices started')
    # await update.message.reply_text('Checking devices started!')
    while True:
        try:
            response = get_api_answer()
            data = check_response(response)

            if statuses := parse_status(data):
                await send_message(context.bot, f'Offline devices: {statuses}')
            else:
                logger.debug('All devices online')

            current_ips = parse_ips(data)
            for device_id in current_ips:
                if current_ips[device_id] is None:
                    continue
                if last_ips.get(
                        device_id, device_id) == current_ips[device_id]:
                    await send_message(
                        context.bot, f'IP not changed on device: {device_id}')
                    logger.debug(f'IP not changed: {device_id}')
                else:
                    last_ips[device_id] = current_ips[device_id]
            logger.debug('IPs checked')

        except BotSendMessageError as error:
            logger.debug(f'Send message failure: {error}')
        except Exception as error:
            logger.error(error)
            message = f'Error in program: {error}'
            await send_message(context.bot, message)
        finally:
            logger.debug('Sleeping')
            interrupt_future = asyncio.create_task(interrupt_event.wait())
            sleep_future = asyncio.sleep(1800)
            done, pending = await asyncio.wait(
                [interrupt_future, sleep_future], return_when=asyncio.FIRST_COMPLETED
            )
            interrupt_future.cancel()  # Отменить задачу ожидания сигнала прерывания

            if interrupt_future in done:
                interrupt_event.clear()
            continue


async def start_check_devices(update, context):
    asyncio.ensure_future(check_devices(update, context))
    # application = context.bot
    # asyncio.create_task(check_devices(update, context))


async def manual_check(update, context, interrupt_future):
    interrupt_future.set()
    logger.debug('Manual command received')
    await send_message(context.bot, 'Manual command received', disable_notification=True)


async def start(update, context):
    reply_markup = ReplyKeyboardMarkup([
        [KeyboardButton('/start_check_devices'), KeyboardButton('/manual')]
    ], input_field_placeholder='Выберите опцию:', one_time_keyboard=True)
    await update.message.reply_text('Выберите опцию:', reply_markup=reply_markup)


def main():
    """Start bot."""
    if not check_tokens():
        sys.exit("Program interrupted! Can't find tokens.")

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('start_check_devices', start_check_devices))
    application.add_handler(CommandHandler('manual', manual_check))

    application.run_polling()

    logger.debug('Bot started')



if __name__ == '__main__':
    asyncio.run(main())
