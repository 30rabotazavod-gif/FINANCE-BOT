# 💰 Финансовый Telegram Бот

Бот для учёта финансов. Работает на Railway.app — бесплатно, без установки.

## Деплой на Railway (15 минут)

### Шаг 1 — Токен бота
1. Telegram → [@BotFather](https://t.me/BotFather) → `/newbot`
2. Скопировать токен вида `123456789:ABCdef...`

### Шаг 2 — Загрузить на GitHub
1. [github.com](https://github.com) → **"New repository"** → название `finance-bot` → Create
2. **"uploading an existing file"** → перетащить все 5 файлов
3. **"Commit changes"**

### Шаг 3 — Создать проект Railway
1. [railway.app](https://railway.app) → Login with GitHub
2. **"New Project"** → **"Deploy from GitHub repo"** → выбрать `finance-bot`

### Шаг 4 — Добавить PostgreSQL
1. В проекте → **"+ New"** → **"Database"** → **"PostgreSQL"**
2. `DATABASE_URL` Railway передаст автоматически ✅

### Шаг 5 — Добавить токен
1. Нажать на сервис `finance-bot` → вкладка **"Variables"**
2. **"New Variable"**: `BOT_TOKEN` = ваш токен
3. **"Add"**

### Готово! 🎉
Через 1-2 минуты пишите боту `/start` в Telegram.

## Возможности
- 💰 Баланс по всем счетам
- ➕➖ Доходы и расходы по категориям
- 🔄 Переводы между счетами
- 📊 Статистика за день/неделю/месяц/год
- 🆕 Свои категории
