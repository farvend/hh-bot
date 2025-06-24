import asyncio
import aiohttp
import json
import os
from typing import Dict, List, Set

# Импорт из модулей
from models import Resume, Account, AccountResumePair
from utils import (
    EXPERIENCE_OPTIONS, 
    display_accounts_info, 
    get_experience_from_user, 
    get_search_order_from_user, 
    use_saved_settings,
    get_website_version
)
from vacancy_processor import process_resume_vacancies

# Константы
ACCOUNTS_FILE = "accounts.json"

async def main() -> None:
    """Основная функция для выполнения программы."""
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as file:
            accounts_data = json.load(file)
    except FileNotFoundError:
        print(f"Файл {ACCOUNTS_FILE} не найден.")
        return

    # Создаем аккаунты и собираем все уникальные поисковые запросы
    accounts = []
    all_search_queries = set()
    
    for account_data in accounts_data:
        resumes = [
            Resume(
                hash=resume["hash"], 
                query=resume["search_criteria"]["query"],
                blacklist=resume["search_criteria"].get("exclude_words", [])
            ) 
            for resume in account_data["resumes"]
        ]
        if resumes:  # Создаем аккаунт только если есть резюме
            accounts.append(Account(email=account_data["email"], resumes=resumes))
            for resume in resumes:
                all_search_queries.add(resume.query)

    if not accounts:
        print("Не найдено аккаунтов с резюме.")
        return

    # Отображаем информацию об аккаунтах
    display_accounts_info(accounts)
    
    # Проверяем наличие сохраненных настроек
    saved_settings = use_saved_settings()
    all_search_queries_list = list(all_search_queries)

    if saved_settings["use_saved"]:
        # Используем сохраненные настройки
        experience_list = saved_settings.get("experience", [])
        
        # Если есть сохраненный порядок поиска, применяем его
        if saved_settings.get("search_order"):
            ordered_search_queries = sorted(
                all_search_queries_list, 
                key=lambda q: saved_settings["search_order"].get(q, 999)
            )
        else:
            ordered_search_queries = all_search_queries_list
            
        # Выводим информацию о выбранных настройках
        experience_labels = [
            next((opt['label'] for opt in EXPERIENCE_OPTIONS.values() if opt['value'] == exp), exp) 
            for exp in experience_list
        ]
        print(f"\nВыбраны варианты опыта работы: {', '.join(experience_labels)}")
        print(f"Используется сохраненный порядок поиска")
    else:
        # Запрашиваем опыт работы
        experience_list = get_experience_from_user()
        experience_labels = [
            next((opt['label'] for opt in EXPERIENCE_OPTIONS.values() if opt['value'] == exp), exp) 
            for exp in experience_list
        ]
        print(f"\nВыбраны варианты опыта работы: {', '.join(experience_labels)}")

        # Получаем порядок обработки от пользователя
        ordered_search_queries = get_search_order_from_user(all_search_queries_list)

    # Создаем пары аккаунт-резюме
    account_resume_pairs = []
    pair_id = 0
    
    for account in accounts:
        for resume in account.resumes:
            account_resume_pairs.append(AccountResumePair(account, resume, pair_id))
            pair_id += 1

    if not account_resume_pairs:
        print("Не найдено подходящих пар аккаунт-резюме.")
        return

    print(f"\n=== НАЧАЛО ОБРАБОТКИ ===")
    print(f"Создано {len(account_resume_pairs)} пар аккаунт-резюме")
    print(f"Порядок обработки запросов: {' → '.join(ordered_search_queries)}")

    exhausted_pairs: List[int] = []
    pair_lock = asyncio.Lock()

    # Получаем версию сайта
    website_version = get_website_version()

    session_headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "X-Static-Version": website_version,
        "X-Xsrftoken": "1",
    }

    async with aiohttp.ClientSession(headers=session_headers) as session:
        # Обрабатываем вакансии в выбранном пользователем порядке
        for search_query in ordered_search_queries:
            # Находим все пары, которые соответствуют данному поисковому запросу
            relevant_pairs = [
                pair for pair in account_resume_pairs 
                if pair.resume.query == search_query
            ]
            
            if not relevant_pairs:
                print(f"Нет пар для поискового запроса: {search_query}")
                continue
                
            # Проверяем, есть ли доступные пары
            available_pairs = [pair for pair in relevant_pairs if pair.pair_id not in exhausted_pairs]
            if not available_pairs:
                print(f"Все аккаунты для запроса '{search_query}' исчерпаны.")
                continue
            
            # Создаем отдельный индекс для каждого поискового запроса
            pair_index = [0]
            
            await process_resume_vacancies(
                session, search_query, relevant_pairs, 
                exhausted_pairs, pair_lock, pair_index, experience_list, website_version
            )

    print(f"\n🎉 ПРОГРАММА ЗАВЕРШЕНА!")

if __name__ == "__main__":
    asyncio.run(main())