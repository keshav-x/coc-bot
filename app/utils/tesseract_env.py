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
        logger.error('pytesseract package is not installed')
        return

    # 1. User/environment override
    if 'TESSERACT_CMD' in os.environ:
        cmd = Path(os.environ['TESSERACT_CMD'])
        if cmd.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(cmd)
            td = _tessdata_dir(cmd.parent)
            if not td.is_dir():
                td = cmd.parent / 'tessdata'
            if td.is_dir():
                os.environ['TESSDATA_PREFIX'] = str(td.resolve()) + os.sep
            logger.info('Tesseract configured from TESSERACT_CMD: %s, tessdata=%s', cmd, td)
            return

    # 2. Check bundled locations (frozen or local dist)
    candidate_bases: list[Path] = []
    if getattr(sys, 'frozen', False):
        if hasattr(sys, '_MEIPASS'):
            candidate_bases.append(Path(sys._MEIPASS))
            candidate_bases.append(Path(sys._MEIPASS) / '_internal')
        if hasattr(sys, 'executable'):
            exe_parent = Path(sys.executable).parent
            candidate_bases.append(exe_parent)
            candidate_bases.append(exe_parent / '_internal')
    else:
        candidate_bases.append(Path.cwd())
        candidate_bases.append(Path.cwd() / '_internal')

    binary_names = ('tesseract.exe', 'tesseract') if sys.platform == 'win32' else ('tesseract',)

    found_cmd: Optional[Path] = None
    for base in candidate_bases:
        for name in binary_names:
            c = base / name
            if c.is_file():
                found_cmd = c
                break
        if found_cmd:
            break

    # 3. System PATH fallback
    if not found_cmd:
        import shutil
        which_tess = shutil.which('tesseract')
        if which_tess:
            found_cmd = Path(which_tess)
            logger.info('Found system Tesseract via PATH: %s', found_cmd)

    # 4. Standard platform installation locations
    if not found_cmd:
        if sys.platform == 'win32':
            win_candidates = [
                Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe'),
                Path(r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'),
            ]
            localappdata = os.environ.get('LOCALAPPDATA')
            if localappdata:
                win_candidates.append(Path(localappdata) / 'Programs' / 'Tesseract-OCR' / 'tesseract.exe')
            userprofile = os.environ.get('USERPROFILE')
            if userprofile:
                win_candidates.append(Path(userprofile) / 'AppData' / 'Local' / 'Programs' / 'Tesseract-OCR' / 'tesseract.exe')

            for wc in win_candidates:
                if wc.is_file():
                    found_cmd = wc
                    logger.info('Found standard Windows Tesseract install: %s', found_cmd)
                    break
        else:
            unix_candidates = [
                Path('/usr/bin/tesseract'),
                Path('/usr/local/bin/tesseract'),
                Path('/opt/homebrew/bin/tesseract'),
                Path('/usr/bin/tesseract-ocr'),
            ]
            for uc in unix_candidates:
                if uc.is_file():
                    found_cmd = uc
                    logger.info('Found standard Unix Tesseract install: %s', found_cmd)
                    break

    if found_cmd:
        pytesseract.pytesseract.tesseract_cmd = str(found_cmd)
        # Resolve tessdata
        td_candidates = [
            found_cmd.parent / 'tessdata',
            found_cmd.parent / '_internal' / 'tessdata',
            Path.cwd() / 'tessdata',
        ]
        if hasattr(sys, '_MEIPASS'):
            td_candidates.insert(0, Path(sys._MEIPASS) / 'tessdata')
        if sys.platform == 'win32':
            td_candidates.append(Path(r'C:\Program Files\Tesseract-OCR\tessdata'))

        for td in td_candidates:
            if td.is_dir() and any(td.glob('*.traineddata')):
                os.environ['TESSDATA_PREFIX'] = str(td.resolve()) + os.sep
                logger.info('Tesseract successfully configured: %s (tessdata: %s)', found_cmd, td)
                return

        logger.info('Tesseract configured: %s (default tessdata)', found_cmd)
        return

    logger.error(
        'Tesseract not configured (install with winget install UB-Mannheim.TesseractOCR, apt install tesseract-ocr, or brew install tesseract). OCR will not work until Tesseract is available.'
    )

