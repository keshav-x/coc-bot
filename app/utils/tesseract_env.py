"""Resolve Tesseract OCR for development and for PyInstaller one-file builds."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.utils.logger import setup_logger

logger = setup_logger('TesseractEnv')


def _patch_pytesseract_hidden_console() -> None:
    if sys.platform != 'win32':
        return
    flag = getattr(subprocess, 'CREATE_NO_WINDOW', None)
    if flag is None:
        return
    try:
        from pytesseract import pytesseract as pt
    except ImportError:
        return

    _orig = pt.subprocess_args

    def subprocess_args(include_stdout: bool = True):
        kwargs = _orig(include_stdout)
        prev = int(kwargs.get('creationflags', 0))
        kwargs['creationflags'] = prev | flag
        return kwargs

    pt.subprocess_args = subprocess_args


def _tessdata_dir(install_root: Path) -> Path:
    return install_root / 'tessdata'


def configure_tesseract() -> None:
    _patch_pytesseract_hidden_console()
    try:
        import pytesseract
    except ImportError:
        return

    if 'TESSERACT_CMD' in os.environ:
        cmd = Path(os.environ['TESSERACT_CMD'])
        pytesseract.pytesseract.tesseract_cmd = str(cmd)
        td = _tessdata_dir(cmd.parent)
        os.environ['TESSDATA_PREFIX'] = str(td.resolve()) + os.sep
        logger.debug('Tesseract from TESSERACT_CMD: %s, tessdata=%s', cmd, td)
        return

    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base = Path(sys._MEIPASS)
        bundled = base / 'tesseract.exe'
        if bundled.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(bundled)
            td = _tessdata_dir(base)
            os.environ['TESSDATA_PREFIX'] = str(td.resolve()) + os.sep
            logger.debug('Tesseract bundled at %s, tessdata=%s', bundled, td)
            return
        else:
            logger.error(
                'Frozen build: tesseract.exe not found under %s. OCR will not work; the Tesseract binary was not bundled/extracted correctly.',
                base,
            )
            return

    win = Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe')
    if win.is_file():
        pytesseract.pytesseract.tesseract_cmd = str(win)
        td = _tessdata_dir(win.parent)
        os.environ['TESSDATA_PREFIX'] = str(td.resolve()) + os.sep
        logger.debug('Tesseract dev install: %s, tessdata=%s', win, td)
        return

    logger.error(
        'Tesseract not configured (install with winget install UB-Mannheim.TesseractOCR or set TESSERACT_CMD). OCR will not work until Tesseract is available.'
    )
