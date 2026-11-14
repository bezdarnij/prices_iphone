import os, re, io, sys, asyncio, sqlite3, threading, requests
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from bs4 import BeautifulSoup

TOKEN = os.environ["BOT_TOKEN"]
CH = os.environ.get("CHANNEL", "new_store77").replace("@", "")
OWNER = int(os.environ.get("OWNER_ID", "0"))
DB = os.environ.get("DB_PATH", "prices.db")
KEY = os.environ.get("KEY", "17 pro max").lower()
EVERY = int(os.environ.get("EVERY", "600"))
PAGES = int(os.environ.get("PAGES", "10"))
LO = int(os.environ.get("MIN_PRICE", "1000"))
HI = int(os.environ.get("MAX_PRICE", "10000000"))
BASE = "https://t.me/s/" + CH
EMB = "https://t.me/" + CH + "/%d?embed=1&mode=tme"
API = "https://api.telegram.org/bot" + TOKEN + "/"
NUM = re.compile(r"\d[\d\s.,]{2,}\d")
LN = re.compile(r"^\s*(\S+)\s+(.+?)\s*\(([^)]*)\)\s*[—–-]\s*(.+)$")
HELP = "/now [фильтр] - актуальный прайс, от дешёвых к дорогим, с изменением\n/last [фильтр] - последние 10 изменений\n/stats фильтр - мин/макс/текущая\n/chart фильтр - график\n\nФильтр - слова через пробел: 256, 512, 1tb, 2tb, silver, deep blue, cosmic orange, esim, 1sim.\nНапример: /chart 256 silver esim"


def db():
    c = sqlite3.connect(DB)
    c.execute("create table if not exists ph(mid integer, ts text, v text, p integer, primary key(mid, ts, v))")
    c.execute("create table if not exists meta(k text primary key, v text)")
    return c


def meta_get(k, d):
    c = db()
    r = c.execute("select v from meta where k=?", (k,)).fetchone()
    c.close()
    if r is None:
        return d
    return r[0]


def meta_set(k, v):
    c = db()
    c.execute("insert or replace into meta values(?,?)", (k, v))
    c.commit()
    c.close()


def now_ts():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse(text):
    out = []
    ls = text.split("\n")
    for i in range(len(ls)):
        l = ls[i]
        low = l.lower()
        if KEY not in low:
            continue
        m = LN.match(l[low.index(KEY) + len(KEY):])
        if not m:
            continue
        ns = NUM.findall(m.group(4))
        if not ns:
            continue
        p = int(re.sub(r"\D", "", ns[-1]))
        if p < LO or p > HI:
            continue
        mem = m.group(1).lower()
        if mem[-1] in "тt":
            mem = mem[:-1] + "tb"
        sim = "esim" if m.group(3).strip().lower() == "esim" else "1sim"
        out.append((mem + " " + m.group(2).strip().lower() + " " + sim, p))
    return out


def grab(u, mid=None):
    r = requests.get(u, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    s = BeautifulSoup(r.text, "html.parser")
    ms = s.select("div.tgme_widget_message")
    res = []
    for i in range(len(ms)):
        m = ms[i]
        t = m.select_one("div.tgme_widget_message_text")
        if not t:
            continue
        post = m.get("data-post")
        if post:
            k = int(post.split("/")[1])
        elif mid:
            k = mid
        else:
            continue
        brs = t.select("br")
        for j in range(len(brs)):
            brs[j].replace_with("\n")
        res.append((k, t.get_text()))
    return res


def save(rows):
    c = db()
    t = now_ts()
    ch = []
    for i in range(len(rows)):
        mid, txt = rows[i]
        ps = parse(txt)
        for j in range(len(ps)):
            v, p = ps[j]
            r = c.execute("select p from ph where mid=? and v=? order by ts desc limit 1", (mid, v)).fetchone()
            if r is None or r[0] != p:
                cur = c.execute("insert or ignore into ph values(?,?,?,?)", (mid, t, v, p))
                if cur.rowcount > 0:
                    old = None
                    if r is not None:
                        old = r[0]
                    ch.append((v, old, p))
    c.commit()
    c.close()
    return ch


def tracked():
    c = db()
    r = c.execute("select distinct mid from ph").fetchall()
    c.close()
    out = []
    for i in range(len(r)):
        out.append(r[i][0])
    return out


def check():
    tr = tracked()
    rows = grab(BASE)
    if not tr:
        for k in range(PAGES):
            best = None
            for i in range(len(rows)):
                if parse(rows[i][1]) and (best is None or rows[i][0] > best[0]):
                    best = rows[i]
            if best:
                return save([best])
            if not rows:
                return []
            old = rows[0][0]
            for i in range(len(rows)):
                if rows[i][0] < old:
                    old = rows[i][0]
            rows = grab(BASE + "?before=" + str(old))
        return []
    d = {}
    for i in range(len(rows)):
        d[rows[i][0]] = rows[i][1]
    top = max(tr)
    out = []
    for k in d:
        if k > top:
            out.append((k, d[k]))
    for i in range(len(tr)):
        m = tr[i]
        if m in d:
            out.append((m, d[m]))
        else:
            try:
                got = grab(EMB % m, m)
            except Exception:
                got = []
            for j in range(len(got)):
                out.append(got[j])
    return save(out)


def allp():
    c = db()
    r = c.execute("select ts, v, p from ph order by ts").fetchall()
    c.close()
    return r


def get(args):
    r = allp()
    ks = []
    for i in range(len(args)):
        ks.append(args[i].lower())
    out = []
    for i in range(len(r)):
        good = True
        for j in range(len(ks)):
            if ks[j] not in r[i][1]:
                good = False
        if good:
            out.append(r[i])
    return out


def fmt(x):
    return "{:,}".format(x).replace(",", " ")


def dt(ts):
    return ts[:16].replace("T", " ")


def sg(d):
    if d > 0:
        return "+" + fmt(d)
    return fmt(d)


def note(ch):
    t = ""
    new = 0
    for i in range(len(ch)):
        v, o, n = ch[i]
        if o is None:
            new += 1
        else:
            t += v + ": " + fmt(o) + " → " + fmt(n) + " (" + sg(n - o) + ")\n"
    if new:
        t += "Новых позиций: " + str(new)
    return t.strip()


def c_now(args):
    r = get(args)
    if not r:
        return "Данных нет"
    cur = {}
    prev = {}
    for i in range(len(r)):
        v = r[i][1]
        if v in cur:
            prev[v] = cur[v]
        cur[v] = r[i][2]
    ks = list(cur.keys())
    ks.sort(key=lambda k: cur[k])
    t = ""
    for i in range(len(ks)):
        k = ks[i]
        t += k + ": " + fmt(cur[k])
        if k in prev:
            t += " (" + sg(cur[k] - prev[k]) + ")"
        t += "\n"
    return t


def c_last(args):
    r = get(args)[-10:]
    if not r:
        return "Данных нет"
    t = ""
    for i in range(len(r)):
        t += dt(r[i][0]) + "  " + r[i][1] + "  " + fmt(r[i][2]) + "\n"
    return t


def c_stats(args):
    if not args:
        return "Нужен фильтр, например: /stats 256 silver esim"
    r = get(args)
    if not r:
        return "Данных нет"
    a = 0
    b = 0
    for i in range(len(r)):
        if r[i][2] < r[a][2]:
            a = i
        if r[i][2] > r[b][2]:
            b = i
    t = "Изменений цены: " + str(len(r)) + "\n"
    t += "Сейчас: " + fmt(r[-1][2]) + " (" + dt(r[-1][0]) + ")\n"
    t += "Мин: " + fmt(r[a][2]) + " (" + dt(r[a][0]) + ")\n"
    t += "Макс: " + fmt(r[b][2]) + " (" + dt(r[b][0]) + ")"
    return t


def c_chart(args):
    if not args:
        return "Нужен фильтр, например: /chart 256 silver esim"
    r = get(args)
    if len(r) < 2:
        return "Мало данных"
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    xs = []
    ys = []
    for i in range(len(r)):
        xs.append(datetime.fromisoformat(r[i][0]))
        ys.append(r[i][2])
    plt.figure(figsize=(8, 4))
    plt.step(xs, ys, where="post", marker="o")
    plt.grid(True)
    plt.title(" ".join(args))
    plt.gcf().autofmt_xdate()
    b = io.BytesIO()
    plt.savefig(b, format="png", dpi=100)
    plt.close()
    return b.getvalue()


def run_cmd(cmd, args):
    if cmd == "/now":
        return c_now(args)
    if cmd == "/last":
        return c_last(args)
    if cmd == "/stats":
        return c_stats(args)
    if cmd == "/chart":
        return c_chart(args)
    return HELP


def api(m, **kw):
    return requests.post(API + m, data=kw, timeout=30).json()


def send(chat, out):
    if isinstance(out, bytes):
        requests.post(API + "sendPhoto", data={"chat_id": chat}, files={"photo": ("c.png", out)}, timeout=60)
    else:
        api("sendMessage", chat_id=chat, text=out)


def once():
    try:
        ch = check()
    except Exception as e:
        print("check failed:", type(e).__name__)
        ch = []
    t = note(ch)
    if t and OWNER:
        send(OWNER, t)
    off = int(meta_get("off", "0"))
    ups = api("getUpdates", offset=off, timeout=0).get("result", [])
    for i in range(len(ups)):
        up = ups[i]
        off = up["update_id"] + 1
        m = up.get("message")
        if not m or "text" not in m:
            continue
        if OWNER and m["from"]["id"] != OWNER:
            continue
        parts = m["text"].split()
        if not parts:
            continue
        send(m["chat"]["id"], run_cmd(parts[0].split("@")[0].lower(), parts[1:]))
    meta_set("off", str(off))
    print("changes:", len(ch), "updates:", len(ups))


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


def srv():
    HTTPServer(("0.0.0.0", int(os.environ["PORT"])), H).serve_forever()


def run_bot():
    from telegram.ext import Application, MessageHandler, filters

    async def hnd(u, ctx):
        if OWNER and u.effective_user.id != OWNER:
            return
        parts = u.message.text.split()
        out = await asyncio.to_thread(run_cmd, parts[0].split("@")[0].lower(), parts[1:])
        if isinstance(out, bytes):
            await u.message.reply_photo(io.BytesIO(out))
        else:
            await u.message.reply_text(out)

    async def imp(u, ctx):
        if OWNER and u.effective_user.id != OWNER:
            return
        d = u.message.document
        if not d.file_name.endswith(".db"):
            return
        f = await d.get_file()
        await f.download_to_drive(DB)
        await u.message.reply_text("База загружена")

    async def poll(ctx):
        try:
            ch = await asyncio.to_thread(check)
        except Exception:
            return
        if ch and OWNER:
            await ctx.bot.send_message(OWNER, note(ch))
            with open(DB, "rb") as f:
                await ctx.bot.send_document(OWNER, f, filename="prices.db", disable_notification=True)

    db().close()
    if os.environ.get("PORT"):
        threading.Thread(target=srv, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.COMMAND, hnd))
    app.add_handler(MessageHandler(filters.Document.ALL, imp))
    app.job_queue.run_repeating(poll, interval=EVERY, first=5)
    app.run_polling()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        once()
    else:
        run_bot()
