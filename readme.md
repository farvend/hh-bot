# Что это такое

Бот для автоматического отклика на вакансии на hh.ru с поддержкой множества аккаунтов и резюме для обхода лимита в 200 откликов на аккаунт. 

**Особенности:**
- Поддержка нескольких аккаунтов с несколькими резюме у каждого
- Разные поисковые запросы для разных резюме
- Автоматическая ротация между аккаунтами
- Работает **без эмуляции браузера** - использует только HTTP-запросы через aiohttp
- Автоматическое сохранение и восстановление cookies
- Обработка ошибок авторизации с запросом новых cookies

По умолчанию ищет вакансии с опытом 1-3 года. Не нравится - правьте код под себя.

# Как запустить

## 1. Установка зависимостей
```bash
pip install aiohttp asyncio json requests
```
Либо установите их любым удобным способом.

## 2. Создание файла accounts.json

Создайте файл `accounts.json` в корне проекта:

```json
[
    {
        "email": "account1@example.com",
        "resumes": [
            {
                "hash": "resume_hash_1",
                "search_criteria": {
                    "query": "Python разработчик",
                    "exclude_words": ["стажер", "практикант", "junior", "интерн"]
                }
            },
            {
                "hash": "resume_hash_2", 
                "search_criteria": {
                    "query": "Backend developer",
                    "exclude_words": ["стартап", "без опыта", "trainee"]
                }
            }
        ]
    },
    {
        "email": "account2@example.com",
        "resumes": [
            {
                "hash": "resume_hash_3",
                "search_criteria": {
                    "query": "Fullstack разработчик",
                    "exclude_words": ["фриланс", "удаленка", "remote"]
                }
            }
        ]
    }
]
```

**Структура:**
- `email` - почта аккаунта (используется для идентификации и сохранения cookies)
- `resumes` - массив резюме для данного аккаунта
  - `hash` - хеш резюме с hh.ru
  - `search_criteria` - критерии поиска для данного резюме
    - `query` - поисковый запрос (что искать на сайте)
    - `exclude_words` - массив слов/фраз для исключения вакансий (необязательное поле)

## 3. Получение данных аккаунта

### Получение hash резюме:
1. Открываем F12 в браузере
2. Переходим на вкладку "Сеть/Network"  
3. Откликаемся на любую вакансию
4. Ищем POST-запрос на `https://hh.ru/applicant/vacancy_response/popup`
5. В параметрах запроса находим `resume_hash` - это и есть наш hash

### Получение cookies:
1. В том же POST-запросе смотрим заголовки
2. Копируем **все** cookies из заголовка Cookie
3. При первом запуске программы она попросит ввести cookies для каждого аккаунта
4. Cookies автоматически сохранятся в папку `cookies/` и будут переиспользоваться

**Важно:** Копируйте cookies целиком, например:
```
_xsrf=abc123; hhtoken=xyz789; other_cookie=value; ...
```

## 4. Запуск

```bash
python main.py
```

При первом запуске программа попросит ввести cookies для каждого аккаунта. В дальнейшем они будут загружаться автоматически.

# Структура файлов

```
├── main.py              # Основной файл программы
├── accounts.json        # Конфигурация аккаунтов и резюме
└── cookies/            # Папка с сохраненными cookies
    ├── account1@example.com.json
    └── account2@example.com.json
```