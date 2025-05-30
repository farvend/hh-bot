import asyncio
import aiohttp
import json
import re
import requests
from typing import Dict, List, Optional
from aiohttp import FormData

# Константы
CONFIG_FILE = "config.json"
ACCOUNTS_FILE = "accounts.json"

class Account:
    """Класс для управления аккаунтом и отправки откликов на вакансии."""
    
    def __init__(self, email: str, resume_hash: str, cookies: Dict[str, str] = None):
        self.email = email
        self.resume_hash = resume_hash
        self.cookies = cookies or {}
        self.is_token_being_updated = False
        self.cookie_jar = aiohttp.CookieJar()
        self.update_cookies(self.cookies)

    def update_cookies(self, cookies: Dict[str, str]) -> None:
        """Обновляет куки в объекте и в cookie_jar."""
        self.cookies.update(cookies)
        self.cookie_jar.update_cookies(cookies)

    def save_cookies_to_file(self) -> None:
        """Сохраняет обновленные куки в файл accounts.json."""
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        
        for account in data:
            if account["email"] == self.email:
                account["cookies"] = self.cookies
                break
        
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)

    def prompt_cookies_update(self) -> None:
        """Запрашивает у пользователя новые куки и обновляет их."""
        self.is_token_being_updated = True
        new_cookies = parse_cookies(input(f"Введите новые куки для {self.email}: "))
        self.update_cookies(new_cookies)
        self.save_cookies_to_file()
        self.is_token_being_updated = False

    async def respond_to_vacancy(self, vacancy_id: int) -> Dict[str, str | bool]:
        """Отправляет отклик на вакансию и возвращает результат."""
        url = "https://hh.ru/applicant/vacancy_response/popup"
        payload = {
            "resume_hash": self.resume_hash,
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

        async with aiohttp.ClientSession(cookie_jar=self.cookie_jar) as session:
            async with session.post(url, data=form_data, headers=headers) as response:
                text = await response.text()
                
                if response.status == 403:
                    print(f"403 Forbidden: {text[:100]}")
                    if not self.is_token_being_updated:
                        self.prompt_cookies_update()
                    else:
                        while self.is_token_being_updated:
                            await asyncio.sleep(5)
                    return await self.respond_to_vacancy(vacancy_id)
                
                # if response.status != 200:
                #     return {"success": False, "error": f"HTTP {response.status}"}

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
                    return await self.respond_to_vacancy(vacancy_id)
                
                return {"success": data.get("success") == "true"}

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
    return data["vacancySearchResult"]["paging"]["lastPage"]["page"]

async def process_vacancy(
    vacancy: Dict,
    accounts: List[Account],
    ignored_account_ids: List[int],
    account_lock: asyncio.Lock,
    account_index: List[int],
    words_blacklist: List[str]
) -> None:
    """Обрабатывает вакансию и отправляет отклик, если это возможно."""
    name = vacancy["name"]
    if any(word in name for word in words_blacklist):
        return

    async with account_lock:
        if len(ignored_account_ids) == len(accounts):
            print("Лимит всех аккаунтов исчерпан.")
            return
        
        while account_index[0] in ignored_account_ids:
            account_index[0] = (account_index[0] + 1) % len(accounts)
            if len(ignored_account_ids) == len(accounts):
                print("Лимит всех аккаунтов исчерпан.")
                return
        
        account = accounts[account_index[0]]
        curr_account_id = account_index[0]
        account_index[0] = (account_index[0] + 1) % len(accounts)

    resp = await account.respond_to_vacancy(vacancy["vacancyId"])
    if resp["success"]:
        print(f"Отклик отправлен на вакансию: {name}")
    else:
        error = resp["error"]
        if error == "negotiations-limit-exceeded":
            print(f"Лимит откликов аккаунта {curr_account_id} исчерпан.")
            async with account_lock:
                if curr_account_id not in ignored_account_ids:
                    ignored_account_ids.append(curr_account_id)
        elif error != "unknown":
            print(f"Не удалось откликнуться на вакансию {name}: {error}")

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
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            config = json.load(file)
    except FileNotFoundError:
        print(f"Файл {CONFIG_FILE} не найден.")
        return

    words_blacklist = config["blacklisted_words"]
    request = config["request"]

    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as file:
            accounts_data = json.load(file)
    except FileNotFoundError:
        print(f"Файл {ACCOUNTS_FILE} не найден.")
        return

    accounts = [
        Account(email=account["email"], resume_hash=account["hash"], cookies=account.get("cookies", {}))
        for account in accounts_data
    ]

    ignored_account_ids: List[int] = []
    account_lock = asyncio.Lock()
    account_index = [0]  # Используем список для изменения индекса

    session_headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "X-Static-Version": website_version,
        "X-Xsrftoken": "1",
    }

    async with aiohttp.ClientSession(headers=session_headers) as session:
        last_page = await get_vacancies_pages(session, request)
        for page in range(1, last_page + 1):
            vacancies = await get_vacancies(session, request, page)
            tasks = [
                process_vacancy(vacancy, accounts, ignored_account_ids, account_lock, account_index, words_blacklist)
                for vacancy in vacancies
            ]
            await asyncio.gather(*tasks)
            if len(ignored_account_ids) == len(accounts):
                print("Лимит всех аккаунтов исчерпан.")
                break

if __name__ == "__main__":
    website_version = get_website_version()
    asyncio.run(main())