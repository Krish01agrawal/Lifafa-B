import logging
import sys
from datetime import datetime

def setup_logging():
    """
    Set up comprehensive logging configuration for the Gmail data upload application.
    """
    
    # Create custom formatter with timestamp, level, module, and message
    class CustomFormatter(logging.Formatter):
        """Custom formatter with colors and emojis for better readability"""
        
        # Color codes
        COLORS = {
            'DEBUG': '\033[36m',     # Cyan
            'INFO': '\033[32m',      # Green
            'WARNING': '\033[33m',   # Yellow
            'ERROR': '\033[31m',     # Red
            'CRITICAL': '\033[35m',  # Magenta
        }
        RESET = '\033[0m'
        
        # Emoji mapping for levels
        EMOJIS = {
            'DEBUG': '🔍',
            'INFO': 'ℹ️',
            'WARNING': '⚠️',
            'ERROR': '❌',
            'CRITICAL': '💥',
        }
        
        def format(self, record):
            # Add color and emoji to level name
            levelname = record.levelname
            if levelname in self.COLORS:
                emoji = self.EMOJIS.get(levelname, '')
                colored_level = f"{self.COLORS[levelname]}{emoji} {levelname}{self.RESET}"
                record.levelname = colored_level
            
            # Add module name for better traceability
            if hasattr(record, 'name'):
                record.module_name = record.name.split('.')[-1]
            else:
                record.module_name = 'unknown'
            
            return super().format(record)
    
    # Create formatters
    detailed_formatter = CustomFormatter(
        fmt='%(asctime)s | %(levelname)s | %(module_name)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = CustomFormatter(
        fmt='%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(detailed_formatter)
    console_handler.setLevel(logging.INFO)
    
    # Create file handler for detailed logs
    file_handler = logging.FileHandler('gmail_upload.log', mode='a', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(
        fmt='%(asctime)s | %(levelname)s | %(name)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    file_handler.setLevel(logging.DEBUG)
    
    # Create error file handler
    error_handler = logging.FileHandler('gmail_upload_errors.log', mode='a', encoding='utf-8')
    error_handler.setFormatter(logging.Formatter(
        fmt='%(asctime)s | %(levelname)s | %(name)s:%(lineno)d | %(message)s\n%(exc_info)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    error_handler.setLevel(logging.ERROR)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Add handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)
    
    # Configure specific loggers
    loggers_to_configure = [
        'app.main',
        'app.gmail',
        'app.mem0_agent',
        'app.oauth',
        'app.auth',
        'app.db'
    ]
    
    for logger_name in loggers_to_configure:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        # Don't propagate to avoid duplicate logs
        logger.propagate = True
    
    # Suppress noisy third-party loggers
    logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.WARNING)
    logging.getLogger('googleapiclient.discovery').setLevel(logging.WARNING)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    
    # Log the setup completion
    logger = logging.getLogger(__name__)
    logger.info("🎛️ Logging system initialized successfully")
    logger.info(f"📝 Detailed logs: gmail_upload.log")
    logger.info(f"🚨 Error logs: gmail_upload_errors.log")
    
    return root_logger

def log_function_entry(func_name: str, **kwargs):
    """Helper function to log function entry with parameters"""
    logger = logging.getLogger()
    params = ', '.join([f"{k}={v}" for k, v in kwargs.items()])
    logger.info(f"🔵 ENTER {func_name}({params})")

def log_function_exit(func_name: str, result=None, duration=None):
    """Helper function to log function exit with result and duration"""
    logger = logging.getLogger()
    result_str = f" -> {result}" if result is not None else ""
    duration_str = f" (took {duration:.2f}s)" if duration is not None else ""
    logger.info(f"🔴 EXIT {func_name}{result_str}{duration_str}")

def log_step_progress(step: int, total: int, description: str):
    """Helper function to log step progress"""
    logger = logging.getLogger()
    progress = f"[{step}/{total}]"
    logger.info(f"⏳ {progress} {description}")

def log_email_processing(email_index: int, total_emails: int, email_id: str, subject: str = None):
    """Helper function to log individual email processing"""
    logger = logging.getLogger()
    progress = f"[{email_index}/{total_emails}]"
    subject_str = f" - '{subject[:50]}...'" if subject and len(subject) > 50 else f" - '{subject}'" if subject else ""
    logger.info(f"📧 {progress} Processing email {email_id}{subject_str}")

def log_error_summary(operation: str, successful: int, failed: int, total: int):
    """Helper function to log operation summary"""
    logger = logging.getLogger()
    success_rate = (successful / total * 100) if total > 0 else 0
    logger.info(f"📊 {operation} Summary: ✅ {successful} succeeded, ❌ {failed} failed, 📈 {success_rate:.1f}% success rate") 