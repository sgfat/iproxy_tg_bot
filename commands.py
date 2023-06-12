import asyncio
import os

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, Application

from api import check_response, get_api_answer, parse_status, parse_ips, parse_devices, send_message
from exceptions import BotSendMessageError
from settings import logger, RETRY_PERIOD, LOG_LINES, LOG_INFO_FILE, info_logger


async def check_rotation(update: Update,
                         context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Auto checking rotation function task.
    """
    # TODO проверять адреса на повторение только если включена проверка
    logger.debug('Started task: auto_check_rotation')
    info_logger.info('Auto checking rotation started')
    retry_period = context.bot_data.get('retry_check_rotation', RETRY_PERIOD) * 60
    last_ips = {}
    while True:
        try:
            response = get_api_answer()
            data = check_response(response)
            current_ips = parse_ips(data)
            for device_id in current_ips:
                if current_ips[device_id] is None:
                    continue
                if last_ips.get(device_id, device_id) == current_ips[device_id]:
                    await send_message(context.bot,
                                       f'IP not changed on device: '
                                       f'{data["device_id"]["name"]}')
                    info_logger.info(f'IP not changed for last {RETRY_PERIOD} '
                                     f'minutes: {data["device_id"]["name"]}')
                else:
                    last_ips[device_id] = current_ips[device_id]

            logger.debug('IP rotation checked')
            info_logger.info('IP rotation checked')
        except BotSendMessageError as error:
            logger.debug(f'Send message failure: {error}')
        except Exception as error:
            logger.error(error)
            await send_message(context.bot, f'Error in program: {error}')
        finally:
            logger.debug('Sleeping rotation check')
            await asyncio.sleep(retry_period)


async def check_devices(update: Update,
                        context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Auto checking online status function task.
    """
    logger.debug('Started task: check_devices')
    info_logger.info('Auto checking online started')
    retry_period = context.bot_data.get('retry_period', RETRY_PERIOD) * 60
    await send_message(context.bot, 'Checking devices started')
    while True:
        try:
            response = get_api_answer()
            data = check_response(response)
            if offline_devices := parse_status(data):
                info_logger.info(f'Offline devices: {offline_devices}')
                await send_message(context.bot,
                                   f'Offline devices: {offline_devices}')
            else:
                info_logger.info('All devices online')
        except BotSendMessageError as error:
            logger.debug(f'Send message failure: {error}')
        except Exception as error:
            logger.error(f'Error: {error}')
            await send_message(context.bot, f'Error in program: {error}')
        finally:
            logger.debug('Checking online sleep')
            info_logger.info(f'Checking online sleep for ({retry_period} min)')
            await asyncio.sleep(retry_period)


# TODO добавить команду /stop_checking
async def start_check_devices(update: Update,
                              context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Starting task check_devices.
    Command format: /start_check_devices <retry period in minutes>
    """
    if context.args:
        try:
            context.bot_data['retry_period'] = int(context.args[0])
        except ValueError:
            await send_message(context.bot, 'Retry period must be integer!')
            logger.error('Retry period must be integer')
            return
    else:
        context.bot_data['retry_period'] = RETRY_PERIOD
    if 'check_devices_task' not in context.bot_data:
        task = asyncio.ensure_future(check_devices(update, context))
        context.bot_data['check_devices_task'] = task
    else:
        await send_message(context.bot, 'Checking devices is already running.')
        logger.debug('Checking devices is already running')


async def start_check_rotation(update: Update,
                              context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Starting task check_rotation.
    Command format: /start_check_rotation <retry period in minutes>
    """
    if context.args:
        try:
            context.bot_data['retry_check_rotation'] = int(context.args[0])
        except ValueError:
            await send_message(context.bot, 'Retry period must be integer!')
            logger.error('Retry period must be integer')
            return
    else:
        context.bot_data['retry_check_rotation'] = RETRY_PERIOD
    if 'check_rotation_task' not in context.bot_data:
        task = asyncio.ensure_future(check_rotation(update, context))
        context.bot_data['check_rotation_task'] = task
    else:
        await send_message(context.bot, 'Check rotation is already running.')
        logger.debug('Check rotation is already running.')


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Manual status request.
    Command format: /status
    """
    logger.debug('Manual command received')
    if 'check_devices_task' in context.bot_data:
        check_devices_task_status = f'Running ({context.bot_data["retry_period"]} min)'
    else:
        check_devices_task_status = 'Stopped'
    if 'check_rotation_task' in context.bot_data:
        check_rotation_task_status = f'Running ({context.bot_data["retry_check_rotation"]} min)'
    else:
        check_rotation_task_status = 'Stopped'
    try:
        manual_response = get_api_answer()
        manual_data = check_response(manual_response)
        manual_devices = parse_devices(manual_data)
        devices_list = '\n'.join(manual_devices)
        if offline_devices := parse_status(manual_data):
            online_status = f'offline devices {offline_devices}'
        else:
            online_status = 'all devices online'
            info_logger.info('All devices online')
        await send_message(
            context.bot,
            f'Registered devices:\n'
            f'name - description - id connection\n'
            f'{devices_list}\n\n'
            f'Checking online devices: {check_devices_task_status}\n\n'
            f'Checking rotation devices: {check_rotation_task_status}\n\n'
            f'Online status: {online_status}',
            short_log=True
        )
    except Exception as error:
        logger.error(error)
        await send_message(context.bot, f'Error in program: {error}')

# TODO добавить дефолтный lines в context.bot_data
async def log(update: Update,
              context: ContextTypes.DEFAULT_TYPE,
              lines=LOG_LINES) -> None:
    """
    Send last lines of log file.
    Command format: /log <lines>
    """
    if context.args:
        try:
            lines = int(context.args[0])
        except ValueError:
            await send_message(context.bot, 'Lines must be integer!')
            logger.error('Lines must be integer')
            return
    logger.debug(f'Requested {lines} log lines')
    try:
        if not os.path.exists(LOG_INFO_FILE):
            await send_message(context.bot, 'Log file not found')
            return
        with open(LOG_INFO_FILE, 'r') as file:
            log_lines = file.readlines()
            last_lines = log_lines[-lines:]
            log_text = '\n'.join(l.strip() for l in last_lines if l.strip())
        await send_message(context.bot,
                           f'Last {lines} log records:\n{log_text}',
                           short_log=True)
    except Exception as error:
        logger.error(error)
        await send_message(context.bot, f'Error in program: {error}')


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Start command handler.
    Command format: /start
    """
    reply_markup = ReplyKeyboardMarkup([[
        KeyboardButton('/start_checking'),
        KeyboardButton('/status'),
        KeyboardButton('/log')
    ]], input_field_placeholder='Choose command:', resize_keyboard=True)
    await update.message.reply_text('Choose command:', reply_markup=reply_markup)


async def send_startup_message(application: Application) -> None:
    """
    Send startup message.
    """
    await send_message(application.bot,
                       f'Bot is ready for work!\nRun command: /start',
                       short_log=True)
