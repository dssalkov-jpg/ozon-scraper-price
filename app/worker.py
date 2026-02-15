"""
Worker для парсинга цен с Ozon через ZenRows API.
- ZenRows обходит защиту Ozon (JS render + premium proxy)
- Простые HTTP запросы вместо браузера
"""

import re
import json
import random
import time
import os
import logging
from datetime import datetime
from urllib.parse import quote_plus

import requests
from sqlalchemy.orm import Session

from .models import Target, PricePoint

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройки
MIN_DELAY = int(os.getenv("MIN_DELAY_SECONDS", "5"))
MAX_DELAY = int(os.getenv("MAX_DELAY_SECONDS", "15"))
ZENROWS_API_KEY = os.getenv("ZENROWS_API_KEY", "")


def random_delay(min_sec: float = None, max_sec: float = None):
    """Случайная задержка между запросами"""
    min_sec = min_sec or MIN_DELAY
    max_sec = max_sec or MAX_DELAY
    delay = random.uniform(min_sec, max_sec)
    logger.info(f"Ждём {delay:.1f} сек...")
    time.sleep(delay)


def extract_price_from_html(html: str) -> dict:
    """
    Извлекает цены из HTML страницы Ozon.
    Ищет JSON-данные в HTML: "price":"1629" и подобные паттерны.
    """
    result = {"price": None, "old_price": None, "card_price": None, "in_stock": True}
    
    # Проверяем наличие товара
    if "Нет в наличии" in html or "Товар закончился" in html or "webOutOfStock" in html:
        result["in_stock"] = False
        return result
    
    # Ищем цену в JSON-данных внутри HTML
    # Паттерн: "price":"1629" или "price":1629
    price_patterns = [
        r'"price"\s*:\s*"?(\d+)"?',
        r'"finalPrice"\s*:\s*"?(\d+)"?',
        r'"salePrice"\s*:\s*"?(\d+)"?',
    ]
    
    for pattern in price_patterns:
        match = re.search(pattern, html)
        if match:
            price_val = int(match.group(1))
            # Цена в рублях, конвертируем в копейки
            result["price"] = price_val * 100
            logger.info(f"Найдена цена: {price_val} ₽")
            break
    
    # Ищем старую цену
    old_price_patterns = [
        r'"originalPrice"\s*:\s*"?(\d+)"?',
        r'"basePrice"\s*:\s*"?(\d+)"?',
        r'"oldPrice"\s*:\s*"?(\d+)"?',
    ]
    
    for pattern in old_price_patterns:
        match = re.search(pattern, html)
        if match:
            result["old_price"] = int(match.group(1)) * 100
            break
    
    # Ищем цену по карте Ozon
    card_price_patterns = [
        r'"cardPrice"\s*:\s*"?(\d+)"?',
        r'"ozonCardPrice"\s*:\s*"?(\d+)"?',
    ]
    
    for pattern in card_price_patterns:
        match = re.search(pattern, html)
        if match:
            result["card_price"] = int(match.group(1)) * 100
            break
    
    return result


class OzonScraper:
    def __init__(self, storage_path: str = None):
        # storage_path не используется с ZenRows, но оставляем для совместимости
        self.storage_path = storage_path
        
        if not ZENROWS_API_KEY:
            raise ValueError("ZENROWS_API_KEY не установлен в .env")
    
    def collect_price(self, url: str) -> dict:
        """Сбор цены для одного URL через ZenRows API"""
        result = {
            "price": None,
            "old_price": None,
            "card_price": None,
            "in_stock": True,
            "raw_json": "",
            "error": "",
        }
        
        try:
            # Формируем URL для ZenRows API
            # js_render=true - рендеринг JavaScript
            # premium_proxy=true - премиум прокси
            # proxy_country=ru - прокси из России
            # wait_for - ждём появления элемента с ценой
            # wait - максимальное время ожидания в мс
            encoded_url = quote_plus(url)
            wait_selector = quote_plus("[data-widget='webPrice']")
            
            zenrows_url = (
                f"https://api.zenrows.com/v1/"
                f"?apikey={ZENROWS_API_KEY}"
                f"&url={encoded_url}"
                f"&js_render=true"
                f"&premium_proxy=true"
                f"&proxy_country=ru"
                f"&wait_for={wait_selector}"
                f"&wait=5000"
            )
            
            logger.info(f"Запрос к ZenRows: {url[:60]}...")
            
            response = requests.get(zenrows_url, timeout=60)
            
            if response.status_code != 200:
                result["error"] = f"zenrows_error: HTTP {response.status_code}"
                logger.error(f"ZenRows вернул {response.status_code}: {response.text[:200]}")
                return result
            
            html = response.text
            
            # Проверяем, не заблокировали ли нас
            if "Доступ ограничен" in html or "Access denied" in html:
                result["error"] = "access_blocked"
                logger.warning("Ozon заблокировал доступ")
                return result
            
            # Извлекаем цены
            prices = extract_price_from_html(html)
            result.update(prices)
            
            if result["price"]:
                logger.info(f"Цена: {result['price']/100:.2f} ₽")
                result["raw_json"] = json.dumps({
                    "source": "zenrows",
                    "price": result["price"],
                    "old_price": result["old_price"],
                    "card_price": result["card_price"],
                }, ensure_ascii=False)
            else:
                result["error"] = "price_not_found"
                logger.warning("Цена не найдена в HTML")
                
        except requests.Timeout:
            result["error"] = "timeout"
            logger.error("Таймаут запроса к ZenRows")
        except Exception as e:
            result["error"] = f"error: {str(e)[:200]}"
            logger.error(f"Ошибка: {e}")
        
        return result


def run_collect(db: Session, run_id: int, storage_path: str):
    """Запуск сбора цен для всех активных целей"""
    from .models import Run
    
    targets = db.query(Target).filter(Target.enabled == True).all()
    run = db.query(Run).filter(Run.id == run_id).first()
    
    if run:
        run.total_targets = len(targets)
        db.commit()
    
    scraper = OzonScraper(storage_path)
    success_count = 0
    fail_count = 0
    
    for i, target in enumerate(targets):
        logger.info(f"[{i+1}/{len(targets)}] Обрабатываем: {target.name or target.url[:50]}")
        
        try:
            data = scraper.collect_price(target.url)
            
            pp = PricePoint(
                run_id=run_id,
                target_id=target.id,
                price=data["price"],
                old_price=data["old_price"],
                card_price=data["card_price"],
                in_stock=data["in_stock"],
                collected_at=datetime.utcnow(),
                raw_json=data["raw_json"],
                error=data["error"],
            )
            db.add(pp)
            db.commit()
            
            if data["price"]:
                success_count += 1
            else:
                fail_count += 1
        
        except Exception as e:
            logger.error(f"Критическая ошибка для {target.url}: {e}")
            pp = PricePoint(
                run_id=run_id,
                target_id=target.id,
                in_stock=True,
                collected_at=datetime.utcnow(),
                error=f"critical_error: {str(e)[:200]}",
            )
            db.add(pp)
            db.commit()
            fail_count += 1
        
        # Задержка между запросами (кроме последнего)
        if i < len(targets) - 1:
            random_delay()
    
    # Обновляем статистику run
    if run:
        run.success_count = success_count
        run.fail_count = fail_count
        db.commit()
    
    logger.info(f"Завершено: {success_count} успешно, {fail_count} с ошибками")
