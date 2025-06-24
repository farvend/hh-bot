import asyncio
import aiohttp
import json
import re
from typing import Dict, List

async def get_vacancies_data(session: aiohttp.ClientSession, params: str, website_version: str) -> Dict:
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

async def get_vacancies(session: aiohttp.ClientSession, request: str, page: int, experience_list: List[str], website_version: str) -> List[Dict]:
    """Получает список вакансий для указанной страницы."""
    all_vacancies = []
    
    for experience in experience_list:
        params = f"text={request}&salary=&ored_clusters=true&experience={experience}&page={page}"
        data = await get_vacancies_data(session, params, website_version)
        all_vacancies.extend(data["vacancySearchResult"]["vacancies"])
    
    return all_vacancies

async def get_vacancies_pages(session: aiohttp.ClientSession, request: str, experience_list: List[str], website_version: str) -> int:
    """Возвращает максимальное количество страниц с вакансиями среди всех выбранных опытов."""
    max_pages = 0
    
    for experience in experience_list:
        params = f"text={request}&salary=&ored_clusters=true&experience={experience}&page=1"
        data = await get_vacancies_data(session, params, website_version)
        paging = data["vacancySearchResult"]["paging"]
        
        if paging is None:
            current_pages = 1
        else:
            current_pages = data["vacancySearchResult"]["paging"]["lastPage"]["page"]
        
        max_pages = max(max_pages, current_pages)
    
    return max_pages 