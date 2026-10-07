# SPDX-License-Identifier: GPL-3.0-or-later
"""Native, lazy weather page. Small tables and at most three decoded illustrations."""
from collections import OrderedDict
from functools import lru_cache
import math
import time
from PyQt6.QtCore import Qt,QTimer,QDateTime,QTimeZone,QSize,QRectF,QPointF,QUrl,QLocale
from PyQt6.QtGui import QPixmap,QImageReader,QPainter,QPainterPath,QPen,QColor,QIcon
from PyQt6.QtWidgets import (QWidget,QLabel,QVBoxLayout,QHBoxLayout,QGridLayout,QToolButton,QTreeWidget,
                             QTreeWidgetItem,QHeaderView,QAbstractItemView,QSizePolicy,QDialog)
from yun_jin_core import BASE
from yun_jin_ui import plain_label,button,icon_button,card,scroll_page
from yun_jin_forecast import condition,cache_valid,FORECAST_TTL
from yun_jin_weather import location_label


def value(number,suffix='',decimals=0):
    if type(number) not in (int,float) or not math.isfinite(number):return '—'
    return (f'{number:.{decimals}f}'.replace('.',',')+suffix)


@lru_cache(maxsize=20)
def weather_icon(key):
    """Compact weather symbols for hourly rows; the hero uses generated artwork."""
    pix=QPixmap(64,64);pix.fill(Qt.GlobalColor.transparent);pix.setDevicePixelRatio(2)
    p=QPainter(pix);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor('#ccd4e4'),1.6));p.setBrush(Qt.BrushStyle.NoBrush)
    if not key:p.drawText(QRectF(0,0,32,32),Qt.AlignmentFlag.AlignCenter,'—');p.end();return QIcon(pix)
    if key in ('sun','partly_cloudy'):
        p.setPen(QPen(QColor('#f3cf79'),1.5));p.setBrush(QColor('#f3cf79'));p.drawEllipse(QRectF(7,5,12,12))
        for angle in range(0,360,45):
            a=math.radians(angle);p.drawLine(QPointF(13+9*math.cos(a),11+9*math.sin(a)),QPointF(13+11*math.cos(a),11+11*math.sin(a)))
    elif key in ('clear_night','partly_cloudy_night'):
        path=QPainterPath();path.addEllipse(QRectF(5,2,19,19));cut=QPainterPath();cut.addEllipse(QRectF(12,0,18,18))
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#d9deef'));p.drawPath(path.subtracted(cut))
    if key not in ('sun','clear_night','wind'):
        p.setPen(QPen(QColor('#b8c2d8'),1));p.setBrush(QColor('#b8c2d8'))
        cloud=QPainterPath(QPointF(5,20));cloud.cubicTo(0,20,0,12,7,12);cloud.cubicTo(8,3,20,5,20,12)
        cloud.cubicTo(30,8,33,21,26,21);cloud.lineTo(5,21);p.drawPath(cloud)
    if key in ('drizzle','rain','heavy_rain','freezing_rain','sleet','thunderstorm','storm_hail'):
        p.setPen(QPen(QColor('#79c6e5'),1.8))
        for x in (8,16,24):p.drawLine(QPointF(x,24),QPointF(x-2,28 if key=='drizzle' else 31))
    if key in ('snow','heavy_snow','sleet','storm_hail','freezing_rain'):
        p.setPen(QPen(QColor('#eef5ff'),1.4))
        for x in (7,16,25):
            p.drawLine(QPointF(x-2,27),QPointF(x+2,27));p.drawLine(QPointF(x,25),QPointF(x,29))
    if key in ('thunderstorm','storm_hail'):
        path=QPainterPath(QPointF(17,16));path.lineTo(11,25);path.lineTo(17,24);path.lineTo(14,32);path.lineTo(23,21);path.lineTo(17,22);path.closeSubpath()
        p.setBrush(QColor('#f5d37d'));p.setPen(Qt.PenStyle.NoPen);p.drawPath(path)
    if key in ('fog','wind'):
        p.setPen(QPen(QColor('#b9d7dd'),1.6))
        for i in range(3):p.drawLine(QPointF(3+i*2,19+i*5),QPointF(28-i*2,19+i*5))
    p.end();return QIcon(pix)


class TemperatureChart(QWidget):
    def __init__(self):
        super().__init__();self.rows=[];self.labels=[];self.setMinimumHeight(132)
        self.setAccessibleName('Andamento orario della temperatura')

    def set_rows(self,rows,labels):self.rows=rows;self.labels=labels;self.update()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        temps=[row.get('temperature_2m') for row in self.rows]
        available=[v for v in temps if v is not None]
        if not available:p.end();return
        lo=min(available)-2;hi=max(available)+2;w=max(1,self.width()-60);h=self.height()-43
        def point(i,v):return QPointF(32+i*w/max(1,len(temps)-1),10+(hi-v)/(hi-lo)*h)
        p.setPen(QPen(QColor('#494256'),1))
        for v in (min(available),max(available)):
            y=point(0,v).y();p.drawLine(QPointF(30,y),QPointF(self.width()-12,y))
            p.setPen(QColor('#c6bfce'));p.drawText(QRectF(0,y-9,28,20),Qt.AlignmentFlag.AlignRight,value(v,'°'));p.setPen(QColor('#494256'))
        path=QPainterPath();connected=False
        for i,v in enumerate(temps):
            if v is None:connected=False;continue
            pt=point(i,v)
            if connected:path.lineTo(pt)
            else:path.moveTo(pt)
            connected=True
        p.setPen(QPen(QColor('#ebbed8'),2.5));p.drawPath(path)
        p.setBrush(QColor('#ebbed8'))
        for i in sorted(set((0,len(temps)//4,len(temps)//2,3*len(temps)//4,len(temps)-1))):
            if temps[i] is not None:p.drawEllipse(point(i,temps[i]),2.7,2.7)
            x=point(i,lo).x();p.setPen(QColor('#c6bfce'))
            p.drawText(QRectF(x-23,self.height()-24,46,22),Qt.AlignmentFlag.AlignCenter,self.labels[i])
        p.end()


class DayStrip(QWidget):
    def __init__(self):
        super().__init__();self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,0,0)
        self.grid.setSpacing(6);self.buttons=[];self.columns=4

    def add(self,button):
        i=len(self.buttons);self.buttons.append(button);self.grid.addWidget(button,i//self.columns,i%self.columns)

    def resizeEvent(self,event):
        super().resizeEvent(event);self.reflow()

    def reflow(self):
        columns=7 if self.width()>=620 else 4
        if columns!=self.columns:
            self.columns=columns
            for i,button in enumerate(self.buttons):
                self.grid.removeWidget(button);self.grid.addWidget(button,i//columns,i%columns)
        if self.buttons:
            rows=(len(self.buttons)+columns-1)//columns
            self.setFixedHeight(rows*max(b.sizeHint().height() for b in self.buttons)+6*(rows-1))
        self.updateGeometry()


class WeatherPanel(QWidget):
    def __init__(self,pet):
        super().__init__();self.pet=pet;self.date=None;self.art=OrderedDict();self.signature=None
        from yun_jin_forecast_service import ForecastService
        if getattr(pet.context,'forecast',None) is None:pet.context.forecast=ForecastService(pet)
        self.service=pet.context.forecast
        self.zone=QTimeZone.utc();self.locale=QLocale(QLocale.Language.Italian,QLocale.Country.Italy)
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(12)
        head=QHBoxLayout();head.setSpacing(12)
        self.city=button('',self.choose_city,head,role='quiet');self.city.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        head.setStretch(0,1)
        self.updated=plain_label('','muted');head.addWidget(self.updated)
        self.refresh_button=icon_button('reset','Aggiorna previsioni',lambda:self.service.request(True),head)
        root.addLayout(head)
        body=QWidget();body.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        main=QVBoxLayout(body);main.setContentsMargins(0,0,4,0);main.setSpacing(14)
        self.notice=plain_label('','muted');main.addWidget(self.notice)
        self.hero,hero=card(main,hero=True);row=QHBoxLayout();row.setSpacing(18);hero.addLayout(row)
        self.picture=QLabel();self.picture.setFixedSize(184,184);self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.picture)
        text=QVBoxLayout();text.setSpacing(5);row.addLayout(text,1)
        self.when=plain_label('','muted');text.addWidget(self.when)
        self.temperature=plain_label('','metric');text.addWidget(self.temperature)
        self.description=plain_label('','section');text.addWidget(self.description)
        self.details=plain_label('','muted');text.addWidget(self.details);text.addStretch()
        self.day_box=DayStrip()
        self.days=[]
        for i in range(7):
            b=QToolButton();b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon);b.setIconSize(QSize(28,28))
            b.setCheckable(True);b.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
            b.setStyleSheet('QToolButton {padding:6px 2px;} QToolButton:checked {background:#655277;border-color:#c1a3c8;}')
            b.clicked.connect(lambda checked=False,index=i:self.select_day(index));self.day_box.add(b);self.days.append(b)
        main.addWidget(self.day_box)
        self.hour_title=plain_label('Ora per ora','section');main.addWidget(self.hour_title)
        self.chart=TemperatureChart();main.addWidget(self.chart)
        self.hours=QTreeWidget();self.hours.setRootIsDecorated(False);self.hours.setAlternatingRowColors(False)
        self.hours.setColumnCount(6);self.hours.setHeaderLabels(['Ora','Meteo','°C','Precip.','mm','Vento'])
        self.hours.setAccessibleName('Previsioni orarie');self.hours.setUniformRowHeights(True)
        self.hours.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.hours.setIconSize(QSize(26,26))
        self.hours.setMinimumHeight(240);self.hours.setMaximumHeight(310)
        self.hours.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.hours.header().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.hours.headerItem().setToolTip(3,'Probabilità di precipitazioni nell’ora.')
        self.hours.headerItem().setToolTip(4,'Precipitazioni totali nell’ora, in millimetri.')
        self.hours.currentItemChanged.connect(self.select_hour);main.addWidget(self.hours)
        self.sun_times=plain_label('','muted');main.addWidget(self.sun_times)
        main.addStretch();root.addWidget(scroll_page(body),1)
        credit=QLabel('<a href="https://open-meteo.com/" style="color:#b8b2c8">Open-Meteo · Best Match</a>')
        credit.setOpenExternalLinks(False);credit.setToolTip('Modelli selezionati da Open-Meteo in base alla località. Condizioni attuali stimate dal modello.')
        credit.linkActivated.connect(lambda url:pet.open_external(QUrl(url),self));root.addWidget(credit)
        self.service.changed.connect(self.changed)
        self.timer=QTimer(self);self.timer.setInterval(60000);self.timer.setTimerType(Qt.TimerType.VeryCoarseTimer)
        self.timer.timeout.connect(self.tick)

    def local(self,stamp):return QDateTime.fromSecsSinceEpoch(int(stamp),self.zone)
    def day_key(self,stamp):return self.local(stamp).toString('yyyy-MM-dd')

    def showEvent(self,event):
        super().showEvent(event);self.timer.start();self.changed();self.service.request()

    def hideEvent(self,event):self.timer.stop();super().hideEvent(event)

    def tick(self):
        if not self.isVisible():return
        self.changed();self.service.request()

    def choose_city(self):
        from yun_jin_weather_ui import CityDialog
        from yun_jin_dialogs import exec_dialog
        dialog=CityDialog(self.pet,self)
        try:
            if exec_dialog(dialog,self.pet)==QDialog.DialogCode.Accepted:self.pet.context.set_weather_location(dialog.selection)
        finally:dialog.deleteLater()
        if self.isVisible():self.service.request()

    def changed(self):
        if not self.isVisible():self.signature=None;return
        data=self.service.data;location=self.service.location
        self.city.setText((location['city'] if location else 'Città')+'…')
        self.city.setToolTip(location_label(location) if location else '')
        valid=cache_valid(data,location)
        for widget in (self.hero,self.day_box,self.hour_title,self.chart,self.hours,self.sun_times):widget.setVisible(valid)
        self.refresh_button.setEnabled(self.service.process is None)
        if not valid:
            self.notice.setText('Caricamento…' if self.service.process is not None else 'Previsioni non disponibili.')
            self.notice.show();self.updated.clear();self.signature=None;return
        self.notice.hide();self.zone=QTimeZone(data['timezone'].encode())
        if not self.zone.isValid():self.zone=QTimeZone(data.get('utc_offset_seconds',0))
        age=time.time()-data['checked'];prefix='Dati salvati · ' if age>=FORECAST_TTL or self.service.failed else 'Aggiornato '
        stamp=self.local(data['checked'])
        self.updated.setText(prefix+stamp.toString('HH:mm' if self.day_key(data['checked'])==self.day_key(time.time()) else 'dd/MM HH:mm'))
        self.updated.setToolTip('Orari di '+location['city'])
        signature=(data['checked'],int(time.time()//3600))
        if signature==self.signature:return
        self.signature=signature
        for i,b in enumerate(self.days):
            b.setVisible(i<len(data['daily']))
            if i>=len(data['daily']):continue
            row=data['daily'][i];day=self.local(row['time']);key=self.day_key(row['time'])
            label='Oggi' if key==self.day_key(time.time()) else self.locale.toString(day.date(),'ddd d')
            text,art=condition(row,1);b.setIcon(weather_icon(art))
            b.setText(label+'\n'+value(row.get('temperature_2m_min'),'°')+' / '+value(row.get('temperature_2m_max'),'°'))
            b.setToolTip(text+' · Min / Max');b.setAccessibleName(label+': '+text)
        self.day_box.reflow()
        matches=[i for i,r in enumerate(data['daily']) if self.day_key(r['time'])==self.date]
        if not matches:matches=[i for i,r in enumerate(data['daily']) if self.day_key(r['time'])==self.day_key(time.time())]
        self.select_day(matches[0] if matches else 0)

    def select_day(self,index):
        data=self.service.data
        if not data or index>=len(data['daily']):return
        row=data['daily'][index];self.date=self.day_key(row['time'])
        for i,b in enumerate(self.days):b.setChecked(i==index)
        rows=[r for r in data['hourly'] if self.day_key(r['time'])==self.date
              and r['time']>time.time()-3600]
        self.hours.blockSignals(True);self.hours.clear()
        for hour in rows:
            description,art=condition(hour)
            item=QTreeWidgetItem([self.local(hour['time']).toString('HH:mm'),description,
                value(hour.get('temperature_2m')),value(hour.get('precipitation_probability'),'%'),
                value(hour.get('precipitation'),decimals=1),value(hour.get('wind_speed_10m'),' km/h')])
            item.setIcon(1,weather_icon(art));item.setData(0,Qt.ItemDataRole.UserRole,hour)
            item.setToolTip(0,self.local(hour['time']).toString('dd/MM HH:mm t'))
            for col in range(2,6):item.setTextAlignment(col,Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
            self.hours.addTopLevelItem(item)
        self.hours.blockSignals(False)
        self.chart.set_rows(rows,[self.local(r['time']).toString('HH') for r in rows])
        self.hour_title.setText('Ora per ora · '+self.locale.toString(self.local(row['time']).date(),'dddd d'))
        sun=lambda key:self.local(row[key]).toString('HH:mm') if row.get(key) is not None else '—'
        self.sun_times.setText('Alba '+sun('sunrise')+'   ·   Tramonto '+sun('sunset')+'   ·   UV '+value(row.get('uv_index_max'),decimals=1))
        if self.date==self.day_key(data['current']['time']):self.show_conditions(data['current'])
        else:self.show_conditions(row,daily=True)

    def select_hour(self,item,previous):
        if item:self.show_conditions(item.data(0,Qt.ItemDataRole.UserRole))

    def show_conditions(self,row,daily=False):
        description,key=condition(row,1 if daily else None)
        self.when.setText(self.locale.toString(self.local(row['time']),'dddd d MMM'+('' if daily else ' · HH:mm')))
        self.temperature.setText(value(row.get('temperature_2m_max' if daily else 'temperature_2m'),'°'))
        self.description.setText(description)
        if daily:
            details='Min '+value(row.get('temperature_2m_min'),'°')+' · Max '+value(row.get('temperature_2m_max'),'°')
            details+='\nPrecip. '+value(row.get('precipitation_probability_max'),'%')+' · '+value(row.get('precipitation_sum'),' mm',1)
            details+='\nVento '+value(row.get('wind_speed_10m_max'),' km/h')+' · Raffiche '+value(row.get('wind_gusts_10m_max'),' km/h')
        else:
            details='Percepita '+value(row.get('apparent_temperature'),'°')+' · Umidità '+value(row.get('relative_humidity_2m'),'%')
            details+='\nVento '+value(row.get('wind_speed_10m'),' km/h')+' · Raffiche '+value(row.get('wind_gusts_10m'),' km/h')
            details+='\nPrecip. '+value(row.get('precipitation'),' mm',1)
        self.details.setText(details)
        self.picture.clear();self.picture.setToolTip(description)
        if key:
            if key not in self.art:
                reader=QImageReader(str(BASE/'assets/weather'/f'{key}.webp'));reader.setScaledSize(QSize(368,368))
                pix=QPixmap.fromImage(reader.read());pix.setDevicePixelRatio(2);self.art[key]=pix
                while len(self.art)>3:self.art.popitem(last=False)
            self.art.move_to_end(key);self.picture.setPixmap(self.art[key])
