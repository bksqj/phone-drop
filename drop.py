#!/usr/bin/env python3
"""phone-drop: передача файлов iPhone <-> ноутбук по Wi-Fi без интернета.
Запуск: python3 drop.py   -> открыть на телефоне в Safari адрес, который покажет программа."""
import json, os, shutil, subprocess, sys, threading, time, urllib.parse
import qr
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

PORT = 8000
def downloads_dir():
    """папка «Загрузки» в любой локали (Загрузки / Downloads)"""
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
</style></head><body>
<h1>📲 Phone Drop</h1>
<label class="drop"><input id="f" type="file" multiple><b>Выбрать файлы</b><span>фото, видео, документы — уйдут на ноутбук</span></label>
<div id="q"></div>
<h2>Текст на ноутбук</h2>
<textarea id="t" placeholder="Вставь или напиши текст — ссылку, заметку, пароль от Wi-Fi…"></textarea>
<button id="tb">Отправить текст</button><div id="ts" class="mut"></div>
<h2>Скачать с ноутбука (папка «Загрузки/На телефон»)</h2><div id="out"><div class="mut">загрузка…</div></div>
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
fetch('/list').then(r=>r.json()).then(l=>{const o=document.getElementById('out');
  o.innerHTML=l.length?'':'<div class="mut">пусто — положи файлы в эту папку на ноутбуке</div>';
  for(const f of l){const d=document.createElement('div');d.className='row';
    d.innerHTML=`<a href="/get/${encodeURIComponent(f.name)}" download>${f.name.replace(/</g,'&lt;')}</a> <span class="mut">${fmt(f.size)}</span>`;o.append(d)}});
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

    def do_GET(self):
        path = urllib.parse.unquote(self.path)
        if path == '/':
            return self.send(200, PAGE.encode())
        if path == '/list':
            files = [{'name': f, 'size': os.path.getsize(os.path.join(OUTBOX, f))}
                     for f in sorted(os.listdir(OUTBOX)) if os.path.isfile(os.path.join(OUTBOX, f))]
            return self.send(200, json.dumps(files).encode(), 'application/json')
        if path.startswith('/get/'):
            name = os.path.basename(path[5:])                    # basename - нельзя выйти из папки
            full = os.path.join(OUTBOX, name)
            if not os.path.isfile(full):
                return self.send(404, b'not found')
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(os.path.getsize(full)))
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + urllib.parse.quote(name))
            self.end_headers()
            with open(full, 'rb') as f:
                shutil.copyfileobj(f, self.wfile)
            print(f'  -> отдал на телефон: {name}')
            return
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
        if self.path == '/text':
            return self.save_text()
        if self.path != '/upload':
            return self.send(404, b'not found')
        name = os.path.basename(urllib.parse.unquote(self.headers.get('X-Filename', 'file'))) or 'file'
        left = int(self.headers.get('Content-Length', 0))
        dest = unique(os.path.join(INBOX, name))
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
            return self.send(400, b'incomplete')
        os.rename(tmp, dest)
        print(f'  <- получил: {os.path.basename(dest)} ({os.path.getsize(dest) // 1024} КБ)')
        self.send(200, b'ok')

    def log_message(self, *a):
        pass                                                     # не засоряем консоль логами запросов


def copy_to_clipboard(text):
    """если установлен xclip - кладём текст в буфер обмена ноутбука"""
    if not shutil.which('xclip'):
        return False
    try:
        subprocess.run(['xclip', '-selection', 'clipboard'], input=text.encode(), timeout=3)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def local_ips():
    out = subprocess.run(['hostname', '-I'], capture_output=True, text=True).stdout.split()
    return [ip for ip in out if '.' in ip and not ip.startswith(('127.', '10.8.', '100.'))]


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
    print('  Остановить: Ctrl+C')
    print('=' * 50)
    ips = local_ips()
    for ip in sorted(ips, key=lambda a: not a.startswith('172.20.10.')):   # кабель/модем айфона - первым
        show(ip)
    if not ips:
        print('\n  Сети пока нет - подключи iPhone кабелем, QR появится сам')
    threading.Thread(target=watch_network, args=(set(ips),), daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\nостановлен')
