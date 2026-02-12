#!/usr/bin/env python3
"""
Скрипт для создания профиля региона (выбор ПВЗ).

Запускается ЛОКАЛЬНО на Mac/Windows с GUI.
Открывает браузер, где ты выбираешь город/ПВЗ.
После закрытия браузера профиль сохраняется в ./data/regions/<name>

Использование:
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python -m playwright install chromium
    
    python scripts/create_region_profile.py moscow_center
"""

import os
import sys
from playwright.sync_api import sync_playwright


def main(name: str):
    storage_path = f"./data/regions/{name}"
    os.makedirs(storage_path, exist_ok=True)
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  Создание профиля региона: {name:<30} ║
╠══════════════════════════════════════════════════════════════╣
║  1. Сейчас откроется браузер с сайтом Ozon                  ║
║  2. Выбери город и ПВЗ доставки                             ║
║  3. Подожди пока cookies сохранятся                         ║
║  4. Закрой браузер (НЕ через Ctrl+C!)                       ║
║                                                              ║
║  Профиль сохранится в: {storage_path:<35} ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=storage_path,
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=[
                "--disable-blink-features=AutomationControlled",
            ]
        )
        
        page = ctx.new_page()
        page.goto("https://www.ozon.ru/", wait_until="domcontentloaded")
        
        print("✅ Браузер открыт. Выбери ПВЗ/регион и закрой окно браузера.")
        print("⏳ Ожидание закрытия браузера...")
        
        # Ждём пока пользователь закроет браузер
        ctx.wait_for_event("close", timeout=0)
    
    print(f"""
✅ Профиль '{name}' сохранён!

Следующие шаги:
1. Если работаешь на сервере — скопируй папку:
   scp -r ./data/regions/{name} user@server:/path/to/app/data/regions/

2. Создай профиль в веб-интерфейсе (вкладка Regions)

3. Запусти сбор цен
""")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/create_region_profile.py <profile_name>")
        print("Example: python scripts/create_region_profile.py moscow_center")
        sys.exit(1)
    
    profile_name = sys.argv[1].strip().replace(" ", "_").lower()
    main(profile_name)
