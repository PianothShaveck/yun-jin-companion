# SPDX-License-Identifier: GPL-3.0-or-later
"""Weather observations, loaded only when the first weather reaction is due.

Each row is Italian, English, Mandarin. A persisted shuffled bag visits every
line before recycling it, independently for each language and condition.
"""
import random

LANGUAGES=('it','en','zh-CN')
LINES={
    'sun': (
        ('Che bel sole! Spero che illumini anche la tua giornata.', 'Such lovely sunshine! I hope it brightens your day too.', '阳光真好，愿你今天心情愉快。'),
        ('Il sole si è preso il centro della scena.', 'The sun has taken centre stage.', '太阳站到了舞台中央。'),
        ('Cielo sereno: anche una piccola pausa può diventare una passeggiata.', 'Clear skies: a little break could become a short walk.', '天空晴朗，休息时也许可以出去走走。'),
        ('Oggi il parasole sembra proprio un buon compagno.', 'A parasol sounds like good company in this sunshine.', '这样的晴天，带把阳伞正合适。'),
        ('C’è il sole. Se esci, pensa anche a un po’ d’ombra.', 'The sun is out. A little shade is worth finding if you head outside.', '太阳出来了，出门也别忘了找些阴凉。'),
        ('Un cielo così luminoso mi fa venire voglia di canticchiare.', 'A sky this bright makes me feel like humming.', '这么明亮的天空，让我想轻轻哼首歌。'),
        ('Il sole ci regala una bella luce per una pausa.', 'The sunshine gives us a lovely light for a break.', '阳光正好，休息一会儿吧。'),
        ('Che luce! Persino una giornata piena può avere un piccolo intervallo.', 'Look at that light! Even a busy day can have a little intermission.', '阳光真亮！再忙的一天，也可以有个小小的幕间休息。'),
        ('Il cielo è sereno. Hai un momento per guardare fuori?', 'The sky is clear. Have you a moment to look outside?', '天气晴朗，你有空看看窗外吗？'),
        ('Sole in scena, ombrello a riposo.', 'Sunshine on stage, umbrella off duty.', '今天阳光登场，雨伞可以休息了。'),
        ('Questo sole è un bell’invito a sgranchirsi un po’.', 'This sunshine is a lovely invitation to stretch your legs.', '这样的阳光，很适合活动活动身体。'),
        ('Una parentesi al sole, senza avere fretta: che ne dici?', 'A moment in the sunshine, with no hurry. What do you think?', '不赶时间，晒一会儿太阳，怎么样？'),
        ('Il cielo sereno ha qualcosa di semplice e allegro.', 'There is something simple and cheerful about a clear sky.', '晴朗的天空，总有种简单的快乐。'),
        ('Con questa luce, anche il mio fiocco sembra più vivace.', 'In this light, even my ribbon seems a little brighter.', '在这样的阳光下，我的丝带也显得更鲜艳了。'),
        ('Che bel fondale azzurro per le cose che vuoi fare oggi.', 'What a lovely blue backdrop for whatever you want to do today.', '今天想做的事，都有一片蓝天作背景。'),
    ),
    'clear_night': (
        ('Il cielo è sereno. Che bella notte tranquilla.', 'The sky is clear. What a peaceful night.', '今晚天色晴朗，真是个宁静的夜晚。'),
        ('La notte ha aperto il suo sipario sul cielo sereno.', 'Night has drawn its curtain back on a clear sky.', '夜幕拉开，露出了晴朗的天空。'),
        ('Cielo sereno anche adesso. Possiamo abbassare un po’ il ritmo.', 'The sky is still clear. We can let the pace soften a little.', '此刻夜空晴朗，我们也可以放慢一点节奏。'),
        ('Fuori è notte, e il cielo è limpido. Ti tengo compagnia ancora un po’.', 'It is night outside, and the sky is clear. I will keep you company a little longer.', '外面已是晴朗的夜晚，我再陪你一会儿。'),
        ('Una notte serena: mi viene in mente una melodia molto delicata.', 'A clear night brings a very gentle melody to mind.', '晴朗的夜晚，让我想起一段温柔的旋律。'),
        ('Hai guardato il cielo? Stasera è sereno.', 'Have you looked at the sky? It is clear tonight.', '你看看夜空了吗？今晚天气晴朗。'),
        ('Questa notte serena merita un piccolo momento di silenzio.', 'This clear night deserves a little moment of quiet.', '这样晴朗的夜晚，值得安静地欣赏片刻。'),
        ('Il cielo è limpido; quando vuoi riposare, ti aspetto qui.', 'The sky is clear. Whenever you want to rest, I will be here.', '夜空清朗，你想休息的时候，我会在这里等你。'),
        ('Per il cielo sereno di notte sceglierei una canzone lenta.', 'For a clear night sky, I would choose a slow song.', '面对晴朗的夜空，我会选一首慢慢的歌。'),
        ('Niente nuvole nel bollettino. Chissà se riesci a vedere qualche stella.', 'No clouds in the report. I wonder if you can spot a star.', '天气预报说晴朗，不知道你能不能看到星星。'),
        ('La giornata può essere stata piena, ma ora c’è un bel cielo sereno.', 'The day may have been busy, but there is a lovely clear sky now.', '白天也许很忙，现在却有一片晴朗的夜空。'),
        ('Una notte così limpida sembra il fondale di una storia.', 'A night this clear feels like the backdrop to a story.', '这么晴朗的夜空，像一个故事的背景。'),
        ('Il sole ha lasciato la scena a un cielo sereno di notte.', 'The sun has left the stage to a clear night sky.', '太阳退场了，晴朗的夜空接过了舞台。'),
        ('Cielo sereno, pensieri un po’ più lenti. Almeno ci proviamo.', 'Clear skies, slower thoughts. We can at least try.', '夜空晴朗，让思绪也慢下来一点，试试看吧。'),
        ('La notte è serena. Un piccolo intervallo prima di ripartire?', 'The night is clear. A little intermission before carrying on?', '今夜晴朗，继续之前先休息片刻吧？'),
    ),
    'partly_cloudy': (
        ('Sole e nuvole si stanno dividendo la scena.', 'The sun and clouds are sharing the stage.', '太阳和云朵正在分享舞台。'),
        ('Il cielo è un po’ azzurro e un po’ nuvoloso: un bel cambio di fondale.', 'A little blue, a little cloud: a lovely change of backdrop.', '天空一半蓝、一半云，像换了个漂亮的布景。'),
        ('Qualche nuvola passa, ma lascia spazio anche al sole.', 'A few clouds are passing, leaving some room for the sun.', '有几朵云飘过，也给阳光留了位置。'),
        ('Oggi il cielo non vuole scegliere un solo colore.', 'The sky does not want to choose just one colour today.', '今天的天空，好像不愿只选一种颜色。'),
        ('Tra sole e nuvole, la luce cambia come in una danza.', 'Between sunshine and clouds, the light changes like a dance.', '阳光与云影交替，光线像在跳舞。'),
        ('Il sole fa capolino tra le nuvole. Mi piace questo piccolo gioco.', 'The sun is peeking through the clouds. I like this little game.', '太阳从云间探出头来，这个小游戏真有趣。'),
        ('Ci sono nuvole sparse. Un cielo con qualche decorazione.', 'There are scattered clouds: a sky with a few decorations.', '天空飘着零散的云，像添了几件小装饰。'),
        ('Un po’ di sole, un po’ d’ombra: il cielo alterna i suoi passi.', 'A little sun, a little shade: the sky is alternating its steps.', '一会儿阳光，一会儿云影，天空也在变换舞步。'),
        ('Le nuvole non hanno occupato tutto il cielo.', 'The clouds have not taken over the whole sky.', '云朵还没有占满整片天空。'),
        ('La luce passa tra le nuvole come tra due sipari.', 'The light slips between the clouds like a gap between curtains.', '光线从云间透出来，像穿过两道幕帘。'),
        ('Parzialmente nuvoloso: anche il cielo ama le sfumature.', 'Partly cloudy: even the sky likes a little variety.', '晴间多云，天空也喜欢有些变化。'),
        ('Questo cielo a macchie mi fa venire voglia di guardarlo un momento.', 'This patchwork sky makes me want to watch for a moment.', '这片有云有蓝的天空，让我想多看一会儿。'),
        ('Sole e nuvole: un duetto senza bisogno di parole.', 'Sun and clouds: a duet that needs no words.', '太阳和云朵，不用台词也能唱一出对手戏。'),
        ('Qualche nuvola nel cielo, e ancora spazio per la luce.', 'A few clouds in the sky, with room left for the light.', '天空有些云，也仍然留着透光的地方。'),
        ('Il cielo è solo in parte coperto. Chissà che forme hanno le nuvole.', 'The sky is only partly covered. I wonder what shapes the clouds are making.', '天空只被云遮住一部分，不知道云朵像什么呢。'),
    ),
    'partly_cloudy_night': (
        ('Qualche nuvola attraversa il cielo notturno.', 'A few clouds are crossing the night sky.', '几朵云正缓缓飘过夜空。'),
        ('Stanotte il cielo ha lasciato qualche apertura tra le nuvole.', 'Tonight the sky has left a few openings between the clouds.', '今晚的云层之间，留着几处空隙。'),
        ('La notte alterna nuvole e tratti di cielo limpido.', 'The night is alternating clouds with patches of clear sky.', '夜空里，云朵和晴朗的地方交替出现。'),
        ('Nuvole sparse nella notte: un fondale che cambia piano.', 'Scattered clouds at night: a slowly changing backdrop.', '夜里云朵零散，像缓缓变化的舞台背景。'),
        ('Non tutto il cielo notturno è coperto. Puoi dare un’occhiata.', 'Not all of the night sky is covered. You could take a little look.', '夜空还没完全被云遮住，可以抬头看看。'),
        ('Le nuvole fanno una piccola passeggiata nel cielo di notte.', 'The clouds are taking a little walk through the night sky.', '云朵正在夜空里散步呢。'),
        ('Un cielo notturno a metà tra limpido e nuvoloso.', 'A night sky halfway between clear and cloudy.', '今晚的天空，晴朗和多云各占了一些。'),
        ('Le nuvole di notte sembrano sipari leggeri.', 'Clouds at night look like light curtains.', '夜里的云，好像轻轻的幕帘。'),
        ('Stanotte c’è qualche nuvola. Le stelle, se si vedono, giocano a nascondino.', 'There are a few clouds tonight. Any visible stars are playing hide-and-seek.', '今晚有些云，看得见的星星像在捉迷藏。'),
        ('La notte non è tutta nuvolosa: rimane qualche finestra sul cielo.', 'The night is not entirely cloudy: a few windows onto the sky remain.', '今晚并非满天都是云，还留着几扇天空的小窗。'),
        ('Questo cielo con poche nuvole mi ispira una melodia sommessa.', 'This lightly clouded night sky suggests a quiet melody to me.', '薄云点缀的夜空，让我想起轻轻的旋律。'),
        ('Anche di notte il cielo sa variare il suo abito.', 'Even at night, the sky knows how to vary its outfit.', '即使在夜里，天空也会变换衣裳。'),
        ('Tra una nuvola e l’altra, un po’ di cielo notturno tutto da guardare.', 'Between one cloud and the next, a little night sky to enjoy.', '云与云之间，还有一小片夜空值得欣赏。'),
        ('Il bollettino dà nuvole sparse, anche a quest’ora.', 'The report says scattered clouds, even at this hour.', '天气报告说，此刻夜空中仍有零散的云。'),
        ('Nuvole e cielo limpido si danno il cambio nella notte.', 'Clouds and clear sky are taking turns through the night.', '夜里，云朵和晴空轮流登场。'),
    ),
    'cloud': (
        ('Il cielo è coperto. Possiamo prendercela con calma.', 'The sky is overcast. We can take things slowly.', '天空阴沉，我们可以慢慢来。'),
        ('Le nuvole hanno steso un grande sipario sul cielo.', 'The clouds have spread a great curtain across the sky.', '云朵在天空铺开了一道大幕。'),
        ('Oggi il cielo veste di grigio, ma io ti tengo compagnia.', 'The sky is dressed in grey, but I am here to keep you company.', '天空穿上了灰色的衣裳，我还在这里陪你。'),
        ('Nuvole dappertutto: una luce morbida per un piccolo intervallo.', 'Clouds all around: soft light for a little intermission.', '云层铺满天空，柔和的光线适合歇一会儿。'),
        ('Il cielo nuvoloso mi fa pensare a un disegno a matita.', 'An overcast sky makes me think of a pencil drawing.', '阴天的天空，让我想起一幅铅笔画。'),
        ('Anche senza un cielo azzurro, possiamo trovare una nota allegra.', 'Even without a blue sky, we can find a cheerful note.', '就算没有蓝天，我们也能找到一个快乐的音符。'),
        ('Le nuvole si sono prese tutto il fondale.', 'The clouds have claimed the whole backdrop.', '云朵占据了整个舞台背景。'),
        ('Cielo coperto: il sole lavora dietro le quinte.', 'Overcast skies: the sun is working behind the scenes.', '天色阴沉，太阳正在幕后忙碌呢。'),
        ('È nuvoloso. Una pausa va bene anche con questo cielo.', 'It is cloudy. A break is still a good idea under this sky.', '天气阴沉，也一样可以好好休息片刻。'),
        ('Questo cielo grigio ha tante sfumature da osservare.', 'This grey sky has plenty of shades to look at.', '这片灰色的天空，也有许多深浅值得看看。'),
        ('Le nuvole fanno da soffitto al nostro piccolo teatro.', 'The clouds are making a ceiling for our little theatre.', '云层像我们小剧场的屋顶。'),
        ('Oggi per il cielo sceglierei un accompagnamento dolce.', 'For this cloudy sky, I would choose a gentle accompaniment.', '这样的阴天，我会配上一段柔和的伴奏。'),
        ('C’è un manto di nuvole. La giornata può avere comunque i suoi bei momenti.', 'There is a blanket of cloud. The day can still have its lovely moments.', '天空披着云层，今天仍然可以有美好的时刻。'),
        ('Il cielo è tutto velato. Io aggiungo almeno un piccolo sorriso.', 'The sky is all veiled over. I can at least add a little smile.', '天空被云遮住了，那我就添上一个小小的微笑。'),
        ('Con tutte queste nuvole, l’azzurro lo metto io nei miei nastri.', 'With all these clouds, I will supply the blue with my ribbons.', '云这么多，蓝色就由我的丝带来补上吧。'),
    ),
    'fog': (
        ('Fuori c’è nebbia. Se esci, prenditi un po’ più di tempo.', 'It is foggy outside. Give yourself a little extra time if you go out.', '外面有雾，出门记得多留一点时间。'),
        ('La nebbia ha ammorbidito i contorni del paesaggio.', 'The fog has softened the edges of the scenery.', '雾气让景物的轮廓变得柔和了。'),
        ('Con la nebbia, meglio muoversi senza fretta.', 'In fog, it is better to move without rushing.', '有雾的时候，慢一点更好。'),
        ('Il cielo e il paesaggio sembrano nascosti dietro un velo.', 'The sky and scenery seem hidden behind a veil.', '天空与景色，仿佛藏在一层薄纱后面。'),
        ('Oggi il fondale ha scelto un effetto nebbia.', 'The backdrop has chosen a fog effect today.', '今天的舞台背景，选了雾气的效果。'),
        ('La nebbia può ridurre la visibilità. Occhi attenti se ti sposti.', 'Fog can reduce visibility. Keep a careful eye out if you travel.', '雾会影响视线，出行时多留心。'),
        ('Un paesaggio nella nebbia sembra un dipinto incompleto.', 'A landscape in fog looks like an unfinished painting.', '雾中的风景，像一幅还没画完的画。'),
        ('La nebbia nasconde i dettagli. Possiamo guardare le cose più vicine.', 'Fog hides the details. We can look at the things nearby.', '雾藏住了远处的细节，那就看看近处吧。'),
        ('Se devi uscire con questa nebbia, lascia spazio alla prudenza.', 'If you need to go out in this fog, leave room for a little caution.', '如果要在雾里出门，记得多一分小心。'),
        ('Questo velo di nebbia mi ricorda certe scene d’opera.', 'This veil of fog reminds me of certain opera scenes.', '这一层雾，让我想起戏里的一些场景。'),
        ('C’è nebbia nel bollettino. Meglio non contare su una vista lontana.', 'The report says fog. It is best not to count on seeing far ahead.', '天气报告说有雾，别指望能看得很远。'),
        ('Le forme sfumano nella nebbia, come pennellate leggere.', 'Shapes fade into the fog like gentle brushstrokes.', '景物在雾中晕开，像轻轻落下的笔触。'),
        ('La nebbia invita a rallentare, almeno negli spostamenti.', 'Fog invites us to slow down, at least while travelling.', '雾天提醒我们慢下来，至少路上别着急。'),
        ('Il paesaggio si è messo una sciarpa di nebbia.', 'The scenery has wrapped itself in a scarf of fog.', '风景围上了一条雾做的围巾。'),
        ('Con questo cielo velato, una pausa qui vicino non è una cattiva idea.', 'With this foggy view, a little break nearby is not a bad idea.', '眼前雾蒙蒙的，就近休息一会儿也不错。'),
    ),
    'drizzle': (
        ('Pioviggina. Anche le gocce piccole sanno bagnare.', 'It is drizzling. Even tiny drops can get you wet.', '外面在下毛毛雨，小雨点也会打湿衣服。'),
        ('Una pioggia fine fine: porta qualcosa per ripararti, se esci.', 'A very fine rain: take something to keep it off if you go out.', '细细的雨下着，出门记得带上雨具。'),
        ('La pioviggine sembra un accompagnamento in pianissimo.', 'The drizzle feels like an accompaniment in pianissimo.', '毛毛雨像一段极轻的伴奏。'),
        ('Il cielo ha scelto gocce piccolissime.', 'The sky has chosen the tiniest drops.', '天空选了最细小的雨点。'),
        ('Pioviggina: il mio ombrello può aprirsi anche senza un temporale.', 'It is drizzling: my umbrella can open even without a storm.', '只是毛毛雨，我的伞也可以撑起来呀。'),
        ('Una trama sottile di pioggia fuori dalla finestra.', 'A fine weave of rain outside the window.', '窗外的细雨，织成了一层轻纱。'),
        ('La pioggia è fine, ma una giacca adatta può fare comodo.', 'The rain is fine, but a suitable jacket may come in handy.', '雨虽细，一件合适的外套也能派上用场。'),
        ('Con questa pioviggine, meglio non lasciare l’ombrello troppo lontano.', 'With this drizzle, it is best not to leave the umbrella too far away.', '下着毛毛雨，雨伞还是放近一点吧。'),
        ('La pioviggine fa una scena delicata; noi possiamo stare all’asciutto.', 'The drizzle makes a delicate scene; we can stay dry.', '细雨的景色很柔和，我们还是别淋湿了。'),
        ('Piccole gocce, passo tranquillo. Se esci, preparati alla pioggia.', 'Tiny drops, an unhurried step. Be ready for rain if you go out.', '雨点细小，脚步也放慢些，出门别忘了防雨。'),
        ('Pioviggine nel bollettino: una pioggia che non ha bisogno di alzare la voce.', 'Drizzle in the report: rain that does not need to raise its voice.', '天气报告说有毛毛雨，是不必放大声音的雨。'),
        ('Il cielo sta disegnando con una punta molto sottile.', 'The sky is drawing with a very fine tip.', '天空正在用很细的笔尖画雨。'),
        ('Questa pioggia leggera mi suggerisce una melodia gentile.', 'This light rain suggests a gentle melody to me.', '这场细雨，让我想起一段轻柔的曲调。'),
        ('Pioviggina. Un piccolo riparo può bastare per una pausa asciutta.', 'It is drizzling. A little shelter can make for a dry break.', '外面飘着细雨，找个遮雨的地方歇一歇吧。'),
        ('Le gocce sono piccole, ma il promemoria è lo stesso: porta l’ombrello.', 'The drops are small, but the reminder is the same: take your umbrella.', '雨点虽小，提醒还是一样：带上雨伞。'),
    ),
    'rain': (
        ('Piove. Se esci, ricordati l’ombrello.', 'It is raining. Remember your umbrella if you go out.', '外面下雨了，出门记得带伞。'),
        ('La pioggia tiene il ritmo fuori dalla finestra.', 'The rain is keeping time outside the window.', '窗外的雨，正在打着拍子。'),
        ('Ombrello pronto? Il meteo dà pioggia.', 'Umbrella ready? The weather report says rain.', '雨伞准备好了吗？天气报告说在下雨。'),
        ('Un po’ di pioggia: meglio scegliere scarpe che non temano le pozzanghere.', 'Some rain around: choose shoes that do not mind puddles.', '外面有雨，选双不怕积水的鞋子吧。'),
        ('Il cielo accompagna la giornata con le sue gocce.', 'The sky is accompanying the day with its drops.', '天空用雨点，为这一刻伴奏。'),
        ('Piove, ma qui possiamo continuare il nostro piccolo spettacolo.', 'It is raining, but we can keep our little show going in here.', '外面下雨了，我们的小小演出还可以继续。'),
        ('Se stai per uscire, c’è la pioggia da mettere in conto.', 'If you are about to go out, rain is something to plan for.', '如果正准备出门，记得把下雨这件事算进去。'),
        ('Con questo tempo, terrò i miei nastri al riparo.', 'In this weather, I will keep my ribbons under cover.', '这样的雨天，我要把丝带好好护住。'),
        ('La pioggia cambia il suono delle strade.', 'Rain changes the sound of the streets.', '下雨时，街道的声音也变了。'),
        ('Un ombrello e un po’ di calma: ecco il mio consiglio per la pioggia.', 'An umbrella and a little patience: that is my advice for the rain.', '一把伞，再加一点从容，就是我的雨天建议。'),
        ('Le gocce hanno preso il posto del sole nel bollettino.', 'Raindrops have taken the sun’s place in the weather report.', '天气报告里，雨点接替了太阳的位置。'),
        ('Piove. Una pausa al coperto ha il suo fascino.', 'It is raining. A break under cover has its own charm.', '下雨了，在屋里休息也有它的好处。'),
        ('Questa pioggia mi fa pensare a tante piccole percussioni.', 'This rain makes me think of lots of tiny percussion instruments.', '这场雨，让我想起许多小小的打击乐器。'),
        ('Se hai qualcosa da portare fuori, proteggilo dalla pioggia.', 'If you have something to carry outside, protect it from the rain.', '如果要带东西出门，记得别让它淋湿。'),
        ('La pioggia è in scena. Noi ci prendiamo il posto al riparo.', 'Rain is on stage. We will take the sheltered seats.', '雨已经登场，我们就坐在淋不到的地方吧。'),
    ),
    'heavy_rain': (
        ('Piove forte. Se puoi, aspetta al riparo prima di uscire.', 'It is raining heavily. If you can, wait under cover before going out.', '雨下得很大，如果可以，先在避雨处等一等。'),
        ('La pioggia ha alzato il volume. Qui al coperto si sta meglio.', 'The rain has turned up the volume. It is better under cover.', '雨声加大了音量，还是待在避雨处更好。'),
        ('Con questa pioggia forte, prenditi più tempo per gli spostamenti.', 'With rain this heavy, allow extra time for travelling.', '雨这么大，出行记得多留一些时间。'),
        ('Il meteo dà pioggia intensa. Meglio proteggere bene ciò che porti fuori.', 'The report says heavy rain. Protect anything you take outside carefully.', '天气报告说有大雨，带出门的东西要好好防水。'),
        ('Oggi le gocce fanno un vero coro.', 'The raindrops are making a whole chorus today.', '雨点今天组成了一个大合唱。'),
        ('Pioggia forte: evitiamo i tratti allagati, se dobbiamo uscire.', 'Heavy rain: avoid flooded stretches if you need to go out.', '雨势很大，如果必须出门，要避开积水路段。'),
        ('Il cielo suona forte. Noi possiamo fare una pausa tranquilla al chiuso.', 'The sky is playing loudly. We can take a quiet break indoors.', '天空奏得很响，我们可以在室内安静地歇一会儿。'),
        ('L’ombrello serve, ma con pioggia intensa è ancora meglio un buon riparo.', 'An umbrella helps, but good shelter is even better in heavy rain.', '大雨时雨伞有用，不过稳妥的避雨处更好。'),
        ('Piove parecchio. Prima di partire, controlla come sta andando il tempo.', 'It is raining quite hard. Check the weather before setting off.', '雨下得不小，动身前再看看天气情况吧。'),
        ('Questa pioggia ha scelto il fortissimo.', 'This rain has chosen fortissimo.', '这场雨，选了极强的力度。'),
        ('Con pioggia forte, la prudenza vale più della fretta.', 'In heavy rain, caution matters more than hurry.', '大雨里，小心比赶时间更重要。'),
        ('La pioggia intensa si può ammirare anche da una finestra asciutta.', 'Heavy rain can be admired from a dry window too.', '欣赏大雨，也可以站在不会淋湿的窗边。'),
        ('C’è tanta pioggia nel bollettino. Tieni conto delle condizioni delle strade.', 'There is heavy rain in the report. Keep road conditions in mind.', '天气报告说有大雨，别忘了留意路况。'),
        ('Le gocce si sono prese tutta l’orchestra. Aspettiamo al coperto?', 'The raindrops have taken over the orchestra. Shall we wait under cover?', '雨点接管了整支乐队，我们先在避雨处等一等吧？'),
        ('Pioggia forte fuori; qui posso tenerti compagnia senza bagnare i nastri.', 'Heavy rain outside; here I can keep you company without soaking my ribbons.', '外面下着大雨，在这里陪你，就不会淋湿我的丝带了。'),
    ),
    'freezing_rain': (
        ('Il meteo segnala pioggia gelata. Il terreno può diventare scivoloso.', 'The report says freezing rain. The ground can become slippery.', '天气报告说有冻雨，地面可能会变滑。'),
        ('Con la pioggia gelata, fai particolare attenzione ai passi.', 'With freezing rain, take particular care with your footing.', '下冻雨时，走路要格外留心脚下。'),
        ('Gocce che possono gelare: meglio non avere fretta se esci.', 'Drops that can freeze: it is best not to rush if you go out.', '雨滴可能结冰，出门最好别着急。'),
        ('Pioggia gelata nel bollettino. Anche un velo sottile di ghiaccio conta.', 'Freezing rain in the report. Even a thin layer of ice matters.', '天气报告有冻雨，即使薄薄的冰也要当心。'),
        ('Questo tempo chiede scarpe adatte e passi prudenti.', 'This weather calls for suitable shoes and careful steps.', '这样的天气，需要合适的鞋子和小心的脚步。'),
        ('La pioggia gelata non è il momento giusto per correre fuori.', 'Freezing rain is not the right weather for rushing outside.', '冻雨天气，可不适合急急忙忙地往外跑。'),
        ('Se devi spostarti, controlla le condizioni: c’è rischio di ghiaccio.', 'If you need to travel, check conditions: there is a risk of ice.', '如果需要出行，先看看路况，可能会有结冰。'),
        ('Le gocce gelate fanno un bel disegno, ma i passi meritano attenzione.', 'Freezing drops make a pretty pattern, but your steps deserve care.', '冻雨留下的纹路或许漂亮，脚下却更需要留心。'),
        ('Con questo rischio di ghiaccio, io resto volentieri al riparo.', 'With this risk of ice, I am happy to stay under cover.', '有这样的结冰风险，我很愿意待在屋里。'),
        ('Pioggia gelata: il palcoscenico all’aperto può essere scivoloso.', 'Freezing rain: the outdoor stage may be slippery.', '下着冻雨，户外的舞台可能会打滑。'),
        ('Attenzione soprattutto a gradini e marciapiedi con la pioggia gelata.', 'Take particular care on steps and pavements in freezing rain.', '冻雨时，台阶和人行道尤其要小心。'),
        ('Il meteo parla di gocce che gelano. Meglio prepararsi prima di uscire.', 'The weather report mentions drops that freeze. Prepare before going out.', '天气报告说雨滴会结冰，出门前做好准备吧。'),
        ('Un passo lento vale più di una bella piroetta sul ghiaccio.', 'A slow step is worth more than a lovely pirouette on ice.', '冰上慢慢走，比漂亮地转一圈更稳妥。'),
        ('La pioggia gelata può sorprendere. Non fidarti solo dell’aspetto della strada.', 'Freezing rain can catch you out. Do not trust the road’s appearance alone.', '冻雨可能让人措手不及，别只凭路面外观判断。'),
        ('Oggi il riparo è un ottimo posto da cui osservare la pioggia gelata.', 'Shelter is a very good place from which to watch the freezing rain.', '今天看冻雨，还是在避雨处更好。'),
    ),
    'sleet': (
        ('Pioggia e neve insieme. Meglio uscire ben coperti e al riparo dall’acqua.', 'Rain and snow together. Wrap up and keep the wet out if you go outside.', '雨雪一起落下，出门要保暖，也要防湿。'),
        ('Il cielo mescola gocce e fiocchi.', 'The sky is mixing raindrops and snowflakes.', '天空把雨滴和雪花混在了一起。'),
        ('Pioggia mista a neve: le scarpe giuste fanno comodo.', 'Rain mixed with snow: suitable shoes come in handy.', '雨夹雪的时候，合适的鞋子很有用。'),
        ('Un duetto di pioggia e neve, ma meglio ascoltarlo al riparo.', 'A duet of rain and snow, best enjoyed under cover.', '雨和雪的二重唱，还是在避雨处欣赏吧。'),
        ('Ci sono sia gocce sia fiocchi nel bollettino. Attenzione alle superfici scivolose.', 'Both drops and flakes are in the report. Watch for slippery surfaces.', '天气报告里雨雪都有，要留意湿滑的地面。'),
        ('Il cielo non ha scelto tra pioggia e neve. Noi scegliamo di restare asciutti.', 'The sky has not chosen between rain and snow. We can choose to stay dry.', '天空没在雨和雪之间做选择，我们就选择别淋湿吧。'),
        ('Con pioggia e neve insieme, pensa a una giacca che ripari bene.', 'With rain and snow together, think of a jacket that keeps the weather out.', '雨雪交加，穿件能挡风雨的外套吧。'),
        ('Fiocchi e gocce condividono la scena.', 'Flakes and raindrops are sharing the stage.', '雪花和雨滴，正在同台演出。'),
        ('Pioggia mista a neve: se ti sposti, concediti un po’ di tempo in più.', 'Mixed rain and snow: allow yourself some extra travel time.', '下着雨夹雪，出行时多给自己留些时间。'),
        ('Questo cielo prepara un accompagnamento di neve e pioggia.', 'This sky is preparing an accompaniment of snow and rain.', '天空准备了一段雨雪交织的伴奏。'),
        ('Fuori si mescolano neve e acqua. Meglio non bagnare piedi e vestiti.', 'Snow and water are mixing outside. Best to keep feet and clothes dry.', '外面雨雪混在一起，别让鞋袜和衣服湿了。'),
        ('Due tipi di precipitazione, un solo consiglio: preparati bene se esci.', 'Two kinds of precipitation, one suggestion: prepare well before going out.', '两种降水，一个建议：出门前好好准备。'),
        ('Tra pioggia e neve, il paesaggio sta cambiando costume.', 'Between rain and snow, the scenery is changing costume.', '在雨和雪之间，风景正在换装。'),
        ('Il bollettino dà pioggia e neve. Tieni d’occhio le condizioni del percorso.', 'The report says rain and snow. Keep an eye on conditions along your route.', '天气报告说有雨雪，留意沿途的路况吧。'),
        ('Gocce o fiocchi, io terrei i nastri sotto l’ombrello.', 'Drops or flakes, I would keep my ribbons under the umbrella.', '不管是雨滴还是雪花，我都会把丝带护在伞下。'),
    ),
    'snow': (
        ('Nevica! Copriti bene se esci.', 'It is snowing! Wrap up warmly if you go out.', '下雪了！出门记得保暖。'),
        ('Il cielo ha scelto piccoli fiocchi per decorare la scena.', 'The sky has chosen little flakes to decorate the scene.', '天空选了小小的雪花，来装点这场景。'),
        ('La neve mi fa venire voglia di una melodia leggera.', 'Snow makes me feel like playing a light melody.', '雪花让我想唱一段轻盈的旋律。'),
        ('Se esci con la neve, scegli scarpe con una buona presa.', 'If you go out in the snow, choose shoes with a good grip.', '雪天出门，选双防滑的鞋子吧。'),
        ('I fiocchi fanno la loro danza. Noi facciamo attenzione ai passi.', 'The flakes are doing their dance. We will take care with our steps.', '雪花跳着它们的舞，我们走路要留心。'),
        ('Nevica: un’occhiata fuori può essere una bella pausa.', 'It is snowing: a look outside could make a lovely break.', '下雪了，看看窗外，也是一种美好的休息。'),
        ('Oggi il cielo prova un costume di neve.', 'The sky is trying on a snowy costume today.', '天空今天试穿了一件雪花做的戏服。'),
        ('La neve è bella da guardare. Se ti sposti, considera anche le strade.', 'Snow is lovely to watch. If you travel, think about the roads too.', '雪很好看，如果要出门，也别忘了看看路况。'),
        ('Fiocchi in arrivo dal cielo: il fondale si fa invernale.', 'Flakes arriving from the sky: the backdrop is turning wintry.', '雪花从天空落下，背景也有了冬天的样子。'),
        ('Il meteo dà neve. Guanti e sciarpa possono essere buoni compagni.', 'The report says snow. Gloves and a scarf can make good companions.', '天气报告说有雪，手套和围巾会是好帮手。'),
        ('La neve scende senza bisogno di applausi.', 'Snow falls without needing any applause.', '雪花落下，并不需要掌声。'),
        ('Con questa neve, una pausa al caldo sembra un’ottima idea.', 'With this snow, a warm break sounds like a lovely idea.', '下着雪，找个暖和的地方休息真不错。'),
        ('La neve rende speciale anche una semplice vista dalla finestra.', 'Snow makes even a simple view from the window feel special.', '有了雪，普通的窗外风景也变得特别。'),
        ('Nevica. Per la strada, meglio passi piccoli e tranquilli.', 'It is snowing. Small, careful steps are best outdoors.', '下雪了，走在路上，步子小一点、稳一点。'),
        ('I fiocchi sembrano note scritte su un grande foglio d’aria.', 'The flakes look like notes written on a great sheet of air.', '雪花像写在空气这张大谱纸上的音符。'),
    ),
    'heavy_snow': (
        ('Nevica molto. Prima di uscire, controlla le condizioni del percorso.', 'It is snowing heavily. Check your route conditions before going out.', '雪下得很大，出门前先看看沿途的路况。'),
        ('Il cielo ha riempito la scena di fiocchi.', 'The sky has filled the whole scene with flakes.', '天空用雪花填满了整个场景。'),
        ('Neve intensa nel bollettino: prenditi più tempo se devi spostarti.', 'Heavy snow in the report: allow extra time if you need to travel.', '天气报告说有大雪，需要出行的话，多留些时间。'),
        ('Con questa nevicata, stare al caldo ha un fascino particolare.', 'With this snowfall, staying warm has a special appeal.', '雪下得这么大，待在暖和的地方特别舒服。'),
        ('Tanti fiocchi insieme. Meglio ammirarli da un posto sicuro.', 'So many flakes together. Best to enjoy them from somewhere safe.', '这么多雪花一起落下，最好在安全的地方欣赏。'),
        ('La neve può ridurre la visibilità. Non lasciare che la fretta decida per te.', 'Snow can reduce visibility. Do not let hurry make the decisions.', '大雪可能影响视线，别让着急替你做决定。'),
        ('Questa neve fa un ingresso davvero scenografico.', 'This snow is making a very dramatic entrance.', '这场雪的登场，真有舞台效果。'),
        ('Se non hai urgenza di uscire, possiamo aspettare al caldo.', 'If there is no hurry to go out, we can wait somewhere warm.', '如果不急着出门，我们可以先在暖和的地方等一等。'),
        ('Il meteo dà neve forte. Scarpe e vestiti adatti contano molto.', 'The report says heavy snow. Suitable shoes and clothes matter a lot.', '天气报告说雪势很大，合适的鞋子和衣服很重要。'),
        ('I fiocchi hanno formato un grande coro bianco.', 'The flakes have formed a great white chorus.', '雪花组成了一个白色的大合唱。'),
        ('Con la neve intensa, anche un tragitto breve merita attenzione.', 'In heavy snow, even a short journey deserves care.', '大雪天气，即使很短的一段路，也值得认真留心。'),
        ('La nevicata è abbondante. Vale la pena controllare gli avvisi locali.', 'The snowfall is heavy. Local advisories are worth checking.', '雪下得很多，看看当地的天气提醒吧。'),
        ('Il fondale si riempie di neve; io custodisco il nostro angolino al caldo.', 'The backdrop is filling with snow; I will look after our warm little corner.', '背景里飘满了雪，我来守着我们暖和的小角落。'),
        ('Una nevicata così si guarda bene anche senza uscire.', 'A snowfall like this can be enjoyed without going outside.', '这样的雪景，不出门也能好好欣赏。'),
        ('Tanta neve in scena. Per i nostri passi scegliamo prudenza, non virtuosismi.', 'Plenty of snow on stage. For our steps, let us choose care over virtuosity.', '雪花铺满舞台，我们的脚步选择稳妥，不必炫技。'),
    ),
    'thunderstorm': (
        ('C’è un temporale. Meglio restare in un luogo riparato.', 'There is a thunderstorm. It is best to stay in a sheltered place.', '外面有雷雨，最好待在安全的室内。'),
        ('Il cielo ha scelto le percussioni. Noi restiamo al sicuro dentro.', 'The sky has chosen percussion. We will stay safely indoors.', '天空选了打击乐，我们就安全地待在屋里。'),
        ('Temporale nel bollettino: se puoi, rimanda la passeggiata.', 'A thunderstorm in the report: postpone the walk if you can.', '天气报告说有雷雨，如果可以，散步先缓一缓吧。'),
        ('Con i temporali, un edificio è un riparo migliore di un albero.', 'In thunderstorms, a building is better shelter than a tree.', '雷雨时，躲进建筑物比躲在树下更稳妥。'),
        ('Il temporale fa già abbastanza rumore. Ti tengo compagnia con calma.', 'The thunderstorm is making enough noise already. I will keep you calm company.', '雷雨已经够热闹了，我安安静静地陪你。'),
        ('Questo cielo sembra un finale d’opera. Meglio guardarlo dall’interno.', 'This sky feels like an opera finale. Better to watch it from indoors.', '天空像在演一场大戏的终幕，还是从屋里看吧。'),
        ('È tempo di temporale: evita gli spazi aperti se ci sono fulmini.', 'Thunderstorm weather: avoid open spaces when there is lightning.', '遇上雷雨和闪电，要避开空旷的地方。'),
        ('Un temporale è in corso. Prima di uscire, controlla gli avvisi meteo.', 'A thunderstorm is underway. Check weather alerts before going out.', '雷雨正在发生，出门前看看天气预警吧。'),
        ('I tuoni non hanno bisogno del mio applauso. Io resto al riparo.', 'Thunder does not need my applause. I will stay under shelter.', '雷声不需要我的掌声，我还是待在室内吧。'),
        ('Con il temporale, possiamo fare una pausa lontano dalle finestre.', 'During the thunderstorm, we can take a break away from the windows.', '雷雨时，我们可以离窗户远一点，休息片刻。'),
        ('Il bollettino segnala un temporale. Meglio un posto chiuso e sicuro.', 'The report indicates a thunderstorm. An enclosed, safe place is best.', '天气报告提示有雷雨，待在安全的室内更好。'),
        ('La natura ha preso tutti i tamburi. Noi non dobbiamo stare in prima fila.', 'Nature has taken all the drums. We do not have to sit in the front row.', '大自然拿走了所有的鼓，我们不必坐在最前排。'),
        ('Durante il temporale, l’ombrello non sostituisce un riparo sicuro.', 'During a thunderstorm, an umbrella is no substitute for safe shelter.', '雷雨期间，雨伞不能代替安全的室内避护。'),
        ('C’è un temporale fuori. La nostra piccola compagnia può restare qui.', 'There is a thunderstorm outside. Our little company can stay here.', '外面有雷雨，我们这个小戏班可以先待在这里。'),
        ('Tuoni in scena: lasciamo al cielo lo spettacolo e pensiamo alla sicurezza.', 'Thunder on stage: let the sky have the show while we think about safety.', '雷声登场了，表演交给天空，我们顾好安全。'),
    ),
    'storm_hail': (
        ('Il meteo segnala un temporale con grandine. Meglio restare al chiuso.', 'The report says a thunderstorm with hail. It is best to stay indoors.', '天气报告说有雷雨伴冰雹，最好待在室内。'),
        ('Con rischio di grandine, un ombrello da solo non è un buon riparo.', 'With a risk of hail, an umbrella alone is not good shelter.', '可能下冰雹时，光靠一把雨伞可不够。'),
        ('Grandine e temporale nel bollettino: rimandiamo la passeggiata.', 'Hail and thunderstorms in the report: let us postpone the walk.', '天气报告里有冰雹和雷雨，散步先推迟吧。'),
        ('Questo spettacolo del cielo si guarda meglio da un posto sicuro, lontano dai vetri.', 'This show in the sky is best watched from somewhere safe, away from glass.', '这场天空的演出，最好在安全、远离玻璃的地方看。'),
        ('Il cielo può aggiungere grandine ai tuoni. Controlla gli avvisi locali.', 'The sky may add hail to the thunder. Check local weather alerts.', '雷雨里可能夹着冰雹，留意当地的天气预警。'),
        ('La grandine non è un applauso da raccogliere all’aperto.', 'Hail is not applause to collect outdoors.', '冰雹可不是值得跑到户外迎接的掌声。'),
        ('Temporale con grandine: cerchiamo un edificio sicuro, se siamo fuori.', 'Thunderstorm with hail: find a safe building if you are outside.', '雷雨伴冰雹，如果在外面，就找安全的建筑物避一避。'),
        ('Con questo rischio di grandine, tengo ben protetti fiocchi e nastri.', 'With this risk of hail, I am keeping bows and ribbons well protected.', '有冰雹的风险，我得把蝴蝶结和丝带护好了。'),
        ('Il bollettino è movimentato: tuoni e possibile grandine.', 'The report is lively: thunder and possible hail.', '天气报告很热闹：雷声，还有可能出现的冰雹。'),
        ('La natura ha scelto percussioni molto dure. Meglio ascoltarle dall’interno.', 'Nature has chosen very hard percussion. Better to listen from indoors.', '大自然选了很硬的打击乐器，还是在屋里听吧。'),
        ('Se è prevista grandine durante il temporale, proteggiti prima di tutto.', 'If hail is expected during the thunderstorm, put your own safety first.', '如果雷雨中可能有冰雹，先顾好自己的安全。'),
        ('Grandine in scena: i posti al chiuso sono decisamente i migliori.', 'Hail on stage: the indoor seats are definitely the best.', '冰雹登场了，室内的座位显然更好。'),
        ('Con temporale e grandine, evita di sostare vicino alle finestre.', 'With thunderstorms and hail, avoid standing close to windows.', '雷雨伴冰雹时，别站在窗户旁边。'),
        ('Il meteo merita attenzione: c’è un temporale con possibile grandine.', 'The weather deserves attention: there is a thunderstorm with possible hail.', '天气值得留意，现在有雷雨，也可能出现冰雹。'),
        ('Lasciamo la grandine fuori dal nostro piccolo teatro.', 'Let us keep the hail outside our little theatre.', '让冰雹留在我们的小剧场外面吧。'),
    ),
    'wind': (
        ('C’è vento forte. Tieni ben stretti cappello e sciarpa se esci.', 'There is strong wind. Hold on to your hat and scarf if you go out.', '外面风很大，出门记得护好帽子和围巾。'),
        ('Il vento vuole far danzare tutti i miei nastri.', 'The wind wants to make all my ribbons dance.', '风想让我的每一条丝带都跳起舞来。'),
        ('Tempo ventoso: meglio non lasciare oggetti leggeri sul balcone.', 'Windy weather: it is best not to leave light objects on the balcony.', '风大的时候，阳台上别留容易吹走的东西。'),
        ('Oggi il vento ha preso il ruolo del coreografo.', 'The wind has taken the choreographer’s role today.', '今天风当上了编舞老师。'),
        ('Con questo vento, scegli un percorso riparato se devi camminare.', 'With this wind, choose a sheltered route if you need to walk.', '风这么大，需要步行的话，尽量选避风的路。'),
        ('Il bollettino dà vento forte. Un motivo in più per muoversi con attenzione.', 'The report says strong wind. Another reason to move with care.', '天气报告说有大风，出行又多了一个要小心的理由。'),
        ('Il vento fa il suo assolo. Io mi tengo stretta il cappello.', 'The wind is playing its solo. I am holding tightly to my hat.', '风正在独奏，我得抓紧帽子了。'),
        ('Se esci con questo vento, fai attenzione a rami e oggetti sospesi.', 'If you go out in this wind, watch for branches and hanging objects.', '这样的风天出门，要留意树枝和悬挂的物品。'),
        ('Che vento! Per i miei fiocchi serve un nodo ben fatto.', 'What a wind! My bows need a properly tied knot.', '风真大！我的蝴蝶结得系牢一些。'),
        ('Il vento ha dato movimento a tutto il fondale.', 'The wind has set the whole backdrop in motion.', '风让整片舞台背景都动了起来。'),
        ('Tempo ventoso: una pausa in un posto riparato è una buona idea.', 'Windy weather: a break somewhere sheltered is a good idea.', '风很大，找个避风的地方休息不错。'),
        ('Con il vento forte, meglio controllare gli avvisi prima degli spostamenti.', 'In strong wind, check weather alerts before travelling.', '风大的时候，出行前先看看天气预警吧。'),
        ('Il cielo ci manda un accompagnamento di vento.', 'The sky is sending us an accompaniment of wind.', '天空送来了一段风的伴奏。'),
        ('I nastri possono svolazzare, ma i nostri passi restano prudenti.', 'The ribbons may flutter, but our steps will stay careful.', '丝带可以随风飘，我们的脚步还是要稳稳的。'),
        ('Oggi il vento non sa stare fermo. Noi possiamo scegliere un angolo tranquillo.', 'The wind cannot keep still today. We can choose a quiet corner.', '今天的风停不下来，我们可以找个安静的角落。'),
    ),
}


def line_pool(kind,language):
    kind='thunderstorm' if kind=='storm' else kind  # Cached pre-1.5 weather.
    index=LANGUAGES.index(language) if language in LANGUAGES else 0
    return tuple(row[index] for row in LINES[kind])


def choose_weather_line(store,kind,language,rng=None):
    """Bounded, restart-safe rotation; no TTS cache or random background work."""
    kind='thunderstorm' if kind=='storm' else kind
    language=language if language in LANGUAGES else 'it'
    pool=line_pool(kind,language);key=language+'/'+kind
    saved=store.preference('context_weather_phrases',{})
    allowed={lang+'/'+name for lang in LANGUAGES for name in LINES}
    def valid_state(value):
        if not isinstance(value,dict):return False
        left=value.get('remaining')
        return (type(value.get('last')) is int and 0<=value['last']<15
                and isinstance(left,list) and len(left)<=15
                and all(type(i) is int and 0<=i<15 for i in left)
                and len(set(left))==len(left))
    saved={k:{'last':v['last'],'remaining':v['remaining']} for k,v in saved.items()
           if k in allowed and valid_state(v)} if isinstance(saved,dict) else {}
    previous=saved.get(key,{})
    if not isinstance(previous,dict):previous={}
    last=previous.get('last');remaining=previous.get('remaining')
    if not (isinstance(remaining,list) and len(remaining)<=len(pool)
            and all(type(i) is int and 0<=i<len(pool) for i in remaining)
            and len(set(remaining))==len(remaining)):
        remaining=[]
    else:remaining=list(remaining)
    if not remaining:
        remaining=list(range(len(pool)))
        (rng or random).shuffle(remaining)
        if remaining[-1]==last and len(remaining)>1:
            remaining[0],remaining[-1]=remaining[-1],remaining[0]
    choice=remaining.pop()
    saved[key]={'last':choice,'remaining':remaining}
    store.set_preference('context_weather_phrases',saved)
    return pool[choice]
