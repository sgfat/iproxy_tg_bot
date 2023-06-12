import os
from json import JSONDecodeError
from typing import Dict, List

import requests
import telegram
import telegram.error
from dotenv import load_dotenv
from requests import RequestException

from exceptions import (BotSendMessageError,
                        JSONError, APIRequestError)
from settings import logger, ENDPOINT

load_dotenv()

IPROXY_TOKEN = os.getenv('IP_TOKEN')
TELEGRAM_TOKEN = os.getenv('TG_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TG_CHAT')


async def send_message(bot, message, short_log=False, **kwargs) -> None:
    """
    Send message to Telegram.
    """
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, **kwargs)
    except telegram.error.TelegramError as error:
        raise BotSendMessageError(f'Send message failure: {error}') from error
    else:
        if not short_log:
            logger.debug(f'Bot send message: "{message}"')
        else:
            logger.debug('Bot send message')


def get_api_answer() -> Dict[str, List]:
    """
    Sending request to API.
    """
    logger.debug('Sending request to API')
    requests_params = {'url': ENDPOINT,
                       'headers': {'Authorization': f'{IPROXY_TOKEN}'}}
    try:
        response = requests.get(**requests_params)
        response.raise_for_status()
    except RequestException as error:
        raise APIRequestError(f'Error with request to API: {error}') from error
    logger.debug('Get response from API')
    try:
        return response.json()
    except JSONDecodeError as error:
        raise JSONError(f'Error with JSON: {error}') from error


def check_response(response: Dict[str, List]) -> Dict[str, Dict]:
    """
    Checking response from API.
    """
    logger.debug('Checking response from API')
    if not isinstance(response, dict):
        raise TypeError('Response is not Dict type.')
    if 'result' not in response:
        raise KeyError('No key "result" in response.')
    if not isinstance(response['result'], list):
        raise TypeError('Response["result"] is not List type.')
    if not response['result']:
        raise ValueError('Response["result"] is empty.')
    return {
        item["id"]: {key: value for key, value in item.items() if key != "id"}
        for item in response['result']
    }


def parse_status(data: Dict[str, Dict]) -> str:
    """
    Parsing online keys from response.
    """
    logger.debug('Parsing status of devices')
    offline_list = []
    for key, value in data.items():
        if not isinstance(value, dict):
            logger.error(f'Value is not Dict type: {key}')
            continue
        online = value.get('online', None)
        if online is None:
            logger.error(f'No key "online" in value: {key}')
            continue
        if not online:
            offline_list.append(f'{value["name"]} - {value["description"]}')
    return ', '.join(offline_list)


def parse_devices(data: Dict[str, Dict]) -> List:
    """
    Parsing devices from response.
    """
    logger.debug('Parsing devices')
    return [
        f"{value['name']} - {value['description']} - {key}"
        for key, value in data.items()
    ]

# TODO Проверить что время обновления меньше
def parse_ips(data: Dict[str, Dict]) -> Dict:
    """
    Parsing ips from response.
    """
    logger.debug('Parsing ips')
    current_ips = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            logger.error(f'Value is not Dict type: {key}')
            continue
        if value.get('ipChangeEnabled', None) is False:
            logger.info(f'IP rotation is disabled on device: {value["name"]}')
            continue
        external_ip = value.get('externalIp', None)
        if external_ip is None:
            logger.error(f'No key "externalIp" in value: {key}')
            continue
        current_ips[key] = external_ip
    return current_ips
