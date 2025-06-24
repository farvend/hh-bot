import json
import re
import requests
from typing import Dict, List

# Константы
PREFERENCES_FILE = "preferences.json"

# Опции опыта работы
EXPERIENCE_OPTIONS = {
    "1": {"label": "Нет опыта", "value": "noExperience"},
    "2": {"label": "От 1 до 3 лет", "value": "between1And3"},
    "3": {"label": "От 3 до 6 лет", "value": "between3And6"},
    "4": {"label": "Более 6 лет", "value": "moreThan6"}
}

def cookies_to_string(cookies: Dict[str, str]) -> str:
    """Преобразует словарь кук в строку."""
    return "; ".join(f"{key}={value}" for key, value in cookies.items())

def parse_cookies(cookie_str: str) -> Dict[str, str]:
    """Парсит строку кук в словарь."""
    return dict(cookie.strip().split("=", 1) for cookie in cookie_str.split(";"))

def get_website_version() -> str:
    """Получает версию сайта hh.ru."""
    url = "https://hh.ru/?hhtmFrom=resume_list"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    }
    response = requests.get(url, headers=headers)
    version = re.search(r"[1-9]{0,2}\.[1-9]{0,2}\.[1-9]{0,2}\.[1-9]{0,2}", response.text)
    if not version:
        raise ValueError("Не удалось определить версию сайта")
    return version.group(0)

def load_preferences() -> Dict:
    """Загружает сохраненные предпочтения пользователя."""
    import os
    if os.path.exists(PREFERENCES_FILE):
        try:
            with open(PREFERENCES_FILE, "r", encoding="utf-8") as file:
                return json.load(file)
        except json.JSONDecodeError:
            return {}
    return {}

def save_preferences(preferences: Dict) -> None:
    """Сохраняет предпочтения пользователя."""
    with open(PREFERENCES_FILE, "w", encoding="utf-8") as file:
        json.dump(preferences, file, indent=4)

def use_saved_settings() -> Dict:
    """Проверяет наличие сохраненных настроек и предлагает их использовать."""
    preferences = load_preferences()
    
    if not preferences:
        return {"use_saved": False}
    
    has_experience = "experience" in preferences and preferences["experience"]
    has_search_order = "search_order" in preferences and preferences["search_order"]
    
    if not (has_experience or has_search_order):
        return {"use_saved": False}
    
    print("\n=== СОХРАНЕННЫЕ НАСТРОЙКИ ===")
    
    if has_experience:
        experience_labels = [
            next((opt['label'] for opt in EXPERIENCE_OPTIONS.values() if opt['value'] == exp), exp) 
            for exp in preferences["experience"]
        ]
        print(f"Опыт работы: {', '.join(experience_labels)}")
    
    if has_search_order:
        print("Порядок поиска: сохранен")
    
    print("\nИспользовать сохраненные настройки? (y/n)")
    user_choice = input("Ваш выбор: ").strip().lower()
    
    if user_choice in ['y', 'yes', 'да', '']:
        return {
            "use_saved": True,
            "experience": preferences.get("experience", []),
            "search_order": preferences.get("search_order", {})
        }
    else:
        return {"use_saved": False}

def is_vacancy_blacklisted(vacancy_name: str, blacklist: List[str]) -> bool:
    """Проверяет, содержит ли название вакансии исключаемые слова."""
    if not blacklist:
        return False
    
    vacancy_name_lower = vacancy_name.lower()
    return any(word.lower() in vacancy_name_lower for word in blacklist)

def display_accounts_info(accounts: List) -> None:
    """Отображает информацию об аккаунтах и их резюме."""
    print("\n=== ИНФОРМАЦИЯ ОБ АККАУНТАХ ===")
    for i, account in enumerate(accounts, 1):
        print(f"\nАккаунт {i}: {account.email}")
        for j, resume in enumerate(account.resumes, 1):
            blacklist_info = f" (исключения: {', '.join(resume.blacklist)})" if resume.blacklist else ""
            print(f"  Резюме {j}: {resume.query}{blacklist_info}")

def get_experience_from_user() -> List[str]:
    """Запрашивает у пользователя предпочтительный опыт работы."""
    preferences = load_preferences()
    saved_experience = preferences.get("experience", [])
    
    print("\n=== ВЫБОР ОПЫТА РАБОТЫ ===")
    print("Доступные варианты:")
    
    for key, option in EXPERIENCE_OPTIONS.items():
        saved_mark = " (сохранено)" if option["value"] in saved_experience else ""
        print(f"{key}. {option['label']}{saved_mark}")
    
    print("\nВыберите один или несколько вариантов через пробел (например: 1 2)")
    if saved_experience:
        print(f"Нажмите Enter, чтобы использовать сохраненные варианты")
    
    while True:
        user_input = input("\nВаш выбор: ").strip()
        
        if not user_input and saved_experience:
            # Используем сохраненный вариант
            print(f"Используются сохраненные варианты опыта работы")
            return saved_experience
        
        try:
            # Парсим ввод пользователя
            selected_keys = user_input.split()
            
            # Проверяем корректность введенных номеров
            if not all(key in EXPERIENCE_OPTIONS for key in selected_keys):
                print("Ошибка: Выберите варианты из предложенного списка")
                continue
                
            if not selected_keys:
                print("Ошибка: Выберите хотя бы один вариант")
                continue
            
            # Получаем значения выбранных опций
            selected_experience = [EXPERIENCE_OPTIONS[key]["value"] for key in selected_keys]
            
            # Спрашиваем, хочет ли пользователь сохранить выбор
            save_choice = input("Сохранить этот выбор? (y/n): ").strip().lower()
            if save_choice in ['y', 'yes', 'да', '']:
                preferences["experience"] = selected_experience
                save_preferences(preferences)
                print("Выбор сохранен")
            
            return selected_experience
            
        except ValueError:
            print("Ошибка: Введите номера через пробел (например: 1 2)")
            continue

def get_search_order_from_user(all_search_queries: List[str]) -> List[str]:
    """Запрашивает у пользователя порядок обработки поисковых запросов."""
    preferences = load_preferences()
    saved_order = preferences.get("search_order", {})
    
    print("\n=== ВЫБОР ПОРЯДКА ОТКЛИКА НА ВАКАНСИИ ===")
    print("Доступные поисковые запросы:")
    
    for i, query in enumerate(all_search_queries, 1):
        saved_position = saved_order.get(query, -1)
        saved_info = f" (сохранено на позиции {saved_position})" if saved_position > 0 else ""
        print(f"{i}. {query}{saved_info}")
    
    print("\nВыберите порядок обработки запросов для максимально эффективного")
    print("использования лимита в 200 откликов на каждый аккаунт.")
    print("Введите номера через пробел в нужном порядке (например: 2 1 3)")
    
    if saved_order and len(saved_order) == len(all_search_queries):
        print("Или нажмите Enter для использования сохраненного порядка")
    else:
        print("Или нажмите Enter для автоматического порядка")
    
    while True:
        user_input = input("\nВаш выбор: ").strip()
        
        if not user_input:
            # Если пользователь не выбрал порядок
            if saved_order and len(saved_order) == len(all_search_queries):
                # Используем сохраненный порядок
                ordered_queries = sorted(all_search_queries, key=lambda q: saved_order.get(q, 999))
                print("Используется сохраненный порядок")
                return ordered_queries
            else:
                # Используем исходный порядок
                print("Используется автоматический порядок")
                return all_search_queries
        
        try:
            # Парсим ввод пользователя
            selected_indices = [int(x) - 1 for x in user_input.split()]
            
            # Проверяем корректность введенных номеров
            if len(selected_indices) != len(all_search_queries):
                print(f"Ошибка: Нужно указать {len(all_search_queries)} номеров")
                continue
                
            if any(i < 0 or i >= len(all_search_queries) for i in selected_indices):
                print(f"Ошибка: Номера должны быть от 1 до {len(all_search_queries)}")
                continue
                
            if len(set(selected_indices)) != len(selected_indices):
                print("Ошибка: Номера не должны повторяться")
                continue
            
            # Создаем упорядоченный список запросов
            ordered_queries = [all_search_queries[i] for i in selected_indices]
            
            print("\nВыбранный порядок:")
            for i, query in enumerate(ordered_queries, 1):
                print(f"{i}. {query}")
            
            # Подтверждение
            confirm = input("\nПодтвердить? (y/n): ").strip().lower()
            if confirm in ['y', 'yes', 'да', '']:
                # Сохраняем порядок
                new_order = {query: i+1 for i, query in enumerate(ordered_queries)}
                preferences = load_preferences()
                preferences["search_order"] = new_order
                save_preferences(preferences)
                print("Порядок сохранен")
                return ordered_queries
            else:
                print("Попробуйте еще раз")
                continue
                
        except ValueError:
            print("Ошибка: Введите номера через пробел (например: 2 1 3)")
            continue 