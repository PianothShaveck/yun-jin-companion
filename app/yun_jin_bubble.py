# SPDX-License-Identifier: GPL-3.0-or-later
"""A passive speech caption. Repositions on window events; no polling timer."""
from PyQt6.QtCore import QEvent, QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget, QLabel


class SpeechBubble(QWidget):
    def __init__(self, pet):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus
                         | Qt.WindowType.WindowTransparentForInput)
        self.pet = pet
        pet.destroyed.connect(self.deleteLater)
        self.text = ''
        self.tail_top = False
        self.tail_x = 30
        self.detached = False
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle('Yun Jin')
        self.label = QLabel(self)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        self.label.setStyleSheet('color: #392d48; background: transparent; font-size: 14px;')
        pet.installEventFilter(self)

    def present(self, text):
        self.text = text
        hidden=self.pet.character_hidden or self.pet.fullscreen_hidden
        if not text or (not self.pet.isVisible() and not hidden) or self.pet.closing:
            self.hide()
            return
        self.label.setText(text)
        self.setAccessibleName(text)
        self.place()
        self.show()  # Deliberately does not activate or focus any window.

    def place(self):
        screen = self.pet.current_screen().availableGeometry()
        width = min(290, max(80, screen.width()-16))
        fm = self.label.fontMetrics()
        flags = Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextWrapAnywhere
        height = fm.boundingRect(QRect(0, 0, width-30, 1000), flags, self.text).height()+38
        height = min(height, max(40, screen.height()-16))
        self.setFixedSize(width, height)
        self.detached=self.pet.character_hidden or self.pet.fullscreen_hidden
        if self.detached:
            self.tail_top=False
            self.label.setGeometry(15,19,width-30,height-38)
            self.move(*self.pet.notification_position(self))
            self.update()
            return
        px = self.pet.x()+self.pet.width()//2
        x = max(screen.left()+8, min(px-width//2, screen.right()-width-7))
        y = self.pet.y()-height-6
        self.tail_top = y < screen.top()+8
        if self.tail_top:
            y = self.pet.y()+self.pet.height()+6
        y = max(screen.top()+8, min(y, screen.bottom()-height-7))
        self.tail_x = max(20, min(px-x, width-20))
        self.label.setGeometry(15, 23 if self.tail_top else 13, width-30, height-38)
        self.move(x, y)
        self.update()

    def eventFilter(self, obj, event):
        if obj is self.pet:
            kind = event.type()
            if kind == QEvent.Type.Hide and (self.pet.character_hidden or self.pet.fullscreen_hidden):
                self.present(self.text)
            elif kind in (QEvent.Type.Hide, QEvent.Type.Close):
                self.hide()
            elif kind == QEvent.Type.Show and self.text:
                self.present(self.text)
            elif kind in (QEvent.Type.Move, QEvent.Type.Resize):
                if self.isVisible(): self.place()
        return False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        if self.detached:
            path.addRoundedRect(QRectF(1,1,self.width()-2,self.height()-2),13,13)
            painter.setPen(QPen(QColor('#b5a5c7'),1));painter.setBrush(QColor('#fffaf4'))
            painter.drawPath(path)
            return
        y = 11 if self.tail_top else 1
        path.addRoundedRect(QRectF(1, y, self.width()-2, self.height()-12), 13, 13)
        tail = QPainterPath()
        edge = 12 if self.tail_top else self.height()-12
        tip = 1 if self.tail_top else self.height()-1
        tail.moveTo(self.tail_x-8, edge)
        tail.lineTo(self.tail_x, tip)
        tail.lineTo(self.tail_x+8, edge)
        tail.closeSubpath()
        painter.setPen(QPen(QColor('#b5a5c7'), 1))
        painter.setBrush(QColor('#fffaf4'))
        painter.drawPath(path.united(tail))
