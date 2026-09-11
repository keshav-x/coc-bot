import sys
import os
from multiprocessing import freeze_support

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.ui.qt.app import run_gui
from app.utils.logger import setup_logger
from app.utils.tesseract_env import configure_tesseract

logger = setup_logger('Main')


def main():
    try:
        configure_tesseract()
        logger.info('Starting Application...')
        run_gui()
    except Exception as e:
        logger.critical(f'Unhandled exception: {e}', exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    freeze_support()
    main()
