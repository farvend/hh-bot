import json
import os
import asyncio
from typing import Dict, List, Optional
from aiohttp import FormData

# Константы
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
        from utils import cookies_to_string, parse_cookies
        import aiohttp
        
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


def parse_cookies(cookie_str: str) -> Dict[str, str]:
    """Парсит строку кук в словарь."""
    return dict(cookie.strip().split("=", 1) for cookie in cookie_str.split(";")) 