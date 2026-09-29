# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared ownership, modality and focus for every application dialog."""
import sys
from pathlib import Path
from PyQt6 import sip
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QFileDialog
from yun_jin_ui import STYLE


def companion(widget):
    while widget is not None:
        if hasattr(widget, 'focus_tool'):
            return widget
        if getattr(widget, 'pet', None) is not None:
            return widget.pet
        widget = widget.parentWidget()
    return None


def owner_window(owner):
    """Keep explicit dialog owners; route pet/global notices to the visible tool."""
    pet = companion(owner)
    if owner is None or owner is pet:
        modal = QApplication.activeModalWidget()
        if modal is not None:
            return modal
        panel = getattr(pet, 'panel', None)
        if panel is not None and panel.isVisible():
            return panel
        if owner is None:
            return QApplication.activeWindow()
    return owner.window() if owner is not None else None


def bring_forward(dialog, pet):
    if sip.isdeleted(dialog) or not dialog.isVisible():
        return
    controller = getattr(pet, 'mac_overlay', None)
    if controller and controller.enabled:
        # Apply before focusing, even if the deferred Show handler has not run.
        try:
            controller.apply(dialog)
        except Exception as exc:
            controller.fail(exc)
    dialog.raise_()
    if pet is not None:
        pet.focus_tool(dialog)
    else:
        dialog.activateWindow()


def prepare_dialog(dialog, pet, modal=False):
    if modal:
        # QMessageBox may select Qt.Sheet here. Do this BEFORE NSPanel setup.
        dialog.setWindowModality(Qt.WindowModality.WindowModal if dialog.parentWidget()
                                 else Qt.WindowModality.ApplicationModal)
    controller = getattr(pet, 'mac_overlay', None)
    if controller is not None:
        controller.prepare(dialog)


def exec_dialog(dialog, pet=None):
    pet = pet or companion(dialog)
    prepare_dialog(dialog, pet, modal=True)
    owner = dialog.parentWidget()
    focus = QTimer(dialog); focus.setSingleShot(True)
    focus.timeout.connect(lambda: bring_forward(dialog, pet))
    try:
        focus.start(0)
        return dialog.exec()
    finally:
        if not sip.isdeleted(focus):
            focus.stop(); focus.deleteLater()
        if (owner is not None and not sip.isdeleted(owner) and owner.isVisible()
                and not getattr(pet, 'closing', False)
                and QApplication.activeModalWidget() in (None, owner)):
            bring_forward(owner, pet)


def show_dialog(dialog, pet, quiet=False):
    prepare_dialog(dialog, pet)
    dialog.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, quiet)
    dialog.show()
    if not quiet:
        bring_forward(dialog, pet)


def message(owner, icon, title, text, buttons=QMessageBox.StandardButton.Ok,
            default=QMessageBox.StandardButton.Ok):
    parent = owner_window(owner)
    pet = companion(owner) or companion(parent)
    box = QMessageBox(parent)
    if sys.platform == 'darwin':
        box.setOption(QMessageBox.Option.DontUseNativeDialog, True)
    box.setStyleSheet(STYLE)
    box.setWindowTitle(title)
    box.setWindowIcon(parent.windowIcon() if parent is not None else QApplication.windowIcon())
    box.setIcon(icon)
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(text)
    box.setStandardButtons(buttons)
    box.setDefaultButton(default)
    try:
        return QMessageBox.StandardButton(exec_dialog(box, pet))
    finally:
        if not sip.isdeleted(box):
            box.deleteLater()


class Messages:
    """Consistent replacements for the static QMessageBox convenience calls."""
    @staticmethod
    def information(owner, title, text):
        return message(owner, QMessageBox.Icon.Information, title, text)

    @staticmethod
    def warning(owner, title, text):
        return message(owner, QMessageBox.Icon.Warning, title, text)

    @staticmethod
    def critical(owner, title, text):
        return message(owner, QMessageBox.Icon.Critical, title, text)

    @staticmethod
    def question(owner, title, text):
        return message(owner, QMessageBox.Icon.Question, title, text,
                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                       QMessageBox.StandardButton.No)


def choose_files(owner, title, mode='files', filename='', name_filter=''):
    parent = owner_window(owner)
    pet = companion(owner)
    dialog = QFileDialog(parent)
    # Qt-owned dialogs share overlay levels, including nested confirmations.
    if sys.platform == 'darwin':
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setWindowTitle(title); dialog.setStyleSheet(STYLE)
    if name_filter:
        dialog.setNameFilter(name_filter)
    if mode == 'folder':
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
    elif mode == 'save':
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setDefaultSuffix(Path(filename).suffix.lstrip('.'))
        # Own this confirmation too, so its parent and level are predictable.
        dialog.setOption(QFileDialog.Option.DontConfirmOverwrite, True)
        dialog.selectFile(filename)
    else:
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
    try:
        while exec_dialog(dialog, pet) == QDialog.DialogCode.Accepted:
            paths = dialog.selectedFiles()
            if mode != 'save' or not paths or not Path(paths[0]).exists():
                return paths
            if Messages.question(parent, 'Sostituisci file',
                                 'Il file esiste già. Sostituirlo?') == QMessageBox.StandardButton.Yes:
                return paths
        return []
    finally:
        if not sip.isdeleted(dialog):
            dialog.deleteLater()
