# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared visual language for the companion's windows and menus."""
from pathlib import Path
from PyQt6.QtCore import Qt, QSize, QRectF, QPointF, QTimer
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QToolButton,
    QVBoxLayout, QHBoxLayout, QAbstractSpinBox, QScrollArea)

STYLE = '''
QWidget { color: #edeaf4; font-size: 13px; }
QDialog { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
    stop:0 #211e30, stop:0.52 #242333, stop:1 #1d2a32); }
QLabel, QCheckBox, QTabWidget, QStackedWidget { background: transparent; }
QWidget#sidebar { background: rgba(20,19,30,135); border-radius: 14px; }
QFrame#card { background: rgba(45,41,61,170); border: 1px solid #464054; border-radius: 12px; }
QFrame#hero { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
    stop:0 #44334f, stop:0.55 #303044, stop:1 #2b4149);
    border: 1px solid #625470; border-radius: 16px; }
QLabel#brand { font-size: 19px; font-weight: 600; color: #f4e7e4; }
QLabel#muted, QLabel#feedback { color: #b8b2c8; }
QLabel#section { font-weight: 600; color: #c5bed6; }
QLabel#metric { font-size: 54px; font-weight: 300; color: #f0e9f4; }
QLabel#alert { color: #e3c293; }
QPushButton, QToolButton { background: #383348; border: 1px solid #51485f;
    border-radius: 7px; padding: 7px 12px; min-height: 19px; }
QPushButton:hover, QToolButton:hover { background: #494158; border-color: #8b749d; }
QPushButton:pressed, QToolButton:pressed { background: #50425f; }
QPushButton:focus, QToolButton:focus { border-color: #bad5d7; }
QPushButton:disabled, QToolButton:disabled { color: #81788e; background: #2c2939; border-color: #3e394c; }
QPushButton[role="primary"] { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
    stop:0 #806294, stop:1 #655682); border: 1px solid #b09cba; color: #ffffff; font-weight: 600; }
QPushButton[role="primary"]:hover { background: #8b6ca0; }
QPushButton[role="primary"]:disabled { background: #3f374d; border-color: #51485f; color: #81788e; }
QPushButton[role="quiet"], QToolButton[role="quiet"] { background: transparent; border-color: transparent; }
QPushButton[role="quiet"]:hover, QToolButton[role="quiet"]:hover { background: #383348; border-color: #51485f; }
QPushButton[role="nav"] { text-align: left; background: transparent;
    border: 1px solid transparent; padding: 10px 12px; color: #c1bace; }
QPushButton[role="nav"]:hover { background: #312c40; }
QPushButton[role="nav"]:checked { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
    stop:0 #514064, stop:1 #39394e); border-color: #635571; color: #ffffff; }
QLineEdit, QTextEdit, QListWidget, QTreeWidget, QDateTimeEdit, QSpinBox, QComboBox {
    background: #211f2e; border: 1px solid #4b435a; border-radius: 7px;
    padding: 7px; selection-background-color: #68547d; selection-color: #ffffff; }
QLineEdit:focus, QTextEdit:focus, QDateTimeEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #a99ac1; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled { color: #8e849c; border-color: #3e394c; }
QSpinBox#tempo { background: transparent; border: none; font-size: 42px; font-weight: 300; }
QComboBox { padding-right: 24px; }
QComboBox::drop-down { width: 24px; border: none; }
QComboBox::down-arrow, QDateTimeEdit::down-arrow { image: url("ASSET_DIR/chevron-down.svg"); width: 14px; height: 14px; }
QSpinBox::up-button, QDateTimeEdit::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 19px; border: none; }
QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 19px; border: none; }
QSpinBox::up-arrow, QDateTimeEdit::up-arrow { image: url("ASSET_DIR/chevron-up.svg"); width: 11px; height: 11px; }
QSpinBox::down-arrow { image: url("ASSET_DIR/chevron-down.svg"); width: 11px; height: 11px; }
QDateTimeEdit::drop-down { width: 26px; border: none; }
QToolButton::menu-indicator { image: url("ASSET_DIR/chevron-down.svg"); width: 11px; height: 11px;
    subcontrol-origin: padding; subcontrol-position: center right; right: 5px; }
QToolButton[compact="true"]::menu-indicator { image: none; }
QCalendarWidget QWidget { background: #302a3f; color: #eee7f3; }
QCalendarWidget QAbstractItemView { selection-background-color: #735c88; alternate-background-color: #393147; }
QComboBox QAbstractItemView { background: #2e293d; selection-background-color: #67527d; }
QListWidget, QTreeWidget { padding: 5px; outline: 0; }
QListWidget::item { padding: 10px 8px; border-radius: 5px; }
QTreeWidget::item { padding: 8px 6px; }
QListWidget::item:selected, QTreeWidget::item:selected { background: #534263; color: #ffffff; }
QListWidget::item:hover, QTreeWidget::item:hover { background: #3b334a; }
QHeaderView::section { background: #2c283b; color: #bfb6cd; padding: 8px;
    border: none; border-bottom: 1px solid #4b435a; }
QCheckBox { spacing: 9px; padding: 4px 0; }
QCheckBox::indicator { width: 17px; height: 17px; }
QCheckBox::indicator:unchecked { border: 1px solid #8a7d9c; border-radius: 5px; background: #211f2e; }
QCheckBox::indicator:checked { image: url("ASSET_DIR/check.svg"); border: 1px solid #b5a4c4; border-radius: 5px; background: #706184; }
QCheckBox::indicator:disabled { border-color: #61596d; }
QScrollArea { background: transparent; border: none; }
QWidget#scrollContent { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #675971; border-radius: 4px; min-height: 32px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QSlider::groove:horizontal { height: 4px; background: #4e455e; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #9e8cb6; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; height: 14px; margin: -5px 0;
    background: #b7d1d4; border: 1px solid #d2e5e6; border-radius: 7px; }
QSplitter::handle { background: transparent; width: 10px; }
QMenu { background: #2b2638; border: 1px solid #655371; border-radius: 7px; padding: 5px; }
QMenu::item { padding: 7px 25px 7px 12px; border-radius: 4px; }
QMenu::item:selected { background: #554265; }
QMenu::item:disabled { color: #84788f; }
QMenu::separator { height: 1px; background: #4e435b; margin: 5px 9px; }
QToolTip { color: #eee7f3; background: #342c44; border: 1px solid #887495; padding: 5px; }
QTabWidget::pane { border: none; }
'''.replace('ASSET_DIR',(Path(__file__).parent/'assets'/'ui').as_posix())


def icon(name, color='#c8bfd7'):
    """Small, native vector marks: consistent on Windows, macOS and Linux."""
    pix = QPixmap(48, 48)
    pix.fill(Qt.GlobalColor.transparent)
    pix.setDevicePixelRatio(2)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color), 1.65, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    def line(a,b,c,d): p.drawLine(QPointF(a,b),QPointF(c,d))
    def poly(points): p.drawPolyline(QPolygonF([QPointF(*v) for v in points]))
    if name in ('note','file'):
        p.drawRoundedRect(QRectF(5,3,14,18),2,2)
        if name=='note':
            for y in (8,12,16): line(8,y,16,y)
    elif name=='bell':
        path=QPainterPath(QPointF(5,17));path.lineTo(7,14);path.lineTo(7,10)
        path.cubicTo(7,3,17,3,17,10);path.lineTo(17,14);path.lineTo(19,17);path.closeSubpath()
        p.drawPath(path);line(10,20,14,20);line(12,3,12,4)
    elif name in ('focus','clock'):
        p.drawEllipse(QRectF(4,5,16,16));line(12,8,12,13);line(12,13,16,15)
        if name=='clock': line(9,2,15,2);line(12,2,12,5)
    elif name=='metro':
        poly([(5,21),(9,3),(14,3),(19,21),(5,21)]);line(10,17,19,5);line(15,7,19,10)
    elif name=='voice':
        p.drawRoundedRect(QRectF(9,3,6,12),3,3)
        path=QPainterPath(QPointF(6,11));path.cubicTo(6,21,18,21,18,11);p.drawPath(path)
        line(12,19,12,22);line(9,22,15,22)
    elif name=='settings':
        for x,y in ((5,9),(12,15),(19,7)):
            line(x,3,x,y-2);line(x,y+2,x,21);p.drawEllipse(QRectF(x-2,y-2,4,4))
    elif name=='help':
        p.drawEllipse(QRectF(3,3,18,18));path=QPainterPath(QPointF(9,9))
        path.cubicTo(9,4,18,7,13,11);path.quadTo(12,12,12,14);p.drawPath(path);line(12,17,12,17.2)
    elif name=='folder': poly([(3,7),(10,7),(12,9),(21,9),(20,20),(3,20),(3,7)])
    elif name=='copy':
        p.drawRoundedRect(QRectF(8,7,12,14),2,2);poly([(15,4),(4,4),(4,17)])
    elif name=='plus': line(12,5,12,19);line(5,12,19,12)
    elif name=='close': line(6,6,18,18);line(6,18,18,6)
    elif name=='check': poly([(5,12),(10,17),(20,6)])
    elif name=='more':
        for x in (5,12,19):p.drawEllipse(QRectF(x-0.6,11.4,1.2,1.2))
    elif name=='play': poly([(8,4),(20,12),(8,20),(8,4)])
    elif name=='stop': p.drawRoundedRect(QRectF(6,6,12,12),1,1)
    elif name=='pause': line(8,5,8,19);line(16,5,16,19)
    elif name=='reset':
        p.drawArc(QRectF(4,4,16,16),40*16,285*16);poly([(18,3),(18,8),(13,8)])
    elif name=='export':
        poly([(4,14),(4,21),(20,21),(20,14)]);line(12,3,12,16);poly([(7,8),(12,3),(17,8)])
    elif name=='volume':
        poly([(3,9),(7,9),(12,5),(12,19),(7,15),(3,15),(3,9)])
        p.drawArc(QRectF(9,6,10,12),-65*16,130*16)
    elif name=='spark':
        poly([(12,3),(14,10),(21,12),(14,14),(12,21),(10,14),(3,12),(10,10),(12,3)])
    elif name=='chevron': poly([(8,10),(12,14),(16,10)])
    p.end()
    return QIcon(pix)


def button(text, callback, layout=None, *, glyph=None, role=None):
    b=QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAutoDefault(False)
    if glyph:b.setIcon(icon(glyph))
    if role:b.setProperty('role',role)
    if callback:b.clicked.connect(callback)
    if layout is not None:layout.addWidget(b)
    return b


def icon_button(glyph, label, callback=None, layout=None):
    b=button('',callback,layout,glyph=glyph,role='quiet')
    b.setFixedSize(34,34)
    b.setAccessibleName(label);b.setToolTip(label)
    b.setStyleSheet('padding: 6px;')
    return b


def menu_button(text, menu, layout=None, *, glyph='more'):
    b=QToolButton();b.setText(text);b.setIcon(icon(glyph))
    b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon if text else Qt.ToolButtonStyle.ToolButtonIconOnly)
    b.setMenu(menu);b.setCursor(Qt.CursorShape.PointingHandCursor)
    if not text:
        b.setFixedSize(34,34);b.setProperty('compact',True);b.setStyleSheet('QToolButton { padding: 6px; }')
    else:b.setStyleSheet('QToolButton { padding-right: 22px; }')
    if layout is not None:layout.addWidget(b)
    return b


def plain_label(text='', name=None):
    lab=QLabel(text);lab.setTextFormat(Qt.TextFormat.PlainText);lab.setWordWrap(True)
    if name:lab.setObjectName(name)
    return lab


class FeedbackLabel(QLabel):
    """Show useful feedback only when there is a result to report."""
    def __init__(self):
        super().__init__();self.setObjectName('feedback');self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.hide_timer=QTimer(self);self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide);self.hide()
    def setText(self,text):
        super().setText(text);self.setVisible(bool(text))
        self.hide_timer.stop()
        if text and not any(word in text.lower() for word in ('errore','non riuscito','non salvato')):
            self.hide_timer.start(5000)


def card(parent_layout=None, *, hero=False):
    frame=QFrame();frame.setObjectName('hero' if hero else 'card')
    layout=QVBoxLayout(frame);layout.setContentsMargins(18,16,18,16);layout.setSpacing(12)
    if parent_layout is not None:parent_layout.addWidget(frame)
    return frame,layout


def scroll_page(content):
    content.setObjectName('scrollContent')
    scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(content)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    return scroll


def stepper(spin):
    spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
    container=QWidget();row=QHBoxLayout(container)
    row.setContentsMargins(0,0,0,0);row.setSpacing(6);row.addWidget(spin,1)
    for text,delta,name in [('−',-1,'Diminuisci'),('+',1,'Aumenta')]:
        control=button(text,lambda checked=False,d=delta:spin.stepBy(d),row)
        control.setAccessibleName(name);control.setToolTip(name)
        control.setFixedWidth(34);control.setStyleSheet('padding: 7px 0;')
        control.setAutoRepeat(True)
    return container


class BeatIndicator(QWidget):
    def __init__(self):
        super().__init__();self.position=-1;self.group=4
        self.setMinimumHeight(24);self.setAccessibleName('Battiti')
    def set_beat(self,position,group):
        self.position=position;self.group=group;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n=max(1,min(12,self.group));step=22;start=(self.width()-(n-1)*step)/2
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(n):
            active=self.position>=0 and (i==self.position%n if self.group else i==0)
            p.setBrush(QColor('#e5c798' if active and self.position==0 else '#b1d0d3' if active else '#605369'))
            radius=5 if active else 3.5
            p.drawEllipse(QPointF(start+i*step,self.height()/2),radius,radius)
        p.end()
