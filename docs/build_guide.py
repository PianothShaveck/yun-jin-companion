#!/usr/bin/env python3
"""Build the version-independent user guide. Screenshots come from render_guide_assets.py."""
from pathlib import Path
from reportlab.platypus import (BaseDocTemplate,PageTemplate,Frame,Paragraph,
    Spacer,PageBreak,Table,TableStyle,Image)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor,white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage

ROOT=Path(__file__).resolve().parents[1];ART=ROOT/'docs/art';OUT=ROOT/'Guida.pdf'
for name,file in [('Text','DejaVuSans.ttf'),('Bold','DejaVuSans-Bold.ttf')]:
    pdfmetrics.registerFont(TTFont(name,'/usr/share/fonts/truetype/dejavu/'+file))
pdfmetrics.registerFontFamily('Text',normal='Text',bold='Bold',italic='Text',boldItalic='Bold')
W,H=595.276,841.89;BW=W-88
INK=HexColor('#302a3f');PURPLE=HexColor('#715583');TEAL=HexColor('#3e777e')
LINE=HexColor('#dfd6e6');PAPER=HexColor('#fcfaf8')
S={
    'p':ParagraphStyle('p',fontName='Text',fontSize=10,leading=15,textColor=INK,spaceAfter=9),
    'small':ParagraphStyle('small',fontName='Text',fontSize=8.7,leading=12.5,textColor=INK,spaceAfter=8),
    'h':ParagraphStyle('h',fontName='Bold',fontSize=12,leading=16,textColor=PURPLE,spaceBefore=12,spaceAfter=7,keepWithNext=True),
    'cell':ParagraphStyle('cell',fontName='Text',fontSize=9,leading=13,textColor=INK),
    'th':ParagraphStyle('th',fontName='Bold',fontSize=9,leading=13,textColor=white),
    'call':ParagraphStyle('call',fontName='Text',fontSize=10,leading=15,textColor=INK),
}
PAGES=[('INIZIA QUI','Windows'),('SUL DESKTOP','macOS, Linux e comandi'),('CONSERVA','Appunti'),
       ('RICORDA','Promemoria'),('ASCOLTA','Voce e suoni'),('ESERCITATI','Metronomo'),
       ('MISURA','Cronometro e focus'),('CONSERVA I DATI','Backup e manutenzione'),('SEMPRE AGGIORNATA','Aggiornamenti'),
       ('RIPOSA','Il sonno di Yun Jin'),('INTORNO A TE','Orario e meteo'),
       ('IMPARA','Studio e ripassi'),('CREA','Le tue flashcard'),('RICORDA A LUNGO','FSRS e richiami'),
       ('PERSONALIZZA','Scorciatoie e Anki'),('AIUTO','Problemi e crediti')]

def p(text,style='p'):return Paragraph(text,S[style])
def h(text):return p(text,'h')
def table(headers,rows,widths=None):
    t=Table([[p(v,'th') for v in headers]]+[[p(str(v),'cell') for v in row] for row in rows],
        colWidths=widths or [150,BW-150],hAlign='LEFT',repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),PURPLE),('ROWBACKGROUNDS',(0,1),(-1,-1),[white,HexColor('#f1ecf5')]),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),
        ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]));return t

def call(text):
    t=Table([[p(text,'call')]],colWidths=[BW]);t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),HexColor('#eae4f0')),('BOX',(0,0),(-1,-1),.5,LINE),
        ('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),
        ('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]));return t

def picture(name,width=BW):
    with PILImage.open(ART/name) as im:height=width*im.height/im.width
    return Image(str(ART/name),width=width,height=height,hAlign='CENTER')

def cover(c):
    """Vector cover composed around the approved character artwork."""
    import math
    c.saveState()
    plum=HexColor('#292238');muted=HexColor('#c3b4cf')
    rose=HexColor('#eab8cf');blue=HexColor('#a2d0da');cream=HexColor('#fcf6f2')
    c.setFillColor(plum);c.rect(0,0,W,H,stroke=0,fill=1)
    # Fine inset rule and small editorial labels.
    c.setStrokeColor(HexColor('#665371'));c.setLineWidth(.6)
    c.rect(24,24,W-48,H-48,stroke=1,fill=0)
    c.setFillColor(blue);c.setFont('Bold',9)
    c.drawString(48,H-62,'GUIDA ILLUSTRATA')
    c.setFillColor(cream);c.setFont('Text',9)
    c.setStrokeColor(HexColor('#665371'));c.line(48,H-82,W-48,H-82)
    c.setFillColor(cream);c.setFont('Bold',55)
    c.drawCentredString(W/2,681,'YUN JIN')
    c.setFillColor(rose);c.setFont('Text',27)
    c.drawCentredString(W/2,644,'Companion')
    c.setFillColor(muted);c.setFont('Text',11)
    c.drawCentredString(W/2,613,'Una piccola compagna per il tuo desktop')
    # A stage-like medallion, with thin orbit lines and musical details.
    cx,cy=W/2,397
    c.setStrokeColor(HexColor('#6d587e'));c.setLineWidth(.6)
    c.circle(cx,cy,171,stroke=1,fill=0)
    c.setFillColor(HexColor('#393047'));c.circle(cx,cy,157,stroke=0,fill=1)
    c.setFillColor(HexColor('#d8c3dd'));c.circle(cx,cy,137,stroke=0,fill=1)
    c.setFillColor(cream);c.circle(cx,cy,126,stroke=0,fill=1)
    for angle,color in [(26,blue),(146,rose),(236,blue),(310,rose)]:
        x=cx+171*math.cos(math.radians(angle));y=cy+171*math.sin(math.radians(angle))
        c.setFillColor(color);c.circle(x,y,3,stroke=0,fill=1)
    c.setFillColor(HexColor('#e7dce8'));c.ellipse(cx-65,cy-100,cx+65,cy-88,fill=1,stroke=0)
    # Place the approved atlas directly, retaining its full source resolution.
    import json
    atlas=ROOT/'app/assets'
    spec=next(a for a in json.loads((atlas/'animations.json').read_text())['animations']
              if a['name']=='conduct16')
    frame=6;sx,sy,sw,sh=spec['frame_rects'][frame];scale=215/sh
    left,bottom=cx-sw*scale/2,cy-95
    with PILImage.open(atlas/spec['file']) as im:iw,ih=im.size
    c.saveState();clip=c.beginPath()
    for row,x,width in spec['frame_clip_rows'][frame]:
        clip.rect(left+x*scale,bottom+(sh-row-1)*scale,width*scale,scale)
    c.clipPath(clip,stroke=0,fill=0)
    c.drawImage(str(atlas/spec['file']),left-sx*scale,bottom-(ih-sy-sh)*scale,
                iw*scale,ih*scale,mask='auto')
    c.restoreState()
    # Musical notes echo the app's metronome without adding interface clutter.
    for x,y,color in [(105,465,blue),(476,330,rose)]:
        c.setStrokeColor(color);c.setFillColor(color);c.setLineWidth(1.5)
        c.ellipse(x-9,y-4,x+3,y+3,stroke=0,fill=1)
        c.line(x+3,y,x+3,y+29);c.line(x+3,y+29,x+15,y+25)
    for x,y in [(121,319),(469,494)]:
        c.setStrokeColor(rose);c.setLineWidth(.7)
        c.line(x-5,y,x+5,y);c.line(x,y-5,x,y+5)
    c.setFillColor(blue);c.setFont('Bold',9)
    c.drawCentredString(W/2,183,'STUDIO   /   TEMPO   /   MUSICA')
    c.setFillColor(cream);c.setFont('Text',11)
    c.drawCentredString(W/2,156,'Installa, personalizza e porta Yun Jin con te.')
    c.setStrokeColor(HexColor('#665371'));c.line(48,110,W-48,110)
    c.setFillColor(muted);c.setFont('Text',9)
    c.drawString(48,85,'Windows · macOS · Linux')
    c.setFont('Text',7);c.drawString(48,62,'Progetto fan indipendente · Personaggio di Genshin Impact')
    c.restoreState()

def page(c,doc):
    n=doc.page-1
    if n==0:
        cover(c)
        return
    c.saveState();c.setFillColor(PAPER);c.rect(0,0,W,H,fill=1,stroke=0)
    c.setFillColor(PURPLE);c.rect(0,H-8,W,8,fill=1,stroke=0)
    tag,title=PAGES[n-1] if n<=len(PAGES) else ('GUIDA','Continua')
    c.setFillColor(TEAL);c.setFont('Bold',9);c.drawString(44,792,tag)
    c.setFillColor(INK);c.setFont('Bold',27);c.drawString(44,756,title)
    c.setFillColor(PURPLE);c.setFont('Text',9);c.drawRightString(W-44,791,'YUN JIN COMPANION')
    c.setStrokeColor(LINE);c.line(44,734,W-44,734);c.line(44,42,W-44,42)
    c.setFont('Text',8);c.setFillColor(PURPLE);c.drawString(44,25,'Guida d’uso')
    c.drawRightString(W-44,25,f'{n:02d} / {len(PAGES):02d}')
    if n in (6,7):
        art='conduct16.png' if n==6 else 'stopwatch16.png'
        c.drawImage(str(ART/art),W-91,742,40,47,mask='auto',preserveAspectRatio=True,anchor='c')
    c.restoreState()

story=[Spacer(1,1),PageBreak()]
# 1
story += [p('Una compagna per imparare, ricordare e fare musica.'),
    call('<b>Windows 10/11, 64 bit.</b> Estrai tutto lo ZIP prima di avviare l’app.'),
    h('Installa'),p('<b>1.</b> Chiudi Yun Jin, se è già aperta.<br/><b>2.</b> Estrai lo <b>ZIP di distribuzione della release</b> in una cartella.<br/><b>3.</b> Apri <b>Windows.cmd</b> e attendi il completamento.'),
    p('L’avviatore cerca Python. Se manca, scarica Python ufficiale e verifica il file. Installa l’app nel tuo profilo, con un ambiente separato, e crea i collegamenti su Desktop e nel menu Start.'),
    h('Dopo l’installazione'),p('Apri <b>Yun Jin Companion</b> dal collegamento. Un doppio clic sul personaggio apre il pannello; il clic destro apre il menu. Scegli uno strumento dalla barra laterale.'),
    picture('appunti.png',390),Spacer(1,9),
    p('Chiudere il pannello lascia Yun Jin aperta; <b>Chiudi</b> nel menu termina l’app.','small'),
    p('Se nella barra delle applicazioni resta la vecchia icona Python, rimuovi quel collegamento fissato e fissa <b>Yun Jin Companion</b> dal menu Start, dopo aver eseguito il nuovo Windows.cmd.','small'),PageBreak()]
# 2
story += [h('macOS'),p('Su <b>macOS 13 o successivo</b>, Intel o Apple Silicon, estrai lo ZIP e apri <b>Mac.command</b>. Se Python manca, completa l’installer ufficiale proposto. In seguito usa <b>Yun Jin Companion.app</b> in <b>/Applications</b> o sulla Scrivania. macOS può chiedere il permesso per la copia.'),
    p('<b>Se macOS blocca l’apertura perché lo sviluppatore non è verificato:</b> dopo il tentativo vai in <b>Impostazioni di Sistema → Privacy e Sicurezza → Apri comunque</b>, quindi conferma <b>Apri</b>. Autorizza solo il pacchetto ottenuto dalla release ufficiale. Il doppio clic, da solo, può non bastare.','small'),
    p('Yun Jin appare anche sopra le app a schermo intero. In questa modalità l’icona nel Dock scompare: usa il personaggio o il menu nella barra in alto. In <b>Impostazioni</b> puoi disattivare <b>Mostra anche sopra le app a schermo intero</b> e ripristinare il Dock. La scelta viene salvata.','small'),
    h('Linux'),p('Servono un desktop grafico, Python 3.11-3.14 a 64 bit e il modulo venv. Dalla cartella estratta esegui <b>bash Linux.sh</b>; poi usa il menu applicazioni. Su Wayland la posizione del personaggio dipende dal compositor; X11 offre maggiore compatibilità.'),
    h('Muovi e controlla Yun Jin'),table(['Comando','Azione'],[
        ['Trascina il personaggio','Sposta Yun Jin sullo schermo.'],
        ['Doppio clic','Apre il pannello.'],['Clic destro / Ctrl-clic su Mac','Apre strumenti, comportamento, animazioni e aspetto.'],
        ['Comportamento','Pausa, ripresa, passeggiata, esibizione e carattere. Seguimi parte dopo 2 secondi e dura 9 secondi.'],
        ['Animazioni','Scegli una categoria e un gesto. Per un ciclo continuo usa Ripeti; Termina lo interrompe.'],
        ['Aspetto','Dimensioni, opacità, monitor e recupero del pet fuori schermo.']]),
    p('Le scorciatoie si personalizzano in <b>Impostazioni → Scorciatoie</b>. Su Windows e macOS funzionano anche mentre usi altre app. Su Linux funzionano nelle finestre di Yun Jin.','small'),
    PageBreak()]
# 3
story += [picture('appunti.png'),Spacer(1,12),
    table(['Controllo','Uso'],[['Nuovo','Crea un appunto. Titolo e testo si salvano automaticamente.'],
        ['Importa','Aggiunge il contenuto copiato, un file o una cartella. Puoi anche trascinarli nel pannello o sul pet.'],
        ['Leggi','Pronuncia la selezione, oppure l’intero appunto.'],
        ['Menu ⋯','Salvataggio esplicito o eliminazione.'],
        ['ChatGPT','Mostra tipo di richiesta e istruzioni facoltative. Copia e apri prepara il testo e apre ChatGPT.']]),Spacer(1,10),
    p('<b>In ChatGPT incolla la richiesta.</b> Eventuali immagini o file vanno allegati manualmente: il pet non li invia.'),
    p('Le immagini incollate vengono conservate. File e cartelle restano collegamenti agli originali: se li sposti, aggiorna il riferimento. Eliminare l’appunto non elimina il file collegato.','small'),PageBreak()]
# 4
pair=Table([[picture('promemoria.png',270),picture('avviso.png',214)]],colWidths=[283,BW-283])
pair.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]))
story += [pair,Spacer(1,16),h('Crea un promemoria'),
    p('Apri <b>Promemoria → Nuovo</b>. Scrivi il contenuto, scegli <b>Tra</b> per un intervallo o <b>Data e ora</b> per una scadenza. I valori rapidi impostano 5, 15, 25 o 60 minuti. Premi <b>Salva</b>.'),
    table(['Quando arriva','Cosa fare'],[['Fatto','Completa il promemoria.'],['Tra 10 min','Rimanda dalla notifica. Nel pannello puoi scegliere un intervallo diverso.'],
        ['Icona elenco','Apre tutti i promemoria.'],['×','Nasconde la notifica; il promemoria resta da gestire.']]),
    h('Gestisci l’elenco'),p('Seleziona una riga per completarla o rimandarla. Il menu <b>⋯</b> contiene <b>Modifica</b> ed <b>Elimina</b>; il doppio clic modifica. Attiva <b>Completati</b> per vedere anche gli avvisi già gestiti.'),
    call('<b>Yun Jin deve essere aperta per avvisarti.</b> Dopo una sospensione o al successivo avvio recupera le scadenze passate.'),Spacer(1,12),
    p('Il numero sul pet e nella barra laterale indica gli avvisi da gestire. Il silenzio temporaneo sospende voce e campanelli; gli avvisi visivi rimangono attivi. Durante il metronomo il campanello dei promemoria suona; la lettura vocale resta sospesa, senza interrompere il ritmo.','small'),PageBreak()]
# 5
story += [picture('voce.png',460),Spacer(1,12),
    p('In <b>Voce</b>, <b>Leggi i promemoria alla scadenza</b> pronuncia gli avvisi alla scadenza. La lettura manuale è indipendente da questa opzione. <b>Ascolta</b> legge il campo di testo; <b>Leggi testo copiato</b> usa gli appunti del sistema. <b>Stop</b> compare durante la lettura o la preparazione.'),
    p('Durante ogni lettura compare un <b>fumetto</b> accanto a Yun Jin. I testi lunghi scorrono in brevi parti; <b>Stop</b> interrompe voce e fumetto. Saluti e commenti meteo usano la lingua selezionata qui.'),
    table(['Servizio','Regolazioni'],[['Microsoft Edge','Voce, velocità, intonazione e volume.'],['Google Translate','Lingua, lettura lenta e volume; la voce è scelta dal servizio.']]),Spacer(1,10),
    p('Il menu <b>⋯</b> svuota la cache o ripristina Elsa: italiano, +20% di velocità, +15 Hz, volume 70%. La lettura accetta fino a 3.000 caratteri; seleziona un passaggio per testi più lunghi.'),
    p('<b>La sintesi vocale usa Internet e invia il testo al servizio scelto.</b> Non servono chiavi API. Edge e gTTS sono accessi non ufficiali: disponibilità e limiti dipendono dai servizi. Gli audio già letti restano nella cache locale.','small'),
    p('I volumi sono separati: voce in <b>Voce</b>, effetti in <b>Impostazioni</b>, click nel <b>Metronomo</b>. Disattivando <b>Effetti sonori</b> spegni campanelli e suoni di saluto e conferma. Una lettura manuale ferma il metronomo.','small'),PageBreak()]
# 6
story += [picture('metronomo.png',450),Spacer(1,12),
    table(['Controllo','Uso'],[['BPM / Tap tempo','Da 20 a 400. I clic ripetuti su Tap tempo impostano la velocità.'],
        ['Accento','Evidenzia il primo battito di gruppi da 1 a 32. Disattivalo per click uniformi.'],
        ['Scalata','Arrivo è il BPM finale; Passo è la variazione. Ogni sceglie l’intervallo in battiti o secondi.'],
        ['Al termine','Continua al BPM finale o ferma dopo un ultimo intervallo completo.']]),Spacer(1,10),
    p('<b>Esempio:</b> 80 → 120 BPM, passo 4, ogni 16 battiti. La scalata può anche scendere; il cambio avviene sul primo battito alla soglia o dopo di essa, senza saltare il tempo finale.'),
    p('Premi <b>Avvia</b>; per cambiare i parametri premi <b>Ferma</b>. Il volume resta regolabile. Chiudere il pannello lascia suonare il metronomo; la sospensione del computer lo ferma. Cuffie Bluetooth possono ritardare l’audio rispetto al gesto.','small'),PageBreak()]
# 7
story += [picture('cronometro.png',400),Spacer(1,10),
    p('<b>Avvia / Riprendi</b> continua il conteggio; <b>Pausa</b> lo sospende. <b>Parziale</b> registra il tempo dall’ultimo passaggio e il totale. L’icona con la freccia circolare azzera tempo e parziali.'),
    p('<b>Copia</b> trasferisce la tabella negli appunti; <b>CSV</b> esporta durate e totali in secondi. Il cronometro prosegue a pannello chiuso. Chiudendo Yun Jin viene salvato e messo in pausa.'),
    h('Focus'),picture('focus.png',370),Spacer(1,10),
    p('Imposta da 1 a 180 minuti e premi <b>Avvia</b>. Yun Jin sospende passeggiate ed esibizioni spontanee; i comandi manuali e i promemoria continuano a funzionare.'),
    p('Alla fine arriva l’avviso di pausa e lo stiracchiamento, quando voce e pannello lo consentono. La sessione non riparte da sola. <b>Interrompi</b> annulla il conto alla rovescia; una scadenza passata viene recuperata al riavvio.','small'),PageBreak()]
# 8
story += [h('Dove sono i dati'),p('In <b>Impostazioni → Cartella dati</b> trovi appunti, immagini, promemoria e preferenze. Gli strumenti musicali e i dati personali funzionano localmente.'),
    table(['Sistema','Cartella'],[['Windows','%LOCALAPPDATA%\\YunJinPet'],['macOS','~/Library/Application Support/YunJinPet'],['Linux','~/.local/share/YunJinPet<br/>(oppure XDG_DATA_HOME)']]),
    h('Backup'),p('Scegli <b>Impostazioni → Backup</b> e salva lo ZIP. Include appunti, promemoria, mazzi, cronologia dei ripassi e relativi audio e immagini. Appunti e promemoria hanno anche una copia leggibile. I file esterni collegati e le collezioni di Anki non sono inclusi. Posizione, carattere e dimensione del pet sono impostazioni del sistema e non fanno parte del backup.'),
    h('Ripristino manuale'),p('<b>1.</b> Chiudi Yun Jin e copia la cartella dati in un luogo sicuro.<br/><b>2.</b> Sposta dalla cartella dati <b>companion.sqlite3</b> e gli eventuali file <b>companion.sqlite3-wal</b> e <b>companion.sqlite3-shm</b>.<br/><b>3.</b> Inserisci il database e le cartelle <b>attachments</b> e <b>study-media</b> del backup.<br/><b>4.</b> Riapri Yun Jin. Se hai cambiato computer, aggiorna i collegamenti ai file esterni.'),
    h('Installazione manuale e riparazione'),p('Per aggiornare manualmente o riparare l’installazione, chiudi Yun Jin, estrai il nuovo pacchetto e avvia <b>Windows.cmd</b>, <b>Mac.command</b> o <b>Linux.sh</b>. L’installer sostituisce il programma e aggiorna le dipendenze conservando i dati. Ripeti l’avvio se il collegamento smette di funzionare dopo aver rimosso Python.'),
    h('Disinstalla'),p('Chiudi l’app e rimuovi i collegamenti. Sul Mac elimina anche l’app in <b>/Applications</b>. Nella cartella dati rimuovi <b>program</b> e <b>runtime</b>; su Windows anche l’eventuale <b>python-3.13</b>. Conserva database, attachments e study-media per riusarli, oppure esporta un backup prima di eliminare tutta la cartella.'),
    call('Per condividere l’app invia lo <b>ZIP di distribuzione</b>. La tua cartella dati contiene appunti personali e non va inclusa.'),PageBreak()]
# 9
story += [picture('aggiornamento.png',330),Spacer(1,8),
    p('Esempio di avviso con note dimostrative. Le note effettive vengono dalla release pubblicata su GitHub.','small'),
    p('Il controllo è attivo di default: circa 30 secondi dopo l’avvio e poi ogni <b>2 ore</b>, finché Yun Jin è aperta. L’avviso automatico attende la fine di voce, metronomo, cronometro o focus.'),
    table(['Scelta','Risultato'],[
        ['Aggiorna e riavvia','Scarica e verifica lo ZIP, salva gli appunti, aggiorna e riapre Yun Jin.'],
        ['Più tardi','Rimanda la proposta di circa due ore.'],
        ['Salta questa versione','Non propone più questa release. Continuerà a cercare quelle successive.']]),Spacer(1,9),
    p('In <b>Impostazioni</b> puoi disattivare il controllo, usare <b>Controlla ora</b> o riaprire le note. Un controllo manuale mostra anche una versione saltata.','small'),
    p('I file vengono aggiornati nella <b>cartella effettivamente in uso</b>, anche se spostata. Dati personali e file aggiunti da te restano al loro posto. In caso di errore nella copia o nel nuovo avvio viene ripristinato il programma precedente.','small'),
    p('Serve Internet. Se una release richiede un nuovo Python o nuove dipendenze, l’app lo segnala e rimanda all’installer. Gli aggiornamenti integrati usano il Python già installato senza aprire Mac.command.','small'),PageBreak()]
# 10
story += [h('Tre fasi, un movimento continuo'),
    p('Yun Jin sbadiglia, si siede e appoggia la testa sulle mani. Il sonno è un ciclo lento di respiro; al risveglio si rialza gradualmente e torna al comportamento normale.'),
    picture('sonno-fasi.png',BW),Spacer(1,15),
    table(['Comando','Comportamento'],[
        ['Comportamento → Carattere → Addormentata','Resta addormentata finché scegli un altro carattere o le chiedi di riprendere. La scelta viene ricordata.'],
        ['Animazioni → Riposo → Sonnellino','Un breve episodio: addormentamento, circa mezzo minuto di sonno e risveglio.'],
        ['Comportamento → Riprendi','La sveglia e ripristina il carattere Normale.'],
        ['Seguimi, passeggiata o animazione manuale','Completa il risveglio prima di eseguire il comando.']]),Spacer(1,13),
    h('Un comportamento occasionale'),
    p('Con le animazioni aggiuntive attive può addormentarsi spontaneamente. Il primo episodio non arriva nei primi 10 minuti; dopo ogni risveglio attende almeno 15 minuti prima di poterlo fare ancora. Gli episodi spontanei durano circa 30-55 secondi di sonno.'),
    h('Strumenti e promemoria'),
    p('Il sonno non spegne i promemoria: gli avvisi e i suoni restano attivi. Voce e metronomo possono farla svegliare per la propria animazione. Focus e metronomo impediscono nuovi sonnellini spontanei.'),
    call('La modalità <b>Addormentata</b> è sopra <b>Tranquilla</b> nel menu Carattere. Non è la Pausa completa: il respiro continua ad animarsi.'),PageBreak()]
# 11
story += [picture('orario-meteo.png',390),Spacer(1,8),
    h('Un saluto quando apri l’app'),
    p('Yun Jin ti saluta nella <b>lingua scelta in Voce</b>, secondo l’orologio locale del computer. Il saluto vocale avviene <b>una sola volta all’avvio</b>: riaprire il pannello o cambiare impostazioni non lo ripete. Usa anche il servizio, la voce e il volume che hai selezionato. La frase compare nel fumetto durante il parlato.'),
    table(['Fascia locale','Reazione al cambio di fascia'],[
        ['05:00–11:59 · Mattina','Apre le braccia e saluta.'],
        ['12:00–17:59 · Pomeriggio','Buon pomeriggio: saluta con la mano.'],
        ['18:00–21:59 · Sera','Buona sera: mano sul cuore e cenno del capo.'],
        ['22:00–04:59 · Notte','Uno sbadiglio.']]),Spacer(1,10),
    p('Ogni cambio di fascia produce al massimo una reazione. Al ritorno dalla sospensione considera solo la fascia attuale, senza recuperare tutte quelle trascorse. Puoi provarle da <b>Animazioni → Orario oppure Meteo</b>. Con le animazioni aggiuntive disattivate usa i gesti originali.','small'),
    p('<b>Applauso</b>, in <b>Animazioni → Gesti</b>, si esegue solo su comando: non è un comportamento casuale.','small'),
    h('Il tempo fuori'),
    p('Dopo circa un minuto, poi ogni <b>ora</b>, cerca il meteo in background. Sole, nuvole, pioggia, neve, nebbia e temporali possono provocare un gesto e una breve frase nella lingua scelta. Al sole si ripara gli occhi; segue una nuvola, cerca riparo dalla pioggia o raccoglie un fiocco di neve. Reagisce ai cambiamenti, con almeno <b>due ore</b> tra due commenti meteo.'),
    p('La posizione è approssimativa, ricavata dall’IP con <b>ipwho.is</b> e conservata fino a 24 ore. VPN e reti mobili possono indicare un’altra zona. I dati di <link href="https://open-meteo.com/" color="#3e777e">Open-Meteo</link> sono stime, conservate per un’ora. Non usa GPS, account o chiavi API.','small'),
    call('Puoi disattivare separatamente saluto, reazioni all’ora e meteo. Durante comandi manuali, sonno, pausa, focus, metronomo o promemoria queste reazioni aspettano brevemente o vengono saltate. Senza dati o connessione, Yun Jin continua normalmente e non mostra errori.'),PageBreak()]
# Study
story += [p('Apri <b>Studio</b> dalla barra laterale. Crea un mazzo, aggiungi alcune carte e premi <b>Studia</b>.'),
    picture('studio.png',450),Spacer(1,10),
    h('Una risposta alla volta'),p('Pensa alla risposta, poi premi <b>Spazio</b> o <b>Mostra risposta</b>. Valuta quanto ricordavi, senza confondere una risposta dimenticata con una risposta difficile.'),
    table(['Tasto','Valutazione'],[
        ['1 · Da rivedere','Non ricordavo la risposta.'],['2 · Difficile','La ricordavo, con fatica.'],
        ['3 · Bene','La ricordavo correttamente.'],['4 · Facile','La ricordavo senza esitazione.']],[140,BW-140]),
    p('Sotto ogni valutazione compare il prossimo intervallo. <b>Spazio</b> dopo la risposta equivale a Bene. La freccia circolare o <b>Ctrl+Z</b> (⌘Z su Mac) annulla l’ultima risposta.','small'),
    p('Ogni risposta è salvata subito. <b>Termina</b> chiude la sessione; puoi riprendere più tardi. Nuove e ripassi sono mescolati; i passi brevi in scadenza hanno la precedenza.','small'),PageBreak()]
# Cards
story += [p('Con <b>Aggiungi carta</b> scegli Fronte / retro oppure Cloze. Le schede Fronte e Retro contengono testo e allegati indipendenti.'),
    picture('carte.png',430),Spacer(1,10),
    h('Fronte / retro'),p('Scrivi la domanda sul fronte e la risposta sul retro. Per il cinese puoi usare un carattere sul fronte e pinyin, significato e una frase sul retro.'),
    h('Cloze: nascondi una parte'),p('Seleziona il testo e premi <b>Lacuna</b>, oppure scrivi <b>{{c1::testo}}</b>. Un suggerimento è facoltativo: <b>{{c1::testo::indizio}}</b>. Ogni numero distinto crea una carta; lo stesso numero nasconde più parti insieme. Le lacune annidate non sono supportate.'),
    h('Immagini e audio'),p('I pulsanti <b>Immagine</b> e <b>Audio</b> copiano i file nella cartella dati: puoi spostare gli originali. Massimo 12 allegati per lato e 32 MB per file. Durante lo studio premi Audio per ascoltare; il silenzio e le impostazioni dei suoni restano rispettati.'),
    p('<b>Anteprima</b> mostra domanda e risposta prima del salvataggio. <b>Salva e aggiungi</b> apre subito una nuova carta. Modificare il testo conserva i progressi delle carte esistenti.','small'),PageBreak()]
# FSRS
story += [p('<b>FSRS 6</b> stima difficoltà, stabilità della memoria e probabilità di ricordare. Pianifica ogni carta in base alle tue risposte. Nel menu del mazzo, apri <b>Opzioni del mazzo</b> per personalizzarlo.'),
    table(['Impostazione','Valore iniziale'],[
        ['FSRS','Attivo. Puoi disattivarlo per usare intervalli convenzionali.'],
        ['Ritenzione desiderata','90%. Più alta significa ripassi più frequenti.'],
        ['Nuove / ripassi al giorno','Senza limiti. 0 blocca nuove carte o nuovi ripassi; i passi già avviati nella giornata continuano.'],
        ['Passi nuove carte','10s 30s 1m 10m'],['Passi dopo un errore','10s 30s 1m'],
        ['Passaggi ostinati','16 errori nei ripassi: carta contrassegnata e messa in pausa. Puoi disattivare la pausa automatica.']],[165,BW-165]),Spacer(1,7),
    p('I passi accettano s, m, h e d; senza unità il valore è in minuti. Da rivedere torna al primo passo; Bene avanza, Difficile ripete il passo (sul primo usa una media), Facile passa ai ripassi. Con passi vuoti decide FSRS. I limiti giornalieri ripartono alle 04:00 locali.','small'),
    h('Si adatta al tuo studio'),p('Dopo le sessioni, FSRS si adatta automaticamente ai tuoi risultati quando c’è abbastanza cronologia. Le scadenze già fissate restano invariate.'),
    p('La ritenzione a 30 giorni nel pannello indica quante risposte hai ricordato nei ripassi distanziati di almeno un giorno. I passi brevi sono esclusi.','small'),
    h('Piccoli richiami'),p('Ogni 90-150 minuti, al massimo tre volte al giorno, può comparire un fumetto. Sceglie tra i <b>passaggi ostinati</b> e il <b>10% più difficile</b> di ogni mazzo studiato oggi, considerando anche gli errori recenti. Aspetta almeno 30 minuti dall’ultimo ripasso della carta e alterna le note. <b>Ripassa</b> apre fino a tre carte; <b>×</b> ignora e <b>Non oggi</b> sospende i richiami. Scompare dopo 18 secondi.'),
    p('Durante il focus o altre attività non interrompe. Puoi disattivare i richiami in <b>Studio → menu → Richiami e Anki</b>. I ripassi extra delle carte native vengono registrati e FSRS ne tiene conto.','small'),PageBreak()]
# Shortcuts and optional Anki
story += [h('Scegli i tuoi tasti'),p('Apri <b>Impostazioni → Scorciatoie</b>, scegli la funzione, clicca una combinazione e premi i tasti. <b>Salva</b> applica; <b>×</b> disattiva; <b>Ripristina</b> torna ai valori iniziali. I nuovi comandi sono senza combinazione finché ne assegni una.'),
    picture('scorciatoie.png',420),Spacer(1,10),
    p('Puoi controllare cronometro, metronomo e focus anche a pannello chiuso. Avvia / Pausa conserva il tempo del cronometro; Parziale registra un giro; Azzera cancella tempo e parziali. Metronomo e focus usano le impostazioni correnti o le ultime salvate.','small'),
    p('Su Windows e macOS, le combinazioni occupate vengono segnalate mentre le imposti. Il controllo legge le scorciatoie di sistema e verifica quelle registrate dalle altre app; le app che intercettano direttamente i tasti possono sfuggirgli. Su Linux le scorciatoie funzionano nelle finestre di Yun Jin.','small'),
    h('Collega Anki, se vuoi'),p('In <b>Studio → menu → Richiami e Anki</b> abilita <b>Includi le carte di Anki</b>. Se c’è un solo profilo viene selezionato; con più profili scegli quello da usare. <b>Sfoglia</b> apre la cartella di Anki, se devi selezionare una collezione diversa. Non servono plugin.'),
    call('Anki viene <b>solo letto</b>. I richiami includono passaggi ostinati e carte difficili dei <b>mazzi studiati nella sua giornata corrente</b>. Puoi includere i passaggi ostinati sospesi con l’apposita spunta: restano sospesi in Anki. Carte nuove, sepolte e nei mazzi filtrati sono escluse. Sono esercizi liberi: non cambiano la pianificazione di Anki.'),Spacer(1,7),
    p('La lettura si aggiorna ogni 15 minuti, anche con Anki aperto. Sono supportati fronte/retro e cloze, con immagini e audio locali. Gli script decorativi vengono ignorati; i modelli che non hanno contenuto statico leggibile vengono segnalati. Puoi scollegare Anki in qualsiasi momento.','small'),PageBreak()]
# 12
story += [table(['Problema','Controllo'],[
    ['Yun Jin non si vede','Menu dell’area di notifica → Aspetto → Riporta sullo schermo.'],
    ['Mac: icona Dock assente','È normale con la modalità sopra le app a schermo intero. Puoi disattivarla in Impostazioni.'],
    ['La voce non parte','Controlla Internet, volume e uscita audio. In Voce prova l’altro servizio o svuota la cache.'],
    ['Promemoria senza voce','In Voce abilita Leggi i promemoria alla scadenza; termina il silenzio dal menu o ferma il metronomo.'],
    ['Il metronomo non suona','Controlla l’uscita audio del sistema. Dopo aver cambiato dispositivo, premi Ferma e Avvia.'],
    ['Il pet resta fermo','In Comportamento togli Pausa completa e scegli Riprendi. Controlla Focus e il carattere scelto, incluso Addormentata.'],
    ['Avvio bloccato','Controlla la provenienza del pacchetto e le autorizzazioni del sistema. Su dispositivi gestiti rivolgiti all’amministratore.'],
    ['Installazione interrotta','Conserva il messaggio, verifica connessione e spazio libero, poi ripeti l’avvio. Il log è yun-jin.log nella cartella dati.']]),
    h('Requisiti e accesso alla rete'),p('Prima installazione, voce, meteo e controllo aggiornamenti richiedono Internet. Studio, appunti, promemoria, focus, cronometro e metronomo funzionano offline. iOS e Android non sono inclusi. Il programma usa Python a 64 bit; gli avviatori gestiscono un ambiente privato.','small'),
    h('Crediti e licenze'),p('Progetto fan non ufficiale. Yun Jin è un personaggio di Genshin Impact; personaggio e marchi appartengono ai rispettivi titolari. Lo sprite originale fornito dall’utente è conservato. Le animazioni aggiuntive sono generate da riferimenti e revisionate. Le immagini della guida provengono dai file definitivi dell’app.','small'),
    p('Codice: <b>GNU GPL v3 o successiva</b>, in <b>app/licenses/GPL-3.0.txt</b>. La licenza del codice non concede diritti ulteriori sulle illustrazioni o sui marchi. Python, PyQt6/Qt, edge-tts, gTTS e FSRS mantengono le rispettive licenze. FSRS 6 è di Open Spaced Repetition; le licenze sono in app/licenses. Nessuna affiliazione con HoYoverse, Microsoft, Google o OpenAI.','small'),
    p('Meteo: <link href="https://open-meteo.com/" color="#3e777e">Open-Meteo</link>, dati CC BY 4.0. Posizione approssimativa: <link href="https://ipwhois.io/" color="#3e777e">ipwho.is</link>. Per la voce, il testo viene inviato al servizio selezionato; per il meteo, i servizi ricevono l’indirizzo IP e le coordinate approssimative necessarie.','small'),
    h('Progetti di riferimento'),p('<link href="https://www.python.org" color="#3e777e">Python</link> · <link href="https://www.riverbankcomputing.com/software/pyqt/" color="#3e777e">PyQt</link> · <link href="https://doc.qt.io" color="#3e777e">Qt</link> · <link href="https://github.com/rany2/edge-tts" color="#3e777e">edge-tts</link> · <link href="https://gtts.readthedocs.io" color="#3e777e">gTTS</link>','small'),
    p('Revisione della guida: 1 ottobre 2026.','small')]

doc=BaseDocTemplate(str(OUT),pagesize=(W,H),title='Yun Jin Companion - Guida',author='Yun Jin Companion',pageCompression=1)
frame=Frame(44,53,BW,666,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
doc.addPageTemplates(PageTemplate(id='guide',frames=[frame],onPage=page));doc.build(story)
print(OUT)
