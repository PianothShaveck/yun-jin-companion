# SPDX-License-Identifier: GPL-3.0-or-later
"""One language, one small catalog; no widget scanning or background work."""
import json
import os
from pathlib import Path

LANGUAGES = (('en', 'English'), ('it', 'Italiano'), ('zh-CN', '简体中文'))
_language = os.environ.get('YUNJIN_LANGUAGE', 'en')
if _language not in dict(LANGUAGES):
    _language = 'en'
_initial_catalog = Path(__file__).with_name('locales') / (_language + '.json')
_catalog = json.loads(_initial_catalog.read_text(encoding='utf-8')) if _language in ('en','zh-CN') and _initial_catalog.is_file() else {}
_qt_translator = None


def language():
    return _language


def tr(text, **values):
    result = _catalog.get(text, text)
    return result.format(**values) if values else result


def set_language(code):
    global _language, _catalog, _qt_translator
    if code not in dict(LANGUAGES):
        code = 'en'
    path = Path(__file__).with_name('locales') / (code + '.json')
    _catalog = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    _language = code
    os.environ['YUNJIN_LANGUAGE'] = code
    from PyQt6.QtCore import QLocale, QTranslator, QLibraryInfo
    from PyQt6.QtWidgets import QApplication
    QLocale.setDefault(QLocale(code.replace('-', '_')))
    app = QApplication.instance()
    if app is not None:
        if _qt_translator is not None:
            app.removeTranslator(_qt_translator)
        _qt_translator = QTranslator(app)
        if _qt_translator.load(QLocale(), 'qtbase', '_', QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
            app.installTranslator(_qt_translator)


def choose_language(store):
    """First launch needs only the three language names, with no onboarding copy."""
    code = store.preference('ui_language', '')
    if code in dict(LANGUAGES):
        set_language(code)
        return True
    from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton
    from yun_jin_ui import STYLE
    dialog = QDialog()
    dialog.setWindowTitle('Yun Jin')
    dialog.setStyleSheet(STYLE)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(12)
    chosen = []
    def select(value):
        chosen.append(value)
        dialog.accept()
    for value, name in LANGUAGES:
        button = QPushButton(name)
        button.setAutoDefault(value == 'en')
        button.setDefault(value == 'en')
        button.clicked.connect(lambda checked=False, value=value: select(value))
        layout.addWidget(button)
        if value == 'en':
            button.setFocus()
    if not dialog.exec() or not chosen:
        return False
    set_language(chosen[0])
    store.set_preference('ui_language', chosen[0])
    # Interface and speech can subsequently be changed independently.
    if store.preference('tts_language', None) is None:
        store.set_preference('tts_language', chosen[0])
    return True
