import asyncio
import logging
import os
import sys
import time
from http import HTTPStatus
from logging.handlers import RotatingFileHandler
from typing import Dict, List

import requests
import telegram
import telegram.error
from dotenv import load_dotenv

from exceptions import NoAPIAnswerError, BotSendMessageError

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
    'main.log', maxBytes=50000000, backupCount=5
)
formatter = logging.Formatter(
    '%(asctime)s, %(levelname)s, %(lineno)d, %(message)s, %(name)s'
)
fileHandler.setFormatter(formatter)
logger.addHandler(fileHandler)


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


async def send_message(bot, message, silent=False):
    """Send message to Telegram."""
    try:
        if silent:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message,
                                   disable_notification=True)
        else:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except telegram.error.TelegramError as error:
        raise BotSendMessageError(f'Send message failure: {error}')
    else:
        logger.debug(f'Bot send message: "{message}"')


def get_api_answer():
    """Sending request to API."""
    logger.debug('Sending request to API')
    requests_params = {'url': ENDPOINT, 'headers': HEADERS}
    try:
        response = requests.get(**requests_params)
    except Exception as error:
        raise Exception(f'Error with request to API: {error}')
    else:
        if response.status_code != HTTPStatus.OK:
            raise NoAPIAnswerError(
                "Can't get response from API."
                f'Error code: {response.status_code}')
        logger.debug('Get response from API')
    try:
        return response.json()
    except Exception as error:
        raise Exception(f'Error with JSON: {error}')


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


async def main():
    """Start bot."""
    if not check_tokens():
        sys.exit("Program interrupted! Can't find tokens.")
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    last_ips = {}
    logger.debug('Bot started')
    async with bot:
        while True:
            try:
                response = get_api_answer()
                data = check_response(response)

                statuses = parse_status(data)
                if statuses:
                    await send_message(bot, f'Offline devices: {statuses}')
                else:
                    logger.debug('All devices online')

                current_ips = parse_ips(data)
                for device_id in current_ips:
                    if current_ips[device_id] is None:
                        continue
                    if last_ips.get(
                            device_id, device_id) == current_ips[device_id]:
                        await send_message(
                            bot, f'IP not changed on device: {device_id}')
                        logger.debug('IP not changed: {c_id}')
                    else:
                        last_ips[device_id] = current_ips[device_id]
                else:
                    logger.debug('IPs checked')

            except BotSendMessageError as error:
                logger.debug(f'Send message failure: {error}')
            except Exception as error:
                logger.error(error)
                message = f'Error in program: {error}'
                await send_message(bot, message)
            finally:
                await send_message(bot, 'All checked', silent=True)
                logger.debug('Sleeping')
                time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    asyncio.run(main())
