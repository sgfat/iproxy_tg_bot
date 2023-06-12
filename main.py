import asyncio
import os
import sys

from dotenv import load_dotenv
from telegram.ext import CommandHandler, Application

from commands import status, start_check_devices, start, send_startup_message, log, start_check_rotation
from settings import logger, info_logger

load_dotenv()

IPROXY_TOKEN = os.getenv('IP_TOKEN')
TELEGRAM_TOKEN = os.getenv('TG_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TG_CHAT')


def check_tokens() -> bool:
    """
    Checking main tokens.
    """
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


def main() -> None:
    """
    Main function for start bot.
    """
    if not check_tokens():
        sys.exit("Program interrupted! Can't find tokens.")

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('start_check_devices', start_check_devices))
    application.add_handler(CommandHandler('start_check_rotation', start_check_rotation))
    application.add_handler(CommandHandler('status', status))
    application.add_handler(CommandHandler('log', log))
    logger.debug('Bot started')
    info_logger.info('Bot started')

    loop = asyncio.get_event_loop()
    loop.run_until_complete(send_startup_message(application))

    application.run_polling()


if __name__ == '__main__':
    main()
