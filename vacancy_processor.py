import asyncio
from typing import Dict, List

from models import AccountResumePair
from utils import is_vacancy_blacklisted
from api import get_vacancies, get_vacancies_pages

async def process_vacancy(
    vacancy: Dict,
    relevant_pairs: List[AccountResumePair],  # Только релевантные пары для данного поискового запроса
    exhausted_pairs: List[int],
    pair_lock: asyncio.Lock,
    pair_index: List[int]
) -> None:
    """Обрабатывает вакансию и отправляет отклик, если это возможно."""
    name = vacancy["name"]
    
    # Проверяем blacklist для первой найденной пары (у всех пар одинаковый query и blacklist)
    if relevant_pairs and is_vacancy_blacklisted(name, relevant_pairs[0].resume.blacklist):
        print(f"Вакансия пропущена (blacklist): {name}")
        return

    async with pair_lock:
        # Фильтруем только неисчерпанные пары из релевантных
        available_pairs = [pair for pair in relevant_pairs if pair.pair_id not in exhausted_pairs]
        
        if not available_pairs:
            print(f"Нет доступных аккаунтов для отклика на вакансию: {name}")
            return
        
        # Выбираем следующую пару по круговому принципу среди доступных
        pair = available_pairs[pair_index[0] % len(available_pairs)]
        curr_pair_id = pair.pair_id
        pair_index[0] = (pair_index[0] + 1) % len(available_pairs)

    resp = await pair.account.respond_to_vacancy(vacancy["vacancyId"], pair.resume)
    if resp["success"]:
        print(f"Отклик отправлен на вакансию: {name} (резюме: {pair.resume.query}, аккаунт: {pair.account.email})")
    else:
        error = resp["error"]
        if error == "negotiations-limit-exceeded":
            print(f"Лимит откликов аккаунта {pair.account.email} исчерпан.")
            async with pair_lock:
                if curr_pair_id not in exhausted_pairs:
                    exhausted_pairs.append(curr_pair_id)
        elif error != "unknown":
            print(f"Не удалось откликнуться на вакансию {name}: {error}")

async def process_resume_vacancies(
    session,
    search_query: str,
    relevant_pairs: List[AccountResumePair],  # Только пары, релевантные для данного поискового запроса
    exhausted_pairs: List[int],
    pair_lock: asyncio.Lock,
    pair_index: List[int],
    experience_list: List[str],
    website_version: str
) -> None:
    """Обрабатывает все вакансии для конкретного поискового запроса."""
    print(f"\n=== Начинаем поиск вакансий для запроса: {search_query} ===")
    
    # Проверяем, есть ли доступные пары для данного поискового запроса
    available_pairs = [pair for pair in relevant_pairs if pair.pair_id not in exhausted_pairs]
    if not available_pairs:
        print(f"Нет доступных аккаунтов для поискового запроса: {search_query}")
        return
    
    print(f"Доступно аккаунтов для '{search_query}': {len(available_pairs)}")
    for pair in available_pairs:
        print(f"  - {pair.account.email}")
    
    last_page = await get_vacancies_pages(session, search_query, experience_list, website_version)
    print(f"Найдено страниц для '{search_query}': {last_page}")
    
    for page in range(0, last_page + 1):
        # Проверяем доступные пары перед каждой страницей
        available_pairs = [pair for pair in relevant_pairs if pair.pair_id not in exhausted_pairs]
        if not available_pairs:
            print(f"\n❌ Лимит всех аккаунтов для запроса '{search_query}' исчерпан.")
            break
            
        vacancies = await get_vacancies(session, search_query, page, experience_list, website_version)
        print(f"Обрабатываем страницу {page}/{last_page} для '{search_query}' ({len(vacancies)} вакансий)")
        
        tasks = [
            process_vacancy(vacancy, relevant_pairs, exhausted_pairs, pair_lock, pair_index)
            for vacancy in vacancies
        ]
        await asyncio.gather(*tasks)
    
    print(f"✅ Завершена обработка запроса: {search_query}") 