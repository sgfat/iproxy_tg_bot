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
from dotenv import load_dotenv
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import CommandHandler, Application, ContextTypes

from exceptions import (NoAPIAnswerError, BotSendMessageError,
                        JSONError, APIRequestError)

load_dotenv()

IPROXY_TOKEN = os.getenv('IP_TOKEN')
TELEGRAM_TOKEN = os.getenv('TG_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TG_CHAT')

RETRY_PERIOD = 1800
ENDPOINT = 'https://api.iproxy.online/v1/connections?with_statuses=1'
HEADERS = {'Authorization': f'{IPROXY_TOKEN}'}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
fileHandler = RotatingFileHandler('main.log', maxBytes=5000000, backupCount=5)
formatter = logging.Formatter(
    '%(asctime)s, %(levelname)s, %(lineno)d, %(message)s, %(name)s'
)
fileHandler.setFormatter(formatter)
logger.addHandler(fileHandler)


def check_tokens() -> bool:
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


async def send_message(bot, message, log=False, **kwargs) -> None:
    """Send message to Telegram."""
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, **kwargs)
    except telegram.error.TelegramError as error:
        raise BotSendMessageError(f'Send message failure: {error}') from error
    else:
        if not log:
            logger.debug(f'Bot send message: "{message}"')
        else:
            logger.debug('Log lines sent')


def get_api_answer() -> Dict[str, List]:
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


def parse_devices(data: List[Dict]) -> List:
    """Parsing devices from response."""
    logger.debug('Parsing devices')
    return [
        f"{item['name']} - {item['description']} ID: {item['id']}"
        for item in data
    ]


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


async def auto_check_devices(update: Update,
                             context: ContextTypes.DEFAULT_TYPE) -> None:
    """Auto checking devices function."""
    logger.debug('Started task: check_devices')
    await send_message(context.bot, 'Checking devices started')
    last_ips = {}
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
            await send_message(context.bot, f'Error in program: {error}')
        finally:
            logger.debug('Sleeping')
            await asyncio.sleep(RETRY_PERIOD)


async def start_checking(update: Update,
                         context: ContextTypes.DEFAULT_TYPE) -> None:
    """Starting task auto_check_devices. Command format: /start_checking"""
    asyncio.ensure_future(auto_check_devices(update, context))


async def manual_check(update: Update,
                       context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manual request. Command format: /check_online"""
    logger.debug('Manual command received')
    try:
        manual_response = get_api_answer()
        manual_data = check_response(manual_response)
        manual_devices = parse_devices(manual_data)
        devices_list = '\n'.join(manual_devices)
        if manual_statuses := parse_status(manual_data):
            await send_message(context.bot,
                               f'Offline devices: {manual_statuses}')
        else:
            await send_message(context.bot, 'All devices online')
        await send_message(context.bot,
                           f'Active devices:\n{devices_list}',
                           log=True)
    except Exception as error:
        logger.error(error)
        await send_message(context.bot, f'Error in program: {error}')


async def request_log(update: Update,
                      context: ContextTypes.DEFAULT_TYPE,
                      lines=10) -> None:
    """Send last lines of log file. Command format: /log <lines>"""
    log_file = 'main.log'
    if context.args:
        lines = int(context.args[0])
    logger.debug(f'Requested {lines} log lines')
    try:
        if not os.path.exists(log_file):
            await send_message(context.bot, 'Log file not found')
            return
        with open(log_file, 'r') as file:
            log_lines = file.readlines()
            last_lines = log_lines[-lines:]
            log_text = '\n'.join(l.strip() for l in last_lines if l.strip())
        await send_message(context.bot,
                           f'Last {lines} log records:\n{log_text}',
                           log=True)
    except Exception as error:
        logger.error(error)
        await send_message(context.bot, f'Error in program: {error}')


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_markup = ReplyKeyboardMarkup([[
        KeyboardButton('/start_checking'),
        KeyboardButton('/manual_check'),
        KeyboardButton('/request_log')
    ]], input_field_placeholder='Choose command:', resize_keyboard=True)
    await update.message.reply_text('Choose command:', reply_markup=reply_markup)


def main() -> None:
    """Main function for start bot."""
    if not check_tokens():
        sys.exit("Program interrupted! Can't find tokens.")

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('start_checking', start_checking))
    application.add_handler(CommandHandler('manual_check', manual_check))
    application.add_handler(CommandHandler('request_log', request_log))
    logger.debug('Bot started')

    application.run_polling()


if __name__ == '__main__':
    main()
