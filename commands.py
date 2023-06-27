import asyncio
import os

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, Application

from api import check_response, get_api_answer, parse_status, parse_ips, parse_devices, send_message
from exceptions import BotSendMessageError
from settings import logger, RETRY_PERIOD, LOG_LINES, LOG_INFO_FILE, info_logger


async def start(update: Update,
                context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Starting task check_devices or check_rotation.
    Command format: /start_check <task_name> <retry period in minutes>
    """
    if len(context.args) < 2:
        await send_message(context.bot, 'Invalid command format for start_check')
        logger.error('Invalid command format for start_check')
        return

    try:
        task_name = context.args[0]
        retry_period = int(context.args[1])
    except ValueError:
        await send_message(context.bot, 'Invalid command format for start_check')
        logger.error('Invalid command format for start_check')
        return

    tasks = {
        'check_devices': {'task': 'check_devices_task', 'retry': 'retry_devices'},
        'check_rotation': {'task': 'check_rotation_task', 'retry': 'retry_rotation'}
    }

    if task_name in tasks:
        task_info = tasks[task_name]
        task_key = task_info['task']
        retry_period_key = task_info['retry']

        if task_key not in context.bot_data:
            context.bot_data[retry_period_key] = retry_period
            task = asyncio.ensure_future(globals()[task_name](update, context))
            context.bot_data[task_key] = task
        else:
            await send_message(context.bot, f'{task_key} is already running.')
            logger.debug(f'{task_key} is already running.')
    else:
        await send_message(context.bot, 'Invalid task_name! '
                                        'Available options: devices, rotation')
        logger.error('Invalid task_name for start_check')




async def check_rotation(update: Update,
                         context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Auto checking rotation function task.
    """
    logger.debug('Started task: check_rotation')
    info_logger.info('Auto checking rotation started')
    retry_period = context.bot_data.get('retry_rotation', RETRY_PERIOD) * 60
    last_ips = {}
    await send_message(context.bot, 'Checking rotation started')
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
    retry_period = context.bot_data.get('retry_devices', RETRY_PERIOD)
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
            await asyncio.sleep(retry_period * 60)


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


async def stop_check(update: Update,
                     context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Stopping task check_devices.
    Command format: /stop_checking
    """
    if 'check_devices_task' in context.bot_data:
        task = context.bot_data['check_devices_task']
        task.cancel()
        del context.bot_data['check_devices_task']
        await send_message(context.bot, 'Checking devices stopped.')
        logger.debug('Checking devices stopped')
    else:
        await send_message(context.bot, 'No active checking devices task found.')
        logger.debug('No active checking devices task found')


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
        check_devices_task_status = f'✅ running ({context.bot_data["retry_devices"]} min)'
    else:
        check_devices_task_status = '🛑 stopped'
    if 'check_rotation_task' in context.bot_data:
        check_rotation_task_status = f'✅ running ({context.bot_data["retry_rotation"]} min)'
    else:
        check_rotation_task_status = '🛑 stopped'
    try:
        manual_response = get_api_answer()
        manual_data = check_response(manual_response)
        manual_devices = parse_devices(manual_data)
        devices_list = '\n'.join(manual_devices)
        await send_message(
            context.bot,
            f'<code>'
            f'Registered devices:\n\n'
            f'{devices_list}\n\n'
            f'Auto check online: {check_devices_task_status}\n'
            f'Auto check rotation: {check_rotation_task_status}\n'
            f'</code>',
            short_log=True,
            parse_mode=ParseMode.HTML
        )
    except Exception as error:
        logger.error(error)
        await send_message(context.bot, f'Error in program: {error}')

async def log(update: Update,
              context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Send last lines of log file.
    Command format: /log <lines>
    """
    if context.args:
        try:
            context.bot_data['lines'] = int(context.args[0])
        except ValueError:
            await send_message(context.bot, 'Lines must be integer!')
            logger.error('Lines must be integer')
            return
    else:
        context.bot_data['lines'] = LOG_LINES
    logger.debug(f'Requested {context.bot_data["lines"]} log lines')
    try:
        if not os.path.exists(LOG_INFO_FILE):
            await send_message(context.bot, 'Log file not found')
            return
        with open(LOG_INFO_FILE, 'r') as file:
            log_lines = file.readlines()
            last_lines = log_lines[-context.bot_data['lines']:]
            log_text = '\n'.join(l.strip() for l in last_lines if l.strip())
        await send_message(context.bot,
                           f'Last {context.bot_data["lines"]} info log records:'
                           f'\n<code>{log_text}</code>',
                           short_log=True, parse_mode=ParseMode.HTML)
    except Exception as error:
        logger.error(error)
        await send_message(context.bot, f'Error in program: {error}')


async def send_startup_message(application: Application) -> None:
    """
    Send startup message.
    """
    await send_message(application.bot,
                       f'Bot is ready for work!\nRun command: /start',
                       short_log=True)
