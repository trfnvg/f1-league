# Деплой на Timeweb App Platform

## Почему «Server Error» (500)

Чаще всего причина одна из:

1. **DisallowedHost** — хост приложения не в `ALLOWED_HOSTS`.
2. **Нет SECRET_KEY** в переменных окружения.
3. **Запуск через runserver** вместо gunicorn (по умолчанию в Timeweb).
4. **База данных** — нет доступа к SQLite (файловая система только для чтения) или не задан `DATABASE_URL` для PostgreSQL.
5. **Ошибка при импорте** — смотреть логи сборки/запуска в панели Timeweb.

---

## Что настроить в панели Timeweb

### 1. Команда запуска (обязательно)

В настройках приложения укажите **команду запуска** (Run command), а не оставляйте значение по умолчанию.

**Если деплой идёт через Docker (образ из репозитория):**
- Команда по умолчанию берётся из `Dockerfile` → `CMD ["/app/start.sh"]` (миграции + collectstatic + gunicorn). Дополнительно ничего не нужно, если образ собирается из этого репозитория.

**Если сборка без Docker (Buildpack / «Сборка из репозитория»):**
- В поле команды запуска укажите:
  ```bash
  python manage.py migrate --noinput; python manage.py collectstatic --noinput; gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}
  ```
  Либо по шагам в «Сборка»:
  - Сборка: `pip install -r requirements.txt`
  - Запуск: `gunicorn config.wsgi:application --bind 0.0.0.0:8000`

Не используйте `runserver` в проде — он не предназначен для продакшена.

### 2. Переменные окружения

В разделе «Переменные окружения» (Environment) добавьте:

| Переменная | Обязательно | Пример |
|------------|-------------|--------|
| `SECRET_KEY` | Да | Длинная случайная строка (например, сгенерировать: `python -c "import secrets; print(secrets.token_urlsafe(50))"`) |
| `ALLOWED_HOSTS` или `DJANGO_ALLOWED_HOSTS` | Да | Домен приложения Timeweb, например: `your-app-12345.twc1.net` или `*` для любого хоста |
| `DEBUG` | Нет | В проде лучше `False` |
| `DATABASE_URL` | Рекомендуется в проде | На App Platform файловая система часто временная/только для чтения — SQLite может не работать. Создай PostgreSQL в панели Timeweb и подставь строку подключения. |
| `TELEGRAM_BOT_TOKEN` | Для Telegram | Токен от `@BotFather`. Храни только в переменных окружения, не добавляй в Git. |
| `TELEGRAM_BOT_USERNAME` | Нет | Username бота без `@`, например `f1_predictions_bot`. Если не указать, сайт определит его через Telegram API. |
| `TELEGRAM_WORKER_ENABLED` | Нет | `True` по умолчанию. Укажи `False`, если воркер запущен отдельно, а сайт должен только показывать кнопку подключения Telegram. |
| `TELEGRAM_API_BASE_URL` | Только при прокси | URL собственного Cloudflare Worker, если Timeweb не может подключиться к `api.telegram.org`. |
| `TELEGRAM_PROXY_SECRET` | Только при прокси | Общий случайный секрет для защиты Cloudflare Worker. |
| `SITE_URL` | Для кнопки в сообщении | Публичный адрес сайта, например `https://f1.example.com`. |

Важно: в `ALLOWED_HOSTS` должен быть **реальный хост**, который отдаёт Timeweb (вид в адресной строке после деплоя). Иначе Django вернёт 500 (DisallowedHost).

### Telegram-уведомления

После добавления `TELEGRAM_BOT_TOKEN` Docker-запуск из `start.sh` автоматически запускает фоновый процесс:

```bash
python manage.py telegram_bot_worker --interval 60
```

Он получает команды бота и раз в минуту проверяет этапы, до дедлайна которых осталось не более трёх часов. Webhook и отдельный cron для этой реализации не нужны.

Если приложение запускается без Docker, добавь запуск воркера в Run command перед gunicorn:

```bash
python manage.py migrate --noinput; python manage.py collectstatic --noinput; python manage.py telegram_bot_worker --interval 60 & gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}
```

Пользователь подключает Telegram кнопкой в своём профиле. В Telegram также доступны команды `/stop` и `/resume`.

#### Если Timeweb не подключается к Telegram

Не нужен отдельный облачный сервер. Можно использовать бесплатный защищённый
Cloudflare Worker как мост:

1. Создай Worker и вставь код из `deploy/cloudflare-telegram-proxy.js`.
2. Добавь в Worker два зашифрованных секрета:
   `TELEGRAM_BOT_TOKEN` и `PROXY_SECRET`.
3. В Timeweb добавь `TELEGRAM_API_BASE_URL` с адресом Worker и
   `TELEGRAM_PROXY_SECRET` с тем же значением `PROXY_SECRET`.
4. Оставь `TELEGRAM_WORKER_ENABLED=True` только в одном приложении Timeweb и
   перезапусти деплой.

Прокси принимает только `getMe`, `getUpdates` и `sendMessage`, а все запросы
без правильного `PROXY_SECRET` отклоняет.

### 3. Рабочая директория

Убедись, что **корень приложения** — каталог, где лежит `manage.py`. В настройках сборки/запуска обычно указывается «Root directory» или «Working directory». Если репозиторий без подпапок — оставь пустым или `.`.

---

## Как посмотреть реальную ошибку

1. **Логи приложения** в панели Timeweb (App → Логи / Logs) — там будет traceback Python при 500.
2. Временно включи **DEBUG**: переменная `DEBUG=True`. После деплоя открой страницу снова — Django покажет полный traceback на экране. **Не забудь потом вернуть DEBUG=False** и перезадеплоить.

---

## Чек-лист перед деплоем

- [ ] Команда запуска: **gunicorn** (не runserver).
- [ ] В env заданы **SECRET_KEY** и **ALLOWED_HOSTS** (или **DJANGO_ALLOWED_HOSTS**) с твоим доменом/хостом.
- [ ] Если используешь БД Timeweb — задан **DATABASE_URL**.
- [ ] В репозитории в корне есть `manage.py`, `requirements.txt`, папка `config` с `settings.py` и `wsgi.py`.

После правок сделай новый деплой и снова открой сайт. Если ошибка останется — пришли из логов приложения строки с **Traceback** или **Error**.
