import os
import sys
from pathlib import Path


def get_resource_path(relative_path):
    try:
        base_path = Path(sys._MEIPASS)
    except Exception:
        base_path = Path(__file__).resolve().parent.parent.parent
    return base_path / relative_path


def get_user_app_data_dir():
    if sys.platform == 'win32':
        local = os.environ.get('LOCALAPPDATA')
        if local:
            return Path(local) / 'ClashAutoLoot'
    return Path.home() / '.local' / 'share' / 'ClashAutoLoot'


def get_autoloot_log_path():
    ensure_dir(get_user_app_data_dir())
    return get_user_app_data_dir() / 'autoloot.log'


def get_template_path(template_name):
    from app.config import Config

    sub = Config().aspect_key
    return get_resource_path(f'templates/{sub}/{template_name}')


def ensure_dir(path):
    path.mkdir(parents=True, exist_ok=True)
