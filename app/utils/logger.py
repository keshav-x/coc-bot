import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional


def setup_logger(
    name: str = 'AutoLoot',
    log_file: Optional[str] = None,
    level: int = logging.INFO,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.hasHandlers():
        return logger

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file is None:
        from app.utils.common import get_autoloot_log_path

        log_file = str(get_autoloot_log_path())

    try:
        file_handler = RotatingFileHandler(
            log_file,
            mode='a',
            encoding='utf-8',
            maxBytes=5242880,
            backupCount=3,
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f'Failed to set up file logging: {e}')

    return logger
