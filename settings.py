import logging
import sys

from logging.handlers import RotatingFileHandler

# Default retry periods for auto checkers in minutes
RETRY_PERIOD = 30

# Default lines in log file to send
LOG_LINES = 10

# API endpoint
ENDPOINT = 'https://api.iproxy.online/v1/connections?with_statuses=1'

# Log format
LOG_DEBUG_FORMAT = '%(asctime)s, %(levelname)s, line %(lineno)d, %(message)s'
LOG_INFO_FORMAT = '%(asctime)s - %(message)s'

# Log file name
LOG_DEBUG_FILE = 'debug.log'
LOG_INFO_FILE = 'info.log'

# Logging settings
logger = logging.getLogger('debug')
info_logger = logging.getLogger('info')
logger.setLevel(logging.DEBUG)
info_logger.setLevel(logging.INFO)

stream_handler = logging.StreamHandler(sys.stdout)
fileHandler = RotatingFileHandler(LOG_DEBUG_FILE, maxBytes=5000000, backupCount=5)
info_handler = RotatingFileHandler(LOG_INFO_FILE, maxBytes=5000000, backupCount=5)

formatter = logging.Formatter(LOG_DEBUG_FORMAT)
info_format = logging.Formatter(fmt=LOG_INFO_FORMAT, datefmt='%d-%m-%Y %H:%M:%S')

fileHandler.setFormatter(formatter)
stream_handler.setFormatter(formatter)
info_handler.setFormatter(info_format)

logger.addHandler(fileHandler)
logger.addHandler(stream_handler)
info_logger.addHandler(info_handler)
