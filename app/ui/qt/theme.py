"""Dark theme tokens and QSS for the PySide6 UI."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

TOKENS = {
    'bg': '#080a0f',
    'surface': '#0f141e',
    'surface_hi': '#171e2c',
    'border': '#1c2536',
    'border_hi': '#2d3b54',
    'text': '#f1f5f9',
    'text_muted': '#8e9dae',
    'primary': '#8b5cf6',
    'primary_hov': '#7c3aed',
    'danger': '#f43f5e',
    'danger_hov': '#e11d48',
    'success': '#10b981',
    'warning': '#f59e0b',
    'neutral': '#1e2638',
    'neutral_hov': '#2b364e',
    'neutral_dark': '#131926',
    'neutral_dark_hov': '#1d2538',
    'accent_gold': '#f59e0b',
    'accent_cyan': '#06b6d4',
}

SPACING = {
    'xs': 4,
    'sm': 8,
    'md': 12,
    'lg': 16,
    'xl': 24,
}

RADIUS = 10
SIDEBAR_WIDTH = 188
WINDOW_DEFAULT = (920, 640)
WINDOW_MIN = (760, 540)

STYLESHEET = f"""
QWidget {{
    background-color: {TOKENS['bg']};
    color: {TOKENS['text']};
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    font-size: 13px;
}}
QLabel {{
    background-color: transparent;
    padding: 0;
    margin: 0;
}}
QFrame#Card {{
    background-color: {TOKENS['surface']};
    border: 1px solid {TOKENS['border']};
    border-radius: {RADIUS}px;
}}
QLabel#SectionTitle {{
    color: #a5b4fc;
    font-weight: bold;
    font-size: 12px;
    letter-spacing: 0.4px;
    background-color: transparent;
}}
QLabel#SectionTitle:disabled {{
    color: #434c60;
}}
QLabel#DurationUnit:disabled {{
    color: #434c60;
}}
QLabel#PageTitle {{
    font-size: 21px;
    font-weight: 800;
    color: {TOKENS['text']};
    background-color: transparent;
}}
QPushButton {{
    border: none;
    border-radius: 8px;
    padding: 6px 14px;
    min-height: 28px;
    font-weight: 600;
}}
QPushButton[role="primary"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b5cf6, stop:1 #7c3aed);
    color: #ffffff;
    font-weight: bold;
}}
QPushButton[role="primary"]:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9333ea, stop:1 #6d28d9);
}}
QPushButton[role="primary"]:disabled {{
    background-color: #231e36;
    color: #524a6a;
}}
QPushButton[role="danger"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f43f5e, stop:1 #e11d48);
    color: #ffffff;
    font-weight: bold;
}}
QPushButton[role="danger"]:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #fb7185, stop:1 #be123c);
}}
QPushButton[role="danger"]:disabled {{
    background-color: #2c161d;
    color: #5e323d;
}}
QPushButton[role="neutral"] {{
    background-color: {TOKENS['neutral']};
    border: 1px solid {TOKENS['border']};
    color: {TOKENS['text']};
}}
QPushButton[role="neutral"]:hover {{
    background-color: {TOKENS['neutral_hov']};
    border-color: {TOKENS['border_hi']};
}}
QPushButton[role="chip"] {{
    background-color: {TOKENS['neutral_dark']};
    border: 1px solid {TOKENS['border']};
    color: {TOKENS['text']};
    padding: 4px 10px;
    min-height: 24px;
}}
QPushButton[role="chip"]:hover {{
    background-color: {TOKENS['neutral_dark_hov']};
    border-color: {TOKENS['primary']};
}}
QPushButton[role="chip"]:disabled {{
    background-color: {TOKENS['surface_hi']};
    color: #434c60;
}}
QPushButton[role="segment"] {{
    background-color: transparent;
    border: 1px solid {TOKENS['border_hi']};
    color: {TOKENS['text_muted']};
}}
QPushButton[role="segment"]:checked {{
    background-color: {TOKENS['primary']};
    color: #ffffff;
    border-color: {TOKENS['primary']};
    font-weight: bold;
}}
QPushButton[role="segment"][underDevelopment="true"] {{
    color: #434c60;
    border-color: #2b3548;
}}
QPushButton[role="segment"]:disabled {{
    color: #434c60;
    border-color: #2b3548;
}}
QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {{
    background-color: {TOKENS['surface_hi']};
    border: 1px solid {TOKENS['border_hi']};
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: {TOKENS['primary']};
    color: {TOKENS['text']};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {TOKENS['primary']};
}}
QSpinBox#DurationSpin {{
    min-height: 28px;
    max-height: 28px;
    padding: 2px 6px;
}}
QSpinBox:disabled, QSpinBox#DurationSpin:disabled {{
    color: #434c60;
    background-color: {TOKENS['surface']};
    border-color: {TOKENS['border']};
}}
QPushButton[role="stepper"] {{
    background-color: {TOKENS['neutral_dark']};
    border: 1px solid {TOKENS['border']};
    padding: 0;
    min-height: 13px;
    max-height: 13px;
    min-width: 22px;
    max-width: 22px;
    border-radius: 4px;
}}
QPushButton[role="stepper"]:hover {{
    background-color: {TOKENS['neutral_dark_hov']};
    border-color: {TOKENS['border_hi']};
}}
QPushButton[role="stepper"]:pressed {{
    background-color: {TOKENS['neutral']};
}}
QPushButton[role="stepper"]:disabled {{
    background-color: {TOKENS['surface_hi']};
    border-color: {TOKENS['border']};
}}
QPushButton[role="help"] {{
    background-color: transparent;
    color: {TOKENS['text_muted']};
    padding: 0;
    min-height: 18px;
    min-width: 18px;
    max-height: 18px;
    max-width: 18px;
    border-radius: 9px;
    border: 1px solid {TOKENS['text_muted']};
    font-size: 11px;
    font-weight: bold;
}}
QPushButton[role="help"]:hover {{
    color: {TOKENS['text']};
    border-color: {TOKENS['text']};
}}
QPushButton[role="icon"] {{
    background-color: {TOKENS['neutral_dark']};
    border: 1px solid {TOKENS['border']};
    color: {TOKENS['text']};
    padding: 0;
    min-height: 34px;
    min-width: 34px;
    max-height: 34px;
    max-width: 34px;
    border-radius: 6px;
}}
QPushButton[role="icon"]:hover {{
    background-color: {TOKENS['neutral_dark_hov']};
    border-color: {TOKENS['border_hi']};
}}
QPushButton[role="icon"]:checked {{
    background-color: {TOKENS['neutral']};
    border-color: {TOKENS['primary']};
}}
QListWidget#Sidebar {{
    background-color: #0b0e15;
    border: none;
    border-right: 1px solid #1c2536;
    padding: 8px;
}}
QListWidget#Sidebar::item {{
    padding: 10px 14px;
    border-radius: 8px;
    color: {TOKENS['text_muted']};
    font-weight: 500;
    margin-bottom: 2px;
}}
QListWidget#Sidebar::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b5cf6, stop:1 #6366f1);
    color: #ffffff;
    font-weight: bold;
}}
QListWidget#Sidebar::item:hover:!selected {{
    background-color: {TOKENS['surface_hi']};
    color: {TOKENS['text']};
}}
QStatusBar {{
    background-color: #0b0e15;
    border-top: 1px solid {TOKENS['border']};
}}
QStatusBar::item {{
    border: none;
}}
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
}}
QScrollBar::handle:vertical {{
    background: {TOKENS['border_hi']};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TOKENS['primary']};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
}}
QProgressBar {{
    background-color: #0d121c;
    border: 1px solid #1c2536;
    border-radius: 4px;
    text-align: center;
    color: #ffffff;
    font-size: 11px;
    height: 9px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b5cf6, stop:0.5 #06b6d4, stop:1 #10b981);
    border-radius: 3px;
}}
QTableWidget {{
    background-color: #0d121c;
    alternate-background-color: #121824;
    border: 1px solid #1c2536;
    border-radius: 8px;
    gridline-color: #1c2536;
    color: {TOKENS['text']};
    font-size: 12px;
}}
QTableWidget::item {{
    padding: 5px 8px;
    border: none;
}}
QTableWidget::item:selected {{
    background-color: {TOKENS['primary']};
    color: #ffffff;
}}
QHeaderView::section {{
    background-color: #0b0e15;
    color: {TOKENS['text_muted']};
    font-weight: bold;
    font-size: 11px;
    border: none;
    border-bottom: 1px solid #1c2536;
    padding: 6px 8px;
}}
QFrame#TrialBanner {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #111724, stop:1 #171f2e);
    border: 1px solid #2d3b54;
    border-radius: 8px;
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(TOKENS['bg']))
    pal.setColor(QPalette.Base, QColor(TOKENS['surface_hi']))
    pal.setColor(QPalette.AlternateBase, QColor(TOKENS['surface']))
    pal.setColor(QPalette.Text, QColor(TOKENS['text']))
    pal.setColor(QPalette.WindowText, QColor(TOKENS['text']))
    pal.setColor(QPalette.Button, QColor(TOKENS['surface']))
    pal.setColor(QPalette.ButtonText, QColor(TOKENS['text']))
    pal.setColor(QPalette.ToolTipBase, QColor(TOKENS['surface']))
    pal.setColor(QPalette.ToolTipText, QColor(TOKENS['text']))
    pal.setColor(QPalette.Highlight, QColor(TOKENS['primary']))
    pal.setColor(QPalette.HighlightedText, QColor('#ffffff'))
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)
