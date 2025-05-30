import asyncio
import aiohttp
import json
import re
import requests
import os
from typing import Dict, List, Optional, Tuple
from aiohttp import FormData

# Константы
ACCOUNTS_FILE = "accounts.json"
COOKIES_DIR = "cookies"

class Resume:
    """Класс для управления резюме."""
    
    def __init__(self, hash: str, query: str, blacklist: List[str] = None):
        self.hash = hash
        self.query = query  # Поисковый запрос для данного резюме
        self.blacklist = blacklist or []  # Список исключаемых слов/фраз

class Account:
    """Класс для управления аккаунтом и отправки откликов на вакансии."""
    
    def __init__(self, email: str, resumes: List[Resume]):
        self.email = email
        self.resumes = resumes
        self.cookies = {}
        self.is_token_being_updated = False
        self.load_cookies()

    def get_cookies_file_path(self) -> str:
        """Возвращает путь к файлу с куками для данного аккаунта."""
        return os.path.join(COOKIES_DIR, f"{self.email}.json")

    def load_cookies(self) -> None:
        """Загружает куки из файла."""
        cookies_file = self.get_cookies_file_path()
        if os.path.exists(cookies_file):
            try:
                with open(cookies_file, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    self.cookies = data.get("cookies", {})
            except (json.JSONDecodeError, FileNotFoundError):
                self.cookies = {}

    def update_cookies(self, cookies: Dict[str, str]) -> None:
        """Обновляет куки в объекте."""
        self.cookies.update(cookies)

    def save_cookies_to_file(self) -> None:
        """Сохраняет обновленные куки в файл."""
        # Создаем папку cookies, если её нет
        os.makedirs(COOKIES_DIR, exist_ok=True)
        
        cookies_file = self.get_cookies_file_path()
        data = {"cookies": self.cookies}
        
        with open(cookies_file, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

    def prompt_cookies_update(self) -> None:
        """Запрашивает у пользователя новые куки и обновляет их."""
        self.is_token_being_updated = True
        new_cookies = parse_cookies(input(f"Введите новые куки для {self.email}: "))
        self.update_cookies(new_cookies)
        self.save_cookies_to_file()
        self.is_token_being_updated = False

    async def respond_to_vacancy(self, vacancy_id: int, resume: Resume) -> Dict[str, str | bool]:
        """Отправляет отклик на вакансию используя указанное резюме."""
        url = "https://hh.ru/applicant/vacancy_response/popup"
        payload = {
            "resume_hash": resume.hash,
            "vacancy_id": str(vacancy_id),
            "lux": "true",
            "ignore_postponed": "true",
            "mark_applicant_visible_in_vacancy_country": "false",
        }
        
        form_data = FormData()
        for key, value in payload.items():
            form_data.add_field(key, value)

        headers = {
            "User-Agent": "Mozilla/5.0",
            "X-Xsrftoken": self.cookies.get("_xsrf", ""),
            "Accept": "application/json",
            "Cookie": cookies_to_string(self.cookies),
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=form_data, headers=headers) as response:
                text = await response.text()
                
                if response.status == 403:
                    print(f"403 Forbidden: {text[:100]}")
                    if not self.is_token_being_updated:
                        self.prompt_cookies_update()
                    else:
                        while self.is_token_being_updated:
                            await asyncio.sleep(5)
                    return await self.respond_to_vacancy(vacancy_id, resume)
                
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    print(f"Некорректный JSON-ответ. Статус: {response.status}, Текст: {text}")
                    return {"success": False, "error": "Некорректный JSON-ответ"}

                if "error" in data:
                    return {"success": False, "error": data["error"]}
                
                if data.get("type") == "need-login":
                    if not self.is_token_being_updated:
                        self.prompt_cookies_update()
                    else:
                        while self.is_token_being_updated:
                            await asyncio.sleep(5)
                    return await self.respond_to_vacancy(vacancy_id, resume)
                
                success_result = {"success": data.get("success") == "true"}
                if success_result["success"]:
                    success_result["resume_used"] = resume.query
                return success_result

class AccountResumePair:
    """Класс для представления пары аккаунт-резюме."""
    
    def __init__(self, account: Account, resume: Resume, pair_id: int):
        self.account = account
        self.resume = resume
        self.pair_id = pair_id
        self.is_exhausted = False

def display_accounts_info(accounts: List[Account]) -> None:
    """Отображает информацию об аккаунтах и их резюме."""
    print("\n=== ИНФОРМАЦИЯ ОБ АККАУНТАХ ===")
    for i, account in enumerate(accounts, 1):
        print(f"\nАккаунт {i}: {account.email}")
        for j, resume in enumerate(account.resumes, 1):
            blacklist_info = f" (исключения: {', '.join(resume.blacklist)})" if resume.blacklist else ""
            print(f"  Резюме {j}: {resume.query}{blacklist_info}")

def get_search_order_from_user(all_search_queries: List[str]) -> List[str]:
    """Запрашивает у пользователя порядок обработки поисковых запросов."""
    print("\n=== ВЫБОР ПОРЯДКА ОТКЛИКА НА ВАКАНСИИ ===")
    print("Доступные поисковые запросы:")
    
    for i, query in enumerate(all_search_queries, 1):
        print(f"{i}. {query}")
    
    print("\nВыберите порядок обработки запросов для максимально эффективного")
    print("использования лимита в 200 откликов на каждый аккаунт.")
    print("Введите номера через пробел в нужном порядке (например: 2 1 3)")
    print("Или нажмите Enter для автоматического порядка")
    
    while True:
        user_input = input("\nВаш выбор: ").strip()
        
        if not user_input:
            # Если пользователь не выбрал порядок, возвращаем исходный список
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
                return ordered_queries
            else:
                print("Попробуйте еще раз")
                continue
                
        except ValueError:
            print("Ошибка: Введите номера через пробел (например: 2 1 3)")
            continue

async def get_vacancies_data(session: aiohttp.ClientSession, params: str) -> Dict:
    """Получает данные о вакансиях с сайта."""
    url = f"https://hh.ru/search/vacancy?{params}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "X-Static-Version": website_version,
        "X-Xsrftoken": "1",
    }
    
    async with session.get(url, headers=headers) as response:
        text = await response.text()
        match = re.search(r'{"topLevelSite".*"action":"POP"}}', text)
        if not match:
            raise ValueError("Не удалось извлечь данные о вакансиях из ответа")
        return json.loads(match.group(0))

async def get_vacancies(session: aiohttp.ClientSession, request: str, page: int) -> List[Dict]:
    """Получает список вакансий для указанной страницы."""
    params = f"text={request}&salary=&ored_clusters=true&experience=between1And3&page={page}"
    data = await get_vacancies_data(session, params)
    return data["vacancySearchResult"]["vacancies"]

async def get_vacancies_pages(session: aiohttp.ClientSession, request: str) -> int:
    """Возвращает количество страниц с вакансиями."""
    params = f"text={request}&salary=&ored_clusters=true&experience=between1And3&page=1"
    data = await get_vacancies_data(session, params)
    paging = data["vacancySearchResult"]["paging"]
    if paging == None:
        return 1
    else:
        return data["vacancySearchResult"]["paging"]["lastPage"]["page"]

def is_vacancy_blacklisted(vacancy_name: str, blacklist: List[str]) -> bool:
    """Проверяет, содержит ли название вакансии исключаемые слова."""
    if not blacklist:
        return False
    
    vacancy_name_lower = vacancy_name.lower()
    return any(word.lower() in vacancy_name_lower for word in blacklist)

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
    session: aiohttp.ClientSession,
    search_query: str,
    relevant_pairs: List[AccountResumePair],  # Только пары, релевантные для данного поискового запроса
    exhausted_pairs: List[int],
    pair_lock: asyncio.Lock,
    pair_index: List[int]
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
    
    last_page = await get_vacancies_pages(session, search_query)
    print(f"Найдено страниц для '{search_query}': {last_page}")
    
    for page in range(0, last_page + 1):
        # Проверяем доступные пары перед каждой страницей
        available_pairs = [pair for pair in relevant_pairs if pair.pair_id not in exhausted_pairs]
        if not available_pairs:
            print(f"\n❌ Лимит всех аккаунтов для запроса '{search_query}' исчерпан.")
            break
            
        vacancies = await get_vacancies(session, search_query, page)
        print(f"Обрабатываем страницу {page}/{last_page} для '{search_query}' ({len(vacancies)} вакансий)")
        
        tasks = [
            process_vacancy(vacancy, relevant_pairs, exhausted_pairs, pair_lock, pair_index)
            for vacancy in vacancies
        ]
        await asyncio.gather(*tasks)
    
    print(f"✅ Завершена обработка запроса: {search_query}")

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

    # Получаем порядок обработки от пользователя
    all_search_queries_list = list(all_search_queries)
    ordered_search_queries = get_search_order_from_user(all_search_queries_list)

    print(f"\n=== НАЧАЛО ОБРАБОТКИ ===")
    print(f"Создано {len(account_resume_pairs)} пар аккаунт-резюме")
    print(f"Порядок обработки запросов: {' → '.join(ordered_search_queries)}")

    exhausted_pairs: List[int] = []
    pair_lock = asyncio.Lock()

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
                exhausted_pairs, pair_lock, pair_index
            )

    print(f"\n🎉 ПРОГРАММА ЗАВЕРШЕНА!")

if __name__ == "__main__":
    website_version = get_website_version()
    asyncio.run(main())