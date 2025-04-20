import asyncio
import aiohttp
import json
from aiohttp import FormData


class Account:
    def __init__(self, token: str, resume_hash: str):
        self.token = token
        self.resume_hash = resume_hash
        self.cookie_jar = aiohttp.CookieJar()
        # Добавляем cookie 'hhtoken'
        self.cookie_jar.update_cookies({'hhtoken': self.token})
        self.session = aiohttp.ClientSession(cookie_jar=self.cookie_jar)
    
    async def close(self):
        await self.session.close()
    
    async def response(self, vacancy_id: int):
        url = "https://hh.ru/applicant/vacancy_response/popup"

        # Выполняем GET-запрос для получения токена '_xsrf'
        async with self.session.get("https://hh.ru/", headers={'User-Agent': 'Mozilla/5.0'}) as resp:
            await resp.text()  # Читаем ответ для обновления cookie

        # Извлекаем '_xsrf' из cookie
        xsrf_token = None
        for cookie in self.session.cookie_jar:
            if cookie.key == '_xsrf':
                xsrf_token = cookie.value
                break

        if not xsrf_token:
            print("Не удалось получить токен '_xsrf'")
            return {'success': False, 'error': 'Не удалось получить токен xsrf'}

        payload = {
            'resume_hash': self.resume_hash,
            'vacancy_id': str(vacancy_id),
            'letterRequired': 'false',
            'lux': 'true',
            'ignore_postponed': 'true',
            'mark_applicant_visible_in_vacancy_country': 'false'
        }

        # Используем FormData для отправки multipart/form-data
        form_data = FormData()
        for key, value in payload.items():
            form_data.add_field(key, value)

        headers = {
            'User-Agent': 'Mozilla/5.0',
            'X-hhtmFrom': 'resume',
            'X-Xsrftoken': xsrf_token,
            'Referer': 'https://hh.ru/'
            # Не устанавливаем 'Content-Type'; aiohttp обрабатывает это с FormData
        }

        async with self.session.post(url, data=form_data, headers=headers) as response:
            text = await response.text()

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                print(f"Некорректный JSON-ответ. Статус: {response.status}, Текст: {text}")
                return {'success': False, 'error': 'Некорректный JSON-ответ'}

            if 'error' in data:
                print(f"Ошибка: {data['error']}")
                return {'success': False, 'error': data['error']}

            if data.get('success') == 'true':
                return {'success': True}

            # Если ничего из вышеупомянутого не сработало, возвращаем неизвестную ошибку с кодом статуса.
            print(f"Неизвестный ответ. Статус: {response.status}, Данные: {data}")
            return {'success': False, 'error': f"HTTP {response.status}"}

    
async def get_vacancies(session: aiohttp.ClientSession, request: str, page: int):
    url = f"https://hh.ru/search/vacancy?text={request}&salary=&ored_clusters=true&experience=between1And3&page={page}"

    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json',
        'X-Static-Version': '25.16.5.2',
        'X-Xsrftoken': '1',
    }

    async with session.get(url, headers=headers) as response:
        data = await response.json()
        vacancies = data['vacancySearchResult']['vacancies']
        return vacancies


async def get_vacancies_pages(session: aiohttp.ClientSession, request: str):
    url = f"https://hh.ru/search/vacancy?text={request}&salary=&ored_clusters=true&experience=between1And3&page=1"

    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json',
        'X-Static-Version': '25.16.5.2',
        'X-Xsrftoken': '1',
    }

    async with session.get(url, headers=headers) as response:
        data = await response.json()
        last_page = data['vacancySearchResult']['paging']['lastPage']['page']
        return last_page


async def process_vacancy(vacancy, accounts, ignored_account_ids, account_lock, account_index, words_blacklist):
    name = vacancy['name']
    if any(word in name for word in words_blacklist):
        return

    async with account_lock:
        if len(ignored_account_ids) == len(accounts):
            print('Лимит всех аккаунтов исчерпан.')
            return

        while account_index[0] in ignored_account_ids:
            account_index[0] = (account_index[0] + 1) % len(accounts)
            if len(ignored_account_ids) == len(accounts):
                print('Лимит всех аккаунтов исчерпан.')
                return

        account = accounts[account_index[0]]
        curr_account_id = account_index[0]
        # Переходим к следующему аккаунту
        account_index[0] = (account_index[0] + 1) % len(accounts)

    # Отправляем отклик вне блокировки
    resp = await account.response(vacancy['vacancyId'])

    if resp['success']:
        print(f"Отклик отправлен на вакансию: {name}")
    else:
        if resp['error'] == 'negotiations-limit-exceeded':
            print(f"Лимит откликов аккаунта {curr_account_id} исчерпан.")
            async with account_lock:
                if curr_account_id not in ignored_account_ids:
                    ignored_account_ids.append(curr_account_id)
        else:
            print(f"Не удалось откликнуться на вакансию {name} из-за ошибки: {resp['error']}")
            

async def main():
    
    try:
        config = json.loads(open('config.json', 'r').read())
    except FileNotFoundError:
        print('Файл config.json не найден.')
        return
    
    words_blacklist = config['blacklisted_words']
    request = config['request']

    try:
        with open('accounts.json', 'r') as f:
            accounts_data = json.load(f)
    except FileNotFoundError:
        print('Файл accounts.json не найден.')
        return
    accounts = [Account(token=account['token'], resume_hash=account['hash']) for account in accounts_data]

    ignored_account_ids = []
    account_lock = asyncio.Lock()
    account_index = [0]  # Используем список для изменения account_index

    # Сессия для получения вакансий
    session_headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json',
        'X-Static-Version': '25.16.5.2',
        'X-Xsrftoken': '1',
    }

    async with aiohttp.ClientSession(headers=session_headers) as session:
        last_page = await get_vacancies_pages(session, request)

        for page in range(1, last_page + 1):
            vacancies = await get_vacancies(session, request, page)
            tasks = []

            for vacancy in vacancies:
                task = asyncio.create_task(
                    process_vacancy(vacancy, accounts, ignored_account_ids, account_lock, account_index, words_blacklist)
                )
                tasks.append(task)

            await asyncio.gather(*tasks)

            if len(ignored_account_ids) == len(accounts):
                print('Лимит всех аккаунтов исчерпан.')
                break

    # Закрываем все сессии аккаунтов
    await asyncio.gather(*(account.close() for account in accounts))
    

if __name__ == '__main__':
    asyncio.run(main())