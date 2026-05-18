import logging
import os
import configparser
import inspect
from consts.sys_consts import *

""" 
Here's how the log levels work:

logging.DEBUG: Logs all messages (DEBUG, INFO, WARNING, ERROR, CRITICAL).
logging.INFO: Logs INFO, WARNING, ERROR, and CRITICAL messages, but not DEBUG.
logging.WARNING: Logs WARNING, ERROR, and CRITICAL messages, but not DEBUG or INFO.
logging.ERROR: Logs ERROR and CRITICAL messages, but not DEBUG, INFO, or WARNING.
logging.CRITICAL: Logs only CRITICAL messages. 

"""

# Default logging configuration
logging.basicConfig(
    filename='app.log',
    filemode='w',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%d-%b-%y %I:%M:%S %p'
)


def setup_logging_from_config(config_file):
    """
    Sets up logging configuration from a config file.
    
    Parameters:
        config_file (str): Path to the configuration file.
    
    Config file format (INI):
        [Logging]
        filename = app.log
        filemode = w
    """
    # Create a ConfigParser object and read the config file
    config = configparser.ConfigParser()
    config.read(config_file)

    # Read logging settings
    filename = config['Logging']['filename']
    filemode = config.get('Logging', 'filemode', fallback='w')

    # Set up logging
    logging.basicConfig(
        filename=filename,
        filemode=filemode,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%d-%b-%y %I:%M:%S %p',
        force=True  # Override any existing configuration
    )


def log_message(level, message):
    """
    Logs a message at the specified level with caller information.
    
    Parameters:
        level (str): Log level - 'debug', 'info', 'warning', 'error', or 'critical'
        message (str): The message to log
    """
    try:
        # Get the current stack frame
        stack = inspect.stack()
        # The caller of log_message is one level up the stack from the current position
        caller_frame = stack[1]
        caller_filename = os.path.splitext(os.path.basename(caller_frame.filename))[0]
        logger = logging.getLogger(caller_filename)
        logger.setLevel(logging.DEBUG)

        full_message = f'{level} message from {caller_filename}: {message}'
        if PRINT_MESSAGES:
            print(f'{caller_filename}: {message}')

        log_function = getattr(logger, level)
        log_function(full_message)
    except Exception as e:
        print(f"An error occurred while logging: {e}")
