import os
import socket
import time
import requests
import base64
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

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
    # добавляй свои источники сюда
]

PROTOCOLS = ["vless://", "vmess://", "trojan://", "ss://", "ssr://",
             "hysteria://", "hysteria2://", "hy2://", "tuic://"]

# ===== ПАРАМЕТРЫ =====
TARGET_COUNT = 80        # сколько РАБОЧИХ конфигов нужно в итоге
TIMEOUT = 4              # сек на проверку одного
MAX_WORKERS = 50         # параллельных проверок
MAX_ROUNDS = 5           # сколько раз прогонять источники, если рабочих мало

# ===== 1. ЗАГРУЗКА ВСЕХ КОНФИГОВ ИЗ ВСЕХ ИСТОЧНИКОВ =====
def fetch_all():
    configs = []
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200:
                for line in r.text.splitlines():
                    line = line.strip()
                    if line and any(line.startswith(p) for p in PROTOCOLS):
                        configs.append(line)
                print(f"✅ {url} — ок")
            else:
                print(f"❌ {url} — {r.status_code}")
        except Exception as e:
            print(f"⚠️ {url} — {e}")
    configs = list(dict.fromkeys(configs))
    print(f"📦 Всего уникальных конфигов: {len(configs)}")
    return configs

# ===== 2. ПАРСИНГ HOST:PORT =====
def parse_host_port(config: str):
    try:
        if config.startswith("vmess://"):
            payload = config[8:]
            decoded = base64.b64decode(payload + "=" * (-len(payload) % 4)).decode("utf-8")
            data = json.loads(decoded)
            return data.get("add"), int(data.get("port", 443))
        parsed = urlparse(config)
        return parsed.hostname, parsed.port or 443
    except Exception:
        return None, None

# ===== 3. ПРОВЕРКА ОДНОГО =====
def check_config(config: str):
    host, port = parse_host_port(config)
    if not host or not port:
        return None
    try:
        start = time.time()
        with socket.create_connection((host, port), timeout=TIMEOUT):
            ping = int((time.time() - start) * 1000)
        return (config, ping)
    except Exception:
        return None

# ===== 4. ПАРАЛЛЕЛЬНАЯ ПРОВЕРКА БАТЧА =====
def verify_batch(batch):
    alive = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(check_config, c): c for c in batch}
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                alive.append(res)
    return alive

# ===== 5. ГЛАВНЫЙ ЦИКЛ — ДОБИРАЕМ РАБОЧИЕ, ПОКА НЕ НАБЕРЁМ TARGET_COUNT =====
def collect_working(configs):
    """Проверяет конфиги батчами, отбрасывает мёртвые, добирает из очереди,
       повторяет раунды, пока не наберёт TARGET_COUNT или не кончатся конфиги."""
    alive = {}          # config -> ping
    queue = configs.copy()

    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"\n🔁 Раунд {round_num} | в очереди: {len(queue)} | уже рабочих: {len(alive)}")

        if not queue:
            print("Очередь пуста — источники закончились")
            break

        # Берём порцию на проверку
        need = TARGET_COUNT - len(alive)
        batch_size = min(len(queue), max(need * 3, 100))  # с запасом, чтобы было из чего выбирать
        batch = queue[:batch_size]
        queue = queue[batch_size:]

        print(f"  Проверяю {len(batch)} конфигов...")
        results = verify_batch(batch)
        for cfg, ping in results:
            if cfg not in alive:
                alive[cfg] = ping
        print(f"  ✅ Живых в этом раунде: {len(results)} | Всего рабочих: {len(alive)}")

        # Достигли цели — выходим
        if len(alive) >= TARGET_COUNT:
            print(f"\n🎯 Цель достигнута: {len(alive)} рабочих конфигов")
            break

        # Если конфиги кончились, но не набрали — начинаем с начала
        if not queue and len(alive) < TARGET_COUNT:
            print("⚠️ Конфиги кончились, рабочих меньше цели. Повторяю источники заново...")
            # Убираем уже проверенные мёртвые, оставляем только свежие
            queue = [c for c in configs if c not in alive]
            time.sleep(2)

    # Сортируем по пингу (самые быстрые — вперёд)
    sorted_alive = sorted(alive.items(), key=lambda x: x[1])
    return sorted_alive[:TARGET_COUNT]

# ===== 6. СОХРАНЕНИЕ =====
def save(top_configs):
    lines = [c for c, _ in top_configs]
    with open("sub.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n💾 Сохранено {len(lines)} рабочих конфигов в sub.txt")

# ===== MAIN =====
def main():
    print(f"🚀 Запуск | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    all_configs = fetch_all()
    if not all_configs:
        print("Нет конфигов — выход")
        return

    working = collect_working(all_configs)
    if not working:
        print("❌ Ничего не работает — sub.txt НЕ перезаписываю (оставляю старый)")
        return

    save(working)

    os.system('git config user.name "isyzan-bot"')
    os.system('git config user.email "bot@isyzan.local"')
    os.system('git add sub.txt')
    os.system(f'git commit -m "update {datetime.now().strftime("%Y-%m-%d %H:%M")} | alive: {len(working)}" || true')
    os.system('git push')
    print("✅ Готово")

if __name__ == "__main__":
    main()
