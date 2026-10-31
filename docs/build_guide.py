#!/usr/bin/env python3
"""Build the three version-independent guides from their maintained text sources."""
from pathlib import Path
from html import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = {'it': ('Guida.pdf', 'Guida', 'Indice'), 'en': ('Guide.pdf', 'User guide', 'Contents'),
             'zh-CN': ('Guide.zh-CN.pdf', '使用指南', '目录')}
INK, ACCENT = HexColor('#302a3f'), HexColor('#715583')
W, H = 595.276, 841.89


def build(language):
    filename, title, contents = LANGUAGES[language]
    chinese = language == 'zh-CN'
    if chinese:
        font_paths = [ROOT/'docs/fonts'/f'NotoSansSC-{weight}.ttf' for weight in ('Regular', 'Semibold')]
    else:
        font_paths = [Path('/usr/share/fonts/truetype/dejavu')/name for name in ('DejaVuSans.ttf','DejaVuSans-Bold.ttf')]
    regular, bold = language+'-Text', language+'-Bold'
    for name, path in zip((regular,bold),font_paths):
        pdfmetrics.registerFont(TTFont(name,str(path)))
    styles = dict(
        body=ParagraphStyle('body',fontName=regular,fontSize=10.1,leading=15.7,textColor=INK,spaceAfter=9,wordWrap='CJK' if chinese else None),
        heading=ParagraphStyle('heading',fontName=bold,fontSize=12,leading=17,textColor=ACCENT,spaceBefore=9,spaceAfter=6,keepWithNext=True),
        chapter=ParagraphStyle('chapter',fontName=bold,fontSize=24,leading=31,textColor=INK,spaceAfter=23,keepWithNext=True),
        cover=ParagraphStyle('cover',fontName=bold,fontSize=32,leading=40,textColor=INK,spaceAfter=12),
        contents=ParagraphStyle('contents',fontName=regular,fontSize=11,leading=25,textColor=INK),
    )
    source=(ROOT/'docs/guides'/f'{language}.txt').read_text(encoding='utf-8')
    chapters=[line[2:] for line in source.splitlines() if line.startswith('# ')]
    doc=SimpleDocTemplate(str(ROOT/filename),pagesize=(W,H),leftMargin=46,rightMargin=46,
                          topMargin=58,bottomMargin=50,title='Yun Jin Companion — '+title,
                          author='Yun Jin Companion',pageCompression=1)
    def frame(canvas, document):
        canvas.setFillColor(ACCENT);canvas.rect(46,H-32,38,3,fill=1,stroke=0)
        canvas.setFont(regular,8);canvas.setFillColor(INK)
        canvas.drawString(46,27,'Yun Jin Companion')
        canvas.drawRightString(W-46,27,str(document.page))
    story=[Spacer(1,32),Paragraph('Yun Jin<br/>Companion',styles['cover']),Paragraph(title,styles['chapter'])]
    art=ROOT/'docs/art/conduct16.png'
    if art.is_file():
        image=Image(str(art));scale=min(150/image.imageWidth,150/image.imageHeight)
        image.drawWidth=image.imageWidth*scale;image.drawHeight=image.imageHeight*scale
        image.hAlign='RIGHT';story += [image]
    story += [Spacer(1,16),Paragraph(contents,styles['heading'])]
    story += [Paragraph(f'{i:02d}　{escape(chapter)}',styles['contents']) for i,chapter in enumerate(chapters,1)]
    for line in source.splitlines():
        if line.startswith('# '):
            story += [PageBreak(),Paragraph(escape(line[2:]),styles['chapter'])]
        elif line.startswith('## '):
            story.append(Paragraph(escape(line[3:]),styles['heading']))
        elif line.strip():
            story.append(Paragraph(escape(line),styles['body']))
    doc.build(story,onFirstPage=frame,onLaterPages=frame)
    print(ROOT/filename)


if __name__=='__main__':
    for language in LANGUAGES:build(language)
