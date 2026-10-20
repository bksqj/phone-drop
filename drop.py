#!/usr/bin/env python3
"""phone-drop: передача файлов iPhone <-> ноутбук по Wi-Fi без интернета.
Запуск: python3 drop.py   -> открыть на телефоне в Safari адрес, который покажет программа."""
import itertools, json, mimetypes, os, shutil, socket, subprocess, sys, threading, time, urllib.parse, webbrowser
import qr
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

PORT = 8000
WINDOWS = os.name == 'nt'
if WINDOWS:
    os.system('')                                          # включает цвета/юникод в старой консоли Windows
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def downloads_dir():
    """папка «Загрузки» в любой локали (Загрузки / Downloads); на Windows - просто Downloads"""
    if WINDOWS:
        return os.path.join(os.path.expanduser('~'), 'Downloads')
    try:
        d = subprocess.run(['xdg-user-dir', 'DOWNLOAD'], capture_output=True, text=True).stdout.strip()
        if d and os.path.isdir(d):
            return d
    except OSError:
        pass
    return os.path.join(os.path.expanduser('~'), 'Downloads')


DL = downloads_dir()
INBOX = os.path.join(DL, 'С телефона')                      # сюда падает то, что прислал телефон
OUTBOX = os.path.join(DL, 'На телефон')                     # отсюда телефон может скачать
TEXTS = os.path.join(INBOX, 'тексты.txt')                  # все присланные тексты подряд
os.makedirs(INBOX, exist_ok=True)
os.makedirs(OUTBOX, exist_ok=True)
PC_TEXTS = []                                              # тексты с ноутбука для телефона (последние 20)
TEXT_IDS = itertools.count(1)
IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.gif', '.heic', '.webp')

PAGE = r'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Phone Drop</title><style>
:root{--bg:#0f1115;--card:#1a1d24;--fg:#eef0f4;--mut:#8b93a3;--acc:#4f8cff;--ok:#3ecf8e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px -apple-system,system-ui,sans-serif;padding:16px}
h1{font-size:22px;margin:4px 0 16px}h2{font-size:15px;color:var(--mut);margin:24px 0 8px;font-weight:600}
.drop{display:block;background:var(--card);border:2px dashed #333a47;border-radius:16px;padding:36px 16px;text-align:center;cursor:pointer}
.drop b{display:block;font-size:18px;margin-bottom:6px}.drop span{color:var(--mut);font-size:14px}
input{display:none}.row{background:var(--card);border-radius:12px;padding:12px;margin:8px 0;font-size:14px;word-break:break-all}
.bar{height:6px;background:#2a2f3a;border-radius:3px;margin-top:8px;overflow:hidden}.bar i{display:block;height:100%;width:0;background:var(--acc);transition:width .1s}
.done i{background:var(--ok)}
textarea{width:100%;min-height:110px;background:var(--card);color:var(--fg);border:1px solid #333a47;border-radius:12px;padding:12px;font:16px -apple-system,system-ui,sans-serif;resize:vertical}
button{width:100%;margin-top:8px;padding:14px;border:0;border-radius:12px;background:var(--acc);color:#fff;font:600 16px -apple-system,system-ui,sans-serif}
button:disabled{opacity:.5}#ts{font-size:14px;margin-top:8px;min-height:18px}a{color:var(--acc);text-decoration:none}.mut{color:var(--mut)}
.new{border:1px solid var(--ok)}.tag{color:var(--ok);font-size:12px;font-weight:600;margin-left:6px}
.pctext{white-space:pre-wrap;word-break:break-word;margin:6px 0}.small{width:auto;padding:8px 14px;margin:0;font-size:14px}
</style></head><body>
<h1>📲 Phone Drop</h1>
<label class="drop"><input id="f" type="file" multiple><b>Выбрать файлы</b><span>фото, видео, документы — уйдут на ноутбук</span></label>
<div id="q"></div>
<h2>Текст на ноутбук</h2>
<textarea id="t" placeholder="Вставь или напиши текст — ссылку, заметку, пароль от Wi-Fi…"></textarea>
<button id="tb">Отправить текст</button><div id="ts" class="mut"></div>
<h2>Текст с ноутбука</h2><div id="pt"><div class="mut">пока ничего</div></div>
<h2>Файлы с ноутбука</h2><div id="out"><div class="mut">загрузка…</div></div>
<script>
const q=document.getElementById('q');
function fmt(n){return n>1e9?(n/1e9).toFixed(1)+' ГБ':n>1e6?(n/1e6).toFixed(1)+' МБ':(n/1e3).toFixed(0)+' КБ'}
async function send(file){
  const row=document.createElement('div');row.className='row';
  row.innerHTML=`<div>${file.name.replace(/</g,'&lt;')} <span class="mut">${fmt(file.size)}</span></div><div class="bar"><i></i></div>`;
  q.prepend(row);const bar=row.querySelector('i');
  await new Promise(res=>{const x=new XMLHttpRequest();x.open('POST','/upload');
    x.setRequestHeader('X-Filename',encodeURIComponent(file.name));
    x.upload.onprogress=e=>{if(e.lengthComputable)bar.style.width=(e.loaded/e.total*100)+'%'};
    x.onload=()=>{bar.style.width='100%';row.classList.add('done');if(x.status!=200)row.querySelector('.mut').textContent=' ошибка '+x.status;res()};
    x.onerror=()=>{row.querySelector('.mut').textContent=' ошибка сети';res()};x.send(file)});
}
const t=document.getElementById('t'),tb=document.getElementById('tb'),ts=document.getElementById('ts');
tb.onclick=async()=>{if(!t.value.trim()){ts.textContent='поле пустое';return}
  tb.disabled=true;ts.textContent='отправляю…';
  try{const r=await fetch('/text',{method:'POST',headers:{'Content-Type':'text/plain;charset=utf-8'},body:t.value});
    if(!r.ok)throw 0;ts.style.color='var(--ok)';ts.textContent='✓ отправлено ('+new Date().toLocaleTimeString()+')';t.value=''}
  catch(e){ts.style.color='#ff6b6b';ts.textContent='ошибка — ноутбук не отвечает'}
  tb.disabled=false;setTimeout(()=>{ts.style.color='';},3000)};
document.getElementById('f').onchange=async e=>{for(const f of e.target.files)await send(f);e.target.value=''};
const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;');
let seen=null,last='';                        // seen - что уже было при первой загрузке, новое подсвечиваем
function copy(btn,text){                      // navigator.clipboard по http не работает - старый способ
  const a=document.createElement('textarea');a.value=text;a.style.position='fixed';a.style.opacity='0';
  document.body.append(a);a.select();a.setSelectionRange(0,text.length);
  const ok=document.execCommand('copy');a.remove();btn.textContent=ok?'✓ скопировано':'выдели и скопируй вручную'}
async function poll(){
  try{const d=await (await fetch('/list')).json();const key=JSON.stringify(d);
    if(key!==last){last=key;
      if(!seen)seen=new Set([...d.files.map(f=>'f'+f.name),...d.texts.map(t=>'t'+t.id)]);
      const o=document.getElementById('out');
      o.innerHTML=d.files.length?'':'<div class="mut">пусто — перетащи файлы в окно Phone Drop на ноутбуке</div>';
      for(const f of d.files){const el=document.createElement('div');const n=!seen.has('f'+f.name);
        el.className='row'+(n?' new':'');const u=encodeURIComponent(f.name);
        el.innerHTML=`<a href="/get/${u}" download>${esc(f.name)}</a> <span class="mut">${fmt(f.size)}</span>${n?'<span class="tag">новое</span>':''}`+
          (f.image?`<div class="mut" style="margin-top:6px"><a href="/view/${u}" target="_blank">открыть</a> → удержи палец на фото → «Сохранить в Фото»</div>`:'');
        o.append(el)}
      const p=document.getElementById('pt');p.innerHTML=d.texts.length?'':'<div class="mut">пока ничего</div>';
      for(const t of d.texts){const el=document.createElement('div');const n=!seen.has('t'+t.id);
        el.className='row'+(n?' new':'');
        el.innerHTML=`<div class="mut">${t.time}${n?'<span class="tag">новое</span>':''}</div><div class="pctext">${esc(t.text)}</div><button class="small">Скопировать</button>`;
        el.querySelector('button').onclick=e=>copy(e.target,t.text);p.append(el)}}}
  catch(e){}
  setTimeout(poll,2000)}
poll();
</script></body></html>'''

PC_PAGE = r'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Phone Drop — отправка на телефон</title><style>
:root{--bg:#0f1115;--card:#1a1d24;--fg:#eef0f4;--mut:#8b93a3;--acc:#4f8cff;--ok:#3ecf8e}
*{box-sizing:border-box}body{margin:0 auto;max-width:640px;background:var(--bg);color:var(--fg);font:16px system-ui,sans-serif;padding:24px 16px}
h1{font-size:22px}h2{font-size:15px;color:var(--mut);margin:28px 0 8px}.mut{color:var(--mut)}
#z{display:block;background:var(--card);border:2px dashed #333a47;border-radius:16px;padding:48px 16px;text-align:center;cursor:pointer}
#z.over{border-color:var(--acc)}#z b{display:block;font-size:18px;margin-bottom:6px}input{display:none}
.row{background:var(--card);border-radius:12px;padding:10px 12px;margin:6px 0;font-size:14px;display:flex;justify-content:space-between;gap:8px;word-break:break-all}
textarea{width:100%;min-height:90px;background:var(--card);color:var(--fg);border:1px solid #333a47;border-radius:12px;padding:12px;font:15px system-ui,sans-serif}
button{padding:12px 18px;border:0;border-radius:12px;background:var(--acc);color:#fff;font:600 15px system-ui,sans-serif;cursor:pointer;margin-top:8px}
.x{background:none;color:var(--mut);padding:0;margin:0;font-size:14px}#ts{margin-left:10px;font-size:14px}
</style></head><body>
<h1>📲 Phone Drop: отправка на телефон</h1>
<label id="z"><input id="f" type="file" multiple><b>Перетащи файлы сюда</b><span class="mut">или нажми, чтобы выбрать: они сразу появятся на странице телефона</span></label>
<h2>Текст на телефон</h2>
<textarea id="t" placeholder="Ссылка, заметка, пароль…  (Ctrl+Enter, чтобы отправить)"></textarea>
<button id="tb">Отправить текст</button><span id="ts" class="mut"></span>
<h2>Сейчас лежит для телефона</h2><div id="l"></div>
<script>
const fmt=n=>n>1e9?(n/1e9).toFixed(1)+' ГБ':n>1e6?(n/1e6).toFixed(1)+' МБ':(n/1e3).toFixed(0)+' КБ';
const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;');
async function list(){const d=await (await fetch('/list')).json();const l=document.getElementById('l');
  l.innerHTML=d.files.length?'':'<div class="mut">пусто</div>';
  for(const f of d.files){const r=document.createElement('div');r.className='row';
    r.innerHTML=`<span>${esc(f.name)} <span class="mut">${fmt(f.size)}</span></span><button class="x">убрать</button>`;
    r.querySelector('button').onclick=async()=>{await fetch('/pc/delete',{method:'POST',headers:{'X-Filename':encodeURIComponent(f.name)}});list()};
    l.append(r)}}
async function up(files){for(const f of files){
  await fetch('/pc/upload',{method:'POST',headers:{'X-Filename':encodeURIComponent(f.name)},body:f});list()}}
const z=document.getElementById('z');
z.ondragover=e=>{e.preventDefault();z.classList.add('over')};z.ondragleave=()=>z.classList.remove('over');
z.ondrop=e=>{e.preventDefault();z.classList.remove('over');up(e.dataTransfer.files)};
document.getElementById('f').onchange=e=>{up(e.target.files);e.target.value=''};
const t=document.getElementById('t'),ts=document.getElementById('ts');
async function sendText(){if(!t.value.trim())return;
  const r=await fetch('/pc/text',{method:'POST',headers:{'Content-Type':'text/plain;charset=utf-8'},body:t.value});
  ts.textContent=r.ok?'✓ отправлено, смотри на телефоне':'ошибка';if(r.ok)t.value=''}
document.getElementById('tb').onclick=sendText;
t.onkeydown=e=>{if(e.key==='Enter'&&e.ctrlKey)sendText()};
list();setInterval(list,3000);
</script></body></html>'''


def unique(path):
    """file.jpg -> file (1).jpg, если такой уже есть"""
    base, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(path):
        path = f'{base} ({n}){ext}'
        n += 1
    return path


class H(BaseHTTPRequestHandler):
    def send(self, code, body, ctype='text/html; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def local(self):
        """страница отправки и её команды - только с самого ноутбука, не из сети"""
        return self.client_address[0] in ('127.0.0.1', '::1', '::ffff:127.0.0.1')

    def do_GET(self):
        path = urllib.parse.unquote(self.path)
        if path == '/':
            return self.send(200, PAGE.encode())
        if path == '/pc':
            return self.send(200, PC_PAGE.encode()) if self.local() else self.send(403, b'forbidden')
        if path == '/list':
            files = [{'name': f, 'size': os.path.getsize(os.path.join(OUTBOX, f)),
                      'image': f.lower().endswith(IMAGE_EXT)}
                     for f in sorted(os.listdir(OUTBOX), key=lambda f: -os.path.getmtime(os.path.join(OUTBOX, f)))
                     if os.path.isfile(os.path.join(OUTBOX, f)) and not f.endswith('.part')]
            body = {'files': files, 'texts': PC_TEXTS[::-1]}
            return self.send(200, json.dumps(body).encode(), 'application/json')
        if path.startswith(('/get/', '/view/')):
            inline = path.startswith('/view/')
            name = os.path.basename(path.split('/', 2)[2])       # basename - нельзя выйти из папки
            full = os.path.join(OUTBOX, name)
            if not os.path.isfile(full):
                return self.send(404, b'not found')
            ctype = (mimetypes.guess_type(name)[0] or 'application/octet-stream') if inline else 'application/octet-stream'
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(os.path.getsize(full)))
            self.send_header('Content-Disposition', ('inline' if inline else 'attachment') +
                             "; filename*=UTF-8''" + urllib.parse.quote(name))
            self.end_headers()
            with open(full, 'rb') as f:
                shutil.copyfileobj(f, self.wfile)
            print(f'  -> отдал на телефон: {name}')
            return
        self.send(404, b'not found')

    def receive(self, folder):
        """принимает файл из тела запроса в folder, возвращает итоговый путь или None"""
        name = os.path.basename(urllib.parse.unquote(self.headers.get('X-Filename', 'file'))) or 'file'
        left = int(self.headers.get('Content-Length', 0))
        dest = unique(os.path.join(folder, name))
        tmp = dest + '.part'
        with open(tmp, 'wb') as f:                               # пишем кусками - большие видео не забьют память
            while left > 0:
                chunk = self.rfile.read(min(left, 1 << 20))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left > 0:
            os.remove(tmp)
            self.send(400, b'incomplete')
            return None
        os.rename(tmp, dest)
        self.send(200, b'ok')
        return dest

    def pc_post(self):
        if not self.local():
            return self.send(403, b'forbidden')
        if self.path == '/pc/upload':
            dest = self.receive(OUTBOX)
            if dest:
                print(f'  -> выложил для телефона: {os.path.basename(dest)}')
            return
        if self.path == '/pc/text':
            n = int(self.headers.get('Content-Length', 0))
            if n > 1 << 20:
                return self.send(413, b'too big')
            text = self.rfile.read(n).decode('utf-8', 'replace')
            PC_TEXTS.append({'id': next(TEXT_IDS), 'time': time.strftime('%H:%M'), 'text': text})
            del PC_TEXTS[:-20]
            print('  -> текст для телефона отправлен')
            return self.send(200, b'ok')
        if self.path == '/pc/delete':
            name = os.path.basename(urllib.parse.unquote(self.headers.get('X-Filename', '')))
            full = os.path.join(OUTBOX, name)
            if name and os.path.isfile(full):
                os.remove(full)
            return self.send(200, b'ok')
        self.send(404, b'not found')

    def save_text(self):
        n = int(self.headers.get('Content-Length', 0))
        if n > 1 << 20:
            return self.send(413, b'too big')
        text = self.rfile.read(n).decode('utf-8', 'replace')
        stamp = time.strftime('%d.%m.%Y %H:%M:%S')
        with open(TEXTS, 'a', encoding='utf-8') as f:
            f.write(f'===== {stamp} =====\n{text}\n\n')
        copied = copy_to_clipboard(text)
        print(f'\n  <- текст ({stamp}){" - скопирован в буфер, жми Ctrl+V" if copied else ""}:')
        print('  ' + '-' * 46)
        for line in text.splitlines() or ['']:
            print('  ' + line)
        print('  ' + '-' * 46)
        self.send(200, b'ok')

    def do_POST(self):
        if self.path.startswith('/pc/'):
            return self.pc_post()
        if self.path == '/text':
            return self.save_text()
        if self.path != '/upload':
            return self.send(404, b'not found')
        dest = self.receive(INBOX)
        if dest:
            print(f'  <- получил: {os.path.basename(dest)} ({os.path.getsize(dest) // 1024} КБ)')

    def log_message(self, *a):
        pass                                                     # не засоряем консоль логами запросов


def copy_to_clipboard(text):
    """кладём текст в буфер обмена ноутбука: на Windows - через WinAPI, на Linux - если стоит xclip"""
    if WINDOWS:
        return win_clipboard(text)
    if not shutil.which('xclip'):
        return False
    try:
        subprocess.run(['xclip', '-selection', 'clipboard'], input=text.encode(), timeout=3)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def win_clipboard(text):
    """буфер обмена Windows без сторонних программ (clip.exe портит кириллицу)"""
    import ctypes
    from ctypes import wintypes
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
    k32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
    u32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
    data = text.encode('utf-16-le') + b'\0\0'
    if not u32.OpenClipboard(None):
        return False
    try:
        u32.EmptyClipboard()
        h = k32.GlobalAlloc(0x0002, len(data))                     # GMEM_MOVEABLE
        ctypes.memmove(k32.GlobalLock(h), data, len(data))
        k32.GlobalUnlock(h)
        return bool(u32.SetClipboardData(13, h))                   # CF_UNICODETEXT
    finally:
        u32.CloseClipboard()


def local_ips():
    if WINDOWS:                                                  # hostname -I на Windows нет
        try:
            out = [a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
        except OSError:
            out = []
    else:
        out = subprocess.run(['hostname', '-I'], capture_output=True, text=True).stdout.split()
    return list(dict.fromkeys(ip for ip in out if '.' in ip and not ip.startswith(('0.', '127.', '10.8.', '100.', '169.254.'))))


def show(ip):
    url = f'http://{ip}:{PORT}'
    print(f'\n  Наведи камеру iPhone на QR или открой в Safari:  {url}')
    print(qr.terminal(url))


def watch_network(known):
    """каждые 2 секунды проверяем адреса: подключил кабель - сразу показываем новый QR"""
    while True:
        time.sleep(2)
        for ip in local_ips():
            if ip not in known:
                known.add(ip)
                print('\n  >>> появилась новая сеть')
                show(ip)


if __name__ == '__main__':
    try:
        srv = ThreadingHTTPServer(('0.0.0.0', PORT), H)
    except OSError as e:
        sys.exit(f'Порт {PORT} занят ({e}). Закрой другую копию программы.')
    print('=' * 50)
    print('  PHONE DROP запущен')
    print(f'  Файлы с телефона  -> {INBOX}')
    print(f'  Файлы на телефон  <- {OUTBOX}')
    print(f'  Тексты с телефона -> {TEXTS}')
    print(f'  Отправить на телефон: http://127.0.0.1:{PORT}/pc  (откроется само)')
    print('  Остановить: Ctrl+C')
    print('=' * 50)
    ips = local_ips()
    for ip in sorted(ips, key=lambda a: not a.startswith('172.20.10.')):   # кабель/модем айфона - первым
        show(ip)
    if not ips:
        print('\n  Сети пока нет - подключи iPhone кабелем, QR появится сам')
    threading.Thread(target=watch_network, args=(set(ips),), daemon=True).start()
    if '--no-browser' not in sys.argv:
        if WINDOWS:
            os.startfile(INBOX)                                  # на Linux папку открывает start.sh
            webbrowser.open(f'http://127.0.0.1:{PORT}/pc')
        elif shutil.which('xdg-open'):
            subprocess.Popen(['xdg-open', f'http://127.0.0.1:{PORT}/pc'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\nостановлен')
