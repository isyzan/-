import os
import socket
import time
import base64
import json
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

# ===== ИСТОЧНИКИ ПОДПИСОК =====
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
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/bypass/bypass-10.txt",
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/bypass/bypass-11.txt",
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/bypass/bypass-12.txt",
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/bypass/bypass-13.txt",
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/bypass/bypass-14.txt",
    "https://raw.githubusercontent.com/whoahaow/rjsxrd/main/githubmirror/bypass/bypass-15.txt",
]

PROTOCOLS = ["vless://", "vmess://", "trojan://", "ss://", "ssr://",
             "hysteria://", "hysteria2://", "hy2://", "tuic://"]

# ===== ПАРАМЕТРЫ =====
TARGET_COUNT = 80       # сколько рабочих конфигов нужно
TIMEOUT = 4             # сек на TCP-проверку одного
MAX_WORKERS = 50        # параллельных проверок
MAX_ROUNDS = 5          # сколько раз гонять источники


# ===== 1. ЗАГРУЗКА ВСЕХ КОНФИГОВ =====
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
        return (cfg, ping)
    except Exception:
        return None


# ===== 4. ПРОВЕРКА БАТЧА ПАРАЛЛЕЛЬНО =====
def verify_batch(batch):
    alive = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(check_one, c) for c in batch]
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                alive.append(r)
    return alive


# ===== 5. ДОБИРАЕМ РАБОЧИЕ, ПОКА НЕ НАБЕРЁМ ЦЕЛЬ =====
def collect_working(configs):
    alive = {}
    queue = configs.copy()

    for rnd in range(1, MAX_ROUNDS + 1):
        print(f"\nРаунд {rnd} | очередь: {len(queue)} | уже рабочих: {len(alive)}")
        if not queue:
            print("Очередь пуста — повторяю источники заново")
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
        for cfg, ping in results:
            if cfg not in alive:
                alive[cfg] = ping
        print(f"Живых в раунде: {len(results)} | всего рабочих: {len(alive)}")

        if len(alive) >= TARGET_COUNT:
            print(f"Цель достигнута: {len(alive)}")
            break

    sorted_alive = sorted(alive.items(), key=lambda x: x[1])
    return sorted_alive[:TARGET_COUNT]


# ===== 6. СОХРАНЕНИЕ =====
def save(top):
    lines = [c for c, _ in top]
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
