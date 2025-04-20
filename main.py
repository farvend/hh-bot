import asyncio
import aiohttp
import json
from aiohttp import FormData


class Account:
    def __init__(self, token: str, resume_hash: str):
        self.token = token
        self.resume_hash = resume_hash
        self.cookie_jar = aiohttp.CookieJar()
        # Add the 'hhtoken' cookie
        self.cookie_jar.update_cookies({'hhtoken': self.token})
        self.session = aiohttp.ClientSession(cookie_jar=self.cookie_jar)
    
    async def close(self):
        await self.session.close()
    
    async def response(self, vacancy_id: int):
        url = "https://hh.ru/applicant/vacancy_response/popup"

        # Perform a GET request to obtain the '_xsrf' token
        async with self.session.get("https://hh.ru/", headers={'User-Agent': 'Mozilla/5.0'}) as resp:
            await resp.text()  # Read the response to update cookies

        # Extract '_xsrf' from cookie jar
        xsrf_token = None
        for cookie in self.session.cookie_jar:
            if cookie.key == '_xsrf':
                xsrf_token = cookie.value
                break

        if not xsrf_token:
            print("Failed to retrieve '_xsrf' token")
            return {'success': False, 'error': 'Failed to retrieve xsrf token'}

        payload = {
            'resume_hash': self.resume_hash,
            'vacancy_id': str(vacancy_id),
            'letterRequired': 'false',
            'lux': 'true',
            'ignore_postponed': 'true',
            'mark_applicant_visible_in_vacancy_country': 'false'
        }

        # Use FormData to send multipart/form-data
        form_data = FormData()
        for key, value in payload.items():
            form_data.add_field(key, value)

        headers = {
            'User-Agent': 'Mozilla/5.0',
            'X-hhtmFrom': 'resume',
            'X-Xsrftoken': xsrf_token,
            'Referer': 'https://hh.ru/'
            # Do not set 'Content-Type'; aiohttp handles it with FormData
        }

        async with self.session.post(url, data=form_data, headers=headers) as response:
            text = await response.text()

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                print(f"Invalid JSON response. Status: {response.status}, Text: {text}")
                return {'success': False, 'error': 'Invalid JSON response'}

            if 'error' in data:
                print(f"Error: {data['error']}")
                return {'success': False, 'error': data['error']}

            if data.get('success') == 'true':
                return {'success': True}

            # If none of the above, return an unknown error with the status code.
            print(f"Unknown response. Status: {response.status}, Data: {data}")
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
            print('All accounts have exceeded their limits.')
            return

        while account_index[0] in ignored_account_ids:
            account_index[0] = (account_index[0] + 1) % len(accounts)
            if len(ignored_account_ids) == len(accounts):
                print('All accounts have exceeded their limits.')
                return

        account = accounts[account_index[0]]
        curr_account_id = account_index[0]
        # Rotate to the next account
        account_index[0] = (account_index[0] + 1) % len(accounts)

    # Send response outside of the lock
    resp = await account.response(vacancy['vacancyId'])

    if resp['success']:
        print(f"Responded to vacancy: {name}")
    else:
        if resp['error'] == 'negotiations-limit-exceeded':
            print(f"Account {curr_account_id} exceeded limit.")
            async with account_lock:
                if curr_account_id not in ignored_account_ids:
                    ignored_account_ids.append(curr_account_id)
        else:
            print(f"Failed to respond to vacancy {name} due to error: {resp['error']}")
            

async def main():
    words_blacklist = ['AI', 'ML', 'Data Scientist', 'Data Engineer', 'DevOps', 'Machine Learning',
                       'Data Analyst', 'QA', 'Malware', 'LLM']

    with open('accounts.json', 'r') as f:
        accounts_data = json.load(f)

    accounts = [Account(token=account['token'], resume_hash=account['hash']) for account in accounts_data]

    ignored_account_ids = []
    account_lock = asyncio.Lock()
    account_index = [0]  # Using a list to make account_index mutable

    # Session for vacancy retrieval
    session_headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json',
        'X-Static-Version': '25.16.5.2',
        'X-Xsrftoken': '1',
    }

    async with aiohttp.ClientSession(headers=session_headers) as session:
        last_page = await get_vacancies_pages(session, 'Python')

        for page in range(1, last_page + 1):
            vacancies = await get_vacancies(session, 'Python', page)
            tasks = []

            for vacancy in vacancies:
                task = asyncio.create_task(
                    process_vacancy(vacancy, accounts, ignored_account_ids, account_lock, account_index, words_blacklist)
                )
                tasks.append(task)

            await asyncio.gather(*tasks)

            if len(ignored_account_ids) == len(accounts):
                print('All accounts have exceeded their limits.')
                break

    # Close all account sessions
    await asyncio.gather(*(account.close() for account in accounts))
    

if __name__ == '__main__':
    asyncio.run(main())