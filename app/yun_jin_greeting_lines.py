# SPDX-License-Identifier: GPL-3.0-or-later
"""Short startup greetings, loaded on demand and rotated across app restarts."""
import random

LANGUAGES = ('it', 'en', 'zh-CN')
# Each row is Italian, English, Mandarin. No weather or activity is assumed.
LINES = {
    'morning': (
        ('Buongiorno! Ti auguro una bella giornata.', 'Good morning! I hope you have a lovely day.', '早上好！愿你今天心情愉快。'),
        ('Buongiorno! Da dove cominciamo?', 'Good morning! Where shall we begin?', '早上好！我们从哪里开始呢？'),
        ('Eccomi! Ti faccio compagnia questa mattina.', 'Here I am! I will keep you company this morning.', '我来啦！今天上午我陪着你。'),
        ('Buongiorno! C’è spazio anche per una piccola pausa.', 'Good morning! There is room for a little break too.', '早上好！也要留点时间休息哦。'),
        ('Una nuova giornata. Facciamo un passo alla volta.', 'A new day. Let us take it one step at a time.', '新的一天，我们一步一步来吧。'),
        ('Buongiorno! Il nostro piccolo sipario si apre.', 'Good morning! Our little curtain is rising.', '早上好！我们的小小幕布拉开了。'),
        ('Che piacere vederti questa mattina!', 'How lovely to see you this morning!', '今天早上见到你，真开心！'),
        ('Buongiorno! Spero che oggi ci sia qualcosa di bello per te.', 'Good morning! I hope today brings you something lovely.', '早上好！希望今天有好事等着你。'),
        ('Ti porto un saluto per cominciare la mattina.', 'A little greeting to start your morning.', '送上一声问候，陪你开始这个上午。'),
        ('Buongiorno! Hai già un’idea per oggi?', 'Good morning! Any plans for today?', '早上好！今天有什么打算吗？'),
        ('Cominciamo con calma. Buongiorno!', 'Let us start gently. Good morning!', '不着急，慢慢开始吧。早上好！'),
        ('Buongiorno! Io sono qui, quando vuoi.', 'Good morning! I am here whenever you need me.', '早上好！需要我的时候，我就在这里。'),
        ('Un saluto e un sorriso per la tua mattina.', 'A greeting and a smile for your morning.', '给你的上午送上一声问候和一个微笑。'),
        ('Buongiorno! Anche i piccoli progressi meritano un sorriso.', 'Good morning! Even small steps deserve a smile.', '早上好！小小的进步，也值得开心一下。'),
        ('Oggi cominciamo da qui. Buongiorno!', 'This is where we begin today. Good morning!', '今天就从这里开始吧。早上好！'),
        ('Buongiorno! Mi metto comoda qui accanto.', 'Good morning! I will settle in beside you.', '早上好！我就在旁边陪着你。'),
        ('Una mattina nuova, tante possibilità.', 'A new morning, full of possibilities.', '又是一个新的早晨，有好多可能呢。'),
        ('Buongiorno! Ti auguro di trovare il tuo ritmo.', 'Good morning! I hope you find a pace that suits you.', '早上好！愿你找到适合自己的节奏。'),
        ('Che la tua giornata inizi con una nota gentile.', 'May your day begin on a gentle note.', '愿你的一天，从温柔的音符开始。'),
        ('Buongiorno! Sono felice di iniziare la giornata con te.', 'Good morning! I am glad to start the day with you.', '早上好！能陪你开始这一天，我很高兴。'),
    ),
    'afternoon': (
        ('Buon pomeriggio! Sono felice di rivederti.', 'Good afternoon! It is lovely to see you again.', '下午好！很高兴又见到你。'),
        ('Eccomi! Come procede il pomeriggio?', 'Here I am! How is your afternoon going?', '我来啦！下午过得怎么样？'),
        ('Buon pomeriggio! Ti tengo compagnia volentieri.', 'Good afternoon! I am happy to keep you company.', '下午好！我很乐意陪着你。'),
        ('Un piccolo saluto per il tuo pomeriggio.', 'A little hello for your afternoon.', '送上一个小小的午后问候。'),
        ('Buon pomeriggio! Da cosa vuoi cominciare?', 'Good afternoon! What would you like to start with?', '下午好！你想先做什么呢？'),
        ('Ci ritroviamo qui. Buon pomeriggio!', 'Here we are again. Good afternoon!', '我们又在这里见面了。下午好！'),
        ('Buon pomeriggio! Spero che tu abbia un momento per te.', 'Good afternoon! I hope you have a moment for yourself.', '下午好！希望你能留一点时间给自己。'),
        ('C’è ancora un po’ di giornata da vivere insieme.', 'There is still some of the day left to share.', '今天还有一些时光，可以一起度过。'),
        ('Buon pomeriggio! Facciamo le cose al tuo ritmo.', 'Good afternoon! We will go at your pace.', '下午好！我们就按你的节奏来。'),
        ('Eccomi di nuovo in scena. Buon pomeriggio!', 'Back on our little stage. Good afternoon!', '我又登场啦。下午好！'),
        ('Buon pomeriggio! Che bello avere la tua compagnia.', 'Good afternoon! It is lovely to have your company.', '下午好！有你在，真好。'),
        ('Ti auguro un pomeriggio piacevole, anche nelle piccole cose.', 'I hope your afternoon is pleasant, even in the little things.', '愿你这个下午，在小事里也能找到快乐。'),
        ('Buon pomeriggio! C’è qualcosa che ti incuriosisce oggi?', 'Good afternoon! Has anything caught your curiosity today?', '下午好！今天有什么让你好奇的事吗？'),
        ('Mi fermo qui accanto a te. Buon pomeriggio!', 'I will stay here beside you. Good afternoon!', '我就在你旁边待着。下午好！'),
        ('Buon pomeriggio! Anche una breve pausa ha il suo valore.', 'Good afternoon! Even a short pause has its value.', '下午好！短短的休息，也很有意义。'),
        ('Un nuovo incontro a metà giornata. Che piacere!', 'A little meeting in the middle of the day. How lovely!', '午后又见到你，真让人开心！'),
        ('Buon pomeriggio! Il prossimo passo lo scegli tu.', 'Good afternoon! You choose the next step.', '下午好！接下来做什么，由你决定。'),
        ('Sono qui per accompagnare questo pomeriggio.', 'I am here to share this afternoon with you.', '这个下午，就让我陪着你吧。'),
        ('Buon pomeriggio! Spero ci sia spazio per qualcosa che ami.', 'Good afternoon! I hope there is time for something you love.', '下午好！希望你有时间做点喜欢的事。'),
        ('Un saluto leggero, come una nota tra due battute.', 'A gentle hello, like a note between two phrases.', '轻轻问声好，就像乐句之间的一个音符。'),
    ),
    'evening': (
        ('Buonasera! Com’è andata la giornata?', 'Good evening! How was your day?', '晚上好！今天过得怎么样？'),
        ('Buonasera! È bello ritrovarti.', 'Good evening! It is lovely to see you again.', '晚上好！又见到你，真好。'),
        ('Eccomi, pronta a farti compagnia questa sera.', 'Here I am, ready to keep you company this evening.', '我来啦，今晚也陪着你。'),
        ('Buonasera! Spero che tu possa concederti un po’ di calma.', 'Good evening! I hope you can enjoy a little calm.', '晚上好！希望你能享受一点轻松的时光。'),
        ('Un piccolo saluto per cominciare la serata.', 'A little greeting to begin the evening.', '用一声小小的问候，开始今晚吧。'),
        ('Buonasera! C’è qualcosa di bello che vuoi ricordare di oggi?', 'Good evening! Is there something lovely you want to remember from today?', '晚上好！今天有没有想记住的美好小事？'),
        ('La sera ha un ritmo tutto suo. Ti faccio compagnia.', 'Evening has a rhythm of its own. I will keep you company.', '夜晚有自己的节奏，我陪着你。'),
        ('Buonasera! Anche le giornate piene meritano una pausa.', 'Good evening! Even busy days deserve a pause.', '晚上好！再忙的一天，也值得歇一歇。'),
        ('Ci ritroviamo a sera. Sono contenta!', 'We meet again this evening. I am glad!', '到了晚上又见面了，我很开心！'),
        ('Buonasera! Per questa sera, che cosa ti va di fare?', 'Good evening! What would you like to do tonight?', '晚上好！今晚你想做些什么呢？'),
        ('Mi accomodo qui vicino. Buonasera!', 'I will settle in nearby. Good evening!', '我就在旁边待着。晚上好！'),
        ('Buonasera! Un saluto senza fretta, tutto per te.', 'Good evening! An unhurried hello, just for you.', '晚上好！不急不忙地，向你问声好。'),
        ('La nostra piccola scena si riapre. Buonasera!', 'Our little stage opens again. Good evening!', '我们的小小舞台又开场了。晚上好！'),
        ('Buonasera! Spero ci sia una nota felice nella tua giornata.', 'Good evening! I hope there was a happy note in your day.', '晚上好！希望你今天有过开心的时刻。'),
        ('È sera, e io sono qui accanto a te.', 'It is evening, and I am here beside you.', '夜晚到了，我就在你身边。'),
        ('Buonasera! Possiamo procedere con calma.', 'Good evening! We can take things gently.', '晚上好！我们可以慢慢来。'),
        ('Ti auguro una serata piacevole, qualunque sia il programma.', 'I hope you have a pleasant evening, whatever your plans.', '不管今晚有什么安排，都祝你过得愉快。'),
        ('Buonasera! Che piacere condividere ancora un po’ di tempo.', 'Good evening! It is lovely to share a little more time.', '晚上好！还能一起待一会儿，真好。'),
        ('Un cenno e un sorriso per la tua serata.', 'A little wave and a smile for your evening.', '轻轻招手，再送你一个晚间的微笑。'),
        ('Buonasera! Il sipario può aprirsi anche su un momento tranquillo.', 'Good evening! The curtain can rise on a quiet moment too.', '晚上好！帷幕拉开，也可以是一个安静的时刻。'),
    ),
    'night': (
        ('È tardi. Ricordati di riposare un po’.', 'It is getting late. Remember to get some rest.', '夜深了，别忘了休息一会儿。'),
        ('Ciao! Ti faccio compagnia, piano piano.', 'Hello! I will keep you quiet company.', '你好呀！我轻轻地陪着你。'),
        ('Eccomi. Anche a quest’ora, un saluto ci sta.', 'Here I am. Even at this hour, a hello is welcome.', '我来啦。这个时候，也想向你问声好。'),
        ('È notte. Facciamo le cose senza fretta.', 'It is night. Let us take things without rushing.', '已经是夜里了，我们不着急，慢慢来。'),
        ('Un saluto sottovoce, per non rompere la quiete.', 'A quiet hello, so as not to break the calm.', '轻轻问声好，不打扰这份安静。'),
        ('Ci ritroviamo anche di notte. Spero tu stia bene.', 'We meet at night too. I hope you are doing well.', '夜里也见面了，希望你一切都好。'),
        ('Sono qui. Quando senti sonno, concediti una pausa.', 'I am here. When you feel sleepy, give yourself a break.', '我在这里。困了的话，就歇一歇吧。'),
        ('Il nostro piccolo teatro abbassa la voce.', 'Our little theatre lowers its voice.', '我们的小剧场，也放轻了声音。'),
        ('Ciao! Ti auguro qualche momento sereno.', 'Hello! I wish you a few peaceful moments.', '你好呀！愿你有一段安心的时光。'),
        ('È notte, ma un sorriso non disturba.', 'It is night, but a smile will not disturb anyone.', '夜深了，不过一个微笑不会打扰谁。'),
        ('Eccomi accanto a te. Non dimenticare il riposo.', 'Here I am beside you. Do not forget to rest.', '我来到你身边啦。也别忘了休息。'),
        ('Un saluto gentile a quest’ora silenziosa.', 'A gentle hello at this quiet hour.', '在这安静的时刻，轻轻向你问好。'),
        ('È un’ora tranquilla per incontrarsi.', 'It is a quiet hour for a little meeting.', '在这样安静的时刻相遇，真好。'),
        ('Ciao! Anche le cose importanti possono avere una pausa.', 'Hello! Even important things can pause for a moment.', '你好呀！再重要的事，也可以稍稍停一会儿。'),
        ('Ti tengo compagnia per un po’. Ascolta anche la tua stanchezza.', 'I will keep you company for a while. Remember to rest when you feel tired.', '我陪你一会儿。累了也要照顾好自己。'),
        ('Un piccolo saluto, e ti auguro una notte serena.', 'A little hello, and a wish for a peaceful night.', '轻轻问声好，愿你今夜安好。'),
        ('Eccomi. Questa notte procediamo al tuo ritmo.', 'Here I am. Tonight we will go at your pace.', '我来啦。今晚就按你的节奏来吧。'),
        ('La notte invita a rallentare un poco.', 'The night invites us to slow down a little.', '到了夜里，也可以把节奏放慢一点。'),
        ('Ciao! Spero che il riposo ti aspetti presto.', 'Hello! I hope some rest is waiting for you soon.', '你好呀！希望你一会儿就能好好休息。'),
        ('Ti saluto con una nota leggera. Sono qui.', 'A soft note to say hello. I am here.', '用一个轻柔的音符问候你。我在这里。'),
    ),
}


def line_pool(period, language):
    index = LANGUAGES.index(language) if language in LANGUAGES else 0
    return tuple(row[index] for row in LINES[period])


def choose_greeting_line(store, period, language, rng=None):
    """Use each phrase once per bag, with bounded state persisted across restarts."""
    language = language if language in LANGUAGES else 'it'
    pool = line_pool(period, language)
    saved = store.preference('context_greeting_phrases', {})
    state = {}
    if isinstance(saved, dict):
        for lang in LANGUAGES:
            for name, rows in LINES.items():
                key = lang + '/' + name
                value = saved.get(key)
                if not isinstance(value, dict):
                    continue
                last, remaining = value.get('last'), value.get('remaining')
                if (type(last) is int and 0 <= last < len(rows)
                        and isinstance(remaining, list) and len(remaining) < len(rows)
                        and all(type(i) is int and 0 <= i < len(rows) for i in remaining)
                        and last not in remaining and len(set(remaining)) == len(remaining)):
                    state[key] = {'last': last, 'remaining': list(remaining)}
    key = language + '/' + period
    previous = state.get(key, {})
    remaining = previous.get('remaining', [])
    if not remaining:
        remaining = list(range(len(pool)))
        (rng or random).shuffle(remaining)
        if remaining[-1] == previous.get('last'):
            remaining[0], remaining[-1] = remaining[-1], remaining[0]
    choice = remaining.pop()
    state[key] = {'last': choice, 'remaining': remaining}
    store.set_preference('context_greeting_phrases', state)
    return pool[choice]
