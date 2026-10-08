import os
import socket
import time
import base64
import json
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, quote

# ===== ИСТОЧНИКИ =====
SOURCES = [
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/bypass/bypass-1.txt",
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/bypass/bypass-2.txt",
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/bypass/bypass-3.txt",
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/bypass/bypass-4.txt",
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/bypass/bypass-5.txt",
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/bypass/bypass-6.txt",
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/bypass/bypass-7.txt",
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/bypass/bypass-8.txt",
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/bypass/bypass-9.txt",
]

PROTOCOLS = ["vless://", "vmess://", "trojan://", "ss://", "ssr://",
             "hysteria://", "hysteria2://", "hy2://", "tuic://"]

# ===== ПАРАМЕТРЫ =====
TARGET_COUNT = 80
TIMEOUT = 4
MAX_WORKERS = 50
MAX_ROUNDS = 5

# ===== КЭШ ГЕО =====
GEO_CACHE = {}
GEO_API = "http://ip-api.com/json/{ip}?fields=status,country,countryCode"


# ===== 1. ЗАГРУЗКА =====
def fetch_all():
    configs = []
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=25)
            if r.status_code == 200:
                cnt = 0
                for line in r.text.splitlines():
                    line = line.strip()
                    if line and any(line.startswith(p) for p in PROTOCOLS):
                        configs.append(line)
                        cnt += 1
                print(f"OK  {url}  -> {cnt}")
            else:
                print(f"ERR {url}  -> {r.status_code}")
        except Exception as e:
            print(f"ERR {url}  -> {e}")
    configs = list(dict.fromkeys(configs))
    print(f"Всего уникальных конфигов: {len(configs)}")
    return configs


# ===== 2. ИЗВЛЕЧЬ HOST:PORT =====
def parse_host_port(cfg):
    try:
        if cfg.startswith("vmess://"):
            payload = cfg[8:]
            decoded = base64.b64decode(payload + "=" * (-len(payload) % 4)).decode("utf-8", "ignore")
            d = json.loads(decoded)
            return d.get("add"), int(d.get("port", 443))
        u = urlparse(cfg)
        return u.hostname, (u.port or 443)
    except Exception:
        return None, None


# ===== 3. TCP-ПРОВЕРКА =====
def check_one(cfg):
    host, port = parse_host_port(cfg)
    if not host or not port:
        return None
    try:
        start = time.time()
        with socket.create_connection((host, port), timeout=TIMEOUT):
            ping = int((time.time() - start) * 1000)
        return (cfg, host, ping)
    except Exception:
        return None


# ===== 4. БАТЧ-ПРОВЕРКА =====
def verify_batch(batch):
    alive = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(check_one, c) for c in batch]
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                alive.append(r)
    return alive


# ===== 5. ГЕО-ОПРЕДЕЛЕНИЕ =====
def get_country(host):
    if not host:
        return None, None
    # Если это домен — резолвим в IP
    ip = host
    try:
        socket.inet_aton(host)
    except OSError:
        try:
            ip = socket.gethostbyname(host)
        except Exception:
            return None, None

    if ip in GEO_CACHE:
        return GEO_CACHE[ip]

    try:
        r = requests.get(GEO_API.format(ip=ip), timeout=5)
        data = r.json()
        if data.get("status") == "success":
            result = (data.get("countryCode", ""), data.get("country", ""))
        else:
            result = (None, None)
    except Exception:
        result = (None, None)

    GEO_CACHE[ip] = result
    time.sleep(0.05)   # мягкий rate-limit (ip-api: 45/мин)
    return result


# ===== 6. ФЛАГ ИЗ КОДА СТРАНЫ =====
def flag_emoji(country_code):
    if not country_code or len(country_code) != 2:
        return "🏴"
    code = country_code.upper()
    return chr(0x1F1E6 + ord(code[0]) - ord("A")) + chr(0x1F1E6 + ord(code[1]) - ord("A"))


# ===== 7. ПЕРЕИМЕНОВАТЬ КОНФИГ =====
def rename_config(cfg, country_code, country_name):
    if not country_name:
        label = "🌐 Unknown (LTE)"
    else:
        label = f"{flag_emoji(country_code)} {country_name} (LTE)"

    # Убираем старый фрагмент (#...) если он есть
    base = cfg.split("#", 1)[0]

    # Для vmess — переименование делается через поле "ps" в JSON
    if base.startswith("vmess://"):
        try:
            payload = base[8:]
            decoded = base64.b64decode(payload + "=" * (-len(payload) % 4)).decode("utf-8", "ignore")
            d = json.loads(decoded)
            d["ps"] = label
            new_payload = base64.b64encode(json.dumps(d, ensure_ascii=False).encode("utf-8")).decode("ascii")
            return "vmess://" + new_payload
        except Exception:
            return base + "#" + quote(label)

    # Для всех остальных — просто добавляем #label
    return base + "#" + quote(label)


# ===== 8. ДОБОР РАБОЧИХ =====
def collect_working(configs):
    alive = {}   # cfg -> (host, ping)
    queue = configs.copy()

    for rnd in range(1, MAX_ROUNDS + 1):
        print(f"\nРаунд {rnd} | очередь: {len(queue)} | уже рабочих: {len(alive)}")
        if not queue:
            print("Очередь пуста — заново")
            queue = [c for c in configs if c not in alive]
            if not queue:
                break
            time.sleep(2)

        need = TARGET_COUNT - len(alive)
        take = min(len(queue), max(need * 3, 100))
        batch = queue[:take]
        queue = queue[take:]

        print(f"Проверяю {len(batch)} конфигов...")
        results = verify_batch(batch)
        for cfg, host, ping in results:
            if cfg not in alive:
                alive[cfg] = (host, ping)
        print(f"Живых в раунде: {len(results)} | всего рабочих: {len(alive)}")

        if len(alive) >= TARGET_COUNT:
            break

    return sorted(alive.items(), key=lambda x: x[1][1])[:TARGET_COUNT]


# ===== 9. СОХРАНЕНИЕ =====
def save(top):
    print(f"\nОпределяю страны для {len(top)} конфигов...")
    lines = []
    for i, (cfg, (host, ping)) in enumerate(top, 1):
        cc, cn = get_country(host)
        renamed = rename_config(cfg, cc, cn)
        lines.append(renamed)
        if i % 10 == 0:
            print(f"  обработано {i}/{len(top)}")

    with open("sub.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Сохранено {len(lines)} конфигов в sub.txt")


# ===== MAIN =====
def main():
    print(f"Запуск | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    all_cfg = fetch_all()
    if not all_cfg:
        print("Нет конфигов")
        return

    working = collect_working(all_cfg)
    if not working:
        print("Ничего не работает — sub.txt не трогаю")
        return

    save(working)

    os.system('git config user.name "isyzan-bot"')
    os.system('git config user.email "bot@isyzan.local"')
    os.system('git add sub.txt')
    os.system(f'git commit -m "update {datetime.now().strftime("%Y-%m-%d %H:%M")} | alive: {len(working)}" || true')
    os.system('git push')
    print("Готово")


if __name__ == "__main__":
    main()
