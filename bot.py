import logging
import os
from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
from database import Database

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for ConversationHandler
(
    MAIN_MENU,
    ADD_TRANSACTION_TYPE,
    ADD_TRANSACTION_ACCOUNT,
    ADD_TRANSACTION_AMOUNT,
    ADD_TRANSACTION_CATEGORY,
    ADD_TRANSACTION_NOTE,
    ADD_ACCOUNT_NAME,
    ADD_ACCOUNT_BALANCE,
    ADD_CATEGORY_NAME,
    TRANSFER_FROM,
    TRANSFER_TO,
    TRANSFER_AMOUNT,
    EDIT_ACCOUNT_BALANCE,
) = range(13)

db = Database()

# ─── KEYBOARDS ────────────────────────────────────────────────

def main_keyboard():
    keyboard = [
        [KeyboardButton("💰 Баланс"), KeyboardButton("➕ Доход")],
        [KeyboardButton("➖ Расход"), KeyboardButton("🔄 Перевод")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("⚙️ Настройки")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def accounts_keyboard(accounts, action="select"):
    buttons = []
    for acc in accounts:
        buttons.append([InlineKeyboardButton(
            f"{acc['name']} — {acc['balance']:,.0f} сум",
            callback_data=f"{action}:{acc['id']}"
        )])
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)

def categories_keyboard(categories, tr_type):
    buttons = []
    row = []
    for i, cat in enumerate(categories):
        row.append(InlineKeyboardButton(
            f"{cat['emoji']} {cat['name']}",
            callback_data=f"cat:{cat['id']}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("➕ Новая категория", callback_data="cat:new")])
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)

def stats_period_keyboard():
    buttons = [
        [
            InlineKeyboardButton("Сегодня", callback_data="stats:today"),
            InlineKeyboardButton("Неделя", callback_data="stats:week"),
        ],
        [
            InlineKeyboardButton("Месяц", callback_data="stats:month"),
            InlineKeyboardButton("Год", callback_data="stats:year"),
        ],
        [InlineKeyboardButton("❌ Закрыть", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(buttons)

def settings_keyboard():
    buttons = [
        [InlineKeyboardButton("🏦 Счета", callback_data="settings:accounts")],
        [InlineKeyboardButton("🏷️ Категории расходов", callback_data="settings:categories_expense")],
        [InlineKeyboardButton("🏷️ Категории доходов", callback_data="settings:categories_income")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(buttons)

# ─── HELPERS ──────────────────────────────────────────────────

def format_balance_message(accounts):
    if not accounts:
        return "У вас нет счетов. Добавьте счёт в ⚙️ Настройки."
    
    total = sum(a['balance'] for a in accounts)
    lines = ["💼 <b>Ваши счета:</b>\n"]
    for acc in accounts:
        lines.append(f"  <b>{acc['name']}</b>: {acc['balance']:,.0f} сум")
    lines.append(f"\n<b>Итого: {total:,.0f} сум</b>")
    return "\n".join(lines)

def format_stats_message(stats, period_name, accounts):
    total_income = sum(t['amount'] for t in stats if t['type'] == 'income')
    total_expense = sum(t['amount'] for t in stats if t['type'] == 'expense')
    
    # Group expenses by category
    expense_by_cat = {}
    for t in stats:
        if t['type'] == 'expense':
            key = f"{t['cat_emoji']} {t['cat_name']}" if t['cat_name'] else "📦 Без категории"
            expense_by_cat[key] = expense_by_cat.get(key, 0) + t['amount']
    
    # Group income by category
    income_by_cat = {}
    for t in stats:
        if t['type'] == 'income':
            key = f"{t['cat_emoji']} {t['cat_name']}" if t['cat_name'] else "💵 Без категории"
            income_by_cat[key] = income_by_cat.get(key, 0) + t['amount']
    
    lines = [f"📊 <b>Статистика за {period_name}:</b>\n"]
    
    if total_income > 0:
        lines.append(f"📈 <b>Доходы: {total_income:,.0f} сум</b>")
        for cat, amount in sorted(income_by_cat.items(), key=lambda x: -x[1]):
            pct = (amount / total_income * 100) if total_income else 0
            lines.append(f"   {cat}: {amount:,.0f} сум ({pct:.0f}%)")
        lines.append("")
    
    if total_expense > 0:
        lines.append(f"📉 <b>Расходы: {total_expense:,.0f} сум</b>")
        for cat, amount in sorted(expense_by_cat.items(), key=lambda x: -x[1]):
            pct = (amount / total_expense * 100) if total_expense else 0
            lines.append(f"   {cat}: {amount:,.0f} сум ({pct:.0f}%)")
        lines.append("")
    
    net = total_income - total_expense
    sign = "+" if net >= 0 else ""
    lines.append(f"<b>Баланс: {sign}{net:,.0f} сум</b>")
    
    if not stats:
        lines.append("Нет транзакций за этот период.")
    
    return "\n".join(lines)

# ─── COMMAND HANDLERS ─────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    db.ensure_user(user_id)
    
    await update.message.reply_text(
        f"👋 Привет, <b>{name}</b>!\n\n"
        "Я твой личный финансовый менеджер.\n"
        "Веду учёт доходов, расходов и баланс по счетам.\n\n"
        "Выбери действие:",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )
    return MAIN_MENU

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>Как пользоваться ботом:</b>\n\n"
        "💰 <b>Баланс</b> — текущий баланс по всем счетам\n"
        "➕ <b>Доход</b> — добавить поступление денег\n"
        "➖ <b>Расход</b> — записать трату\n"
        "🔄 <b>Перевод</b> — перевести между счетами\n"
        "📊 <b>Статистика</b> — расходы по категориям\n"
        "⚙️ <b>Настройки</b> — управление счетами и категориями\n\n"
        "Для начала добавьте счёт в ⚙️ Настройки.",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )
    return MAIN_MENU

# ─── BALANCE ──────────────────────────────────────────────────

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    accounts = db.get_accounts(user_id)
    await update.message.reply_text(
        format_balance_message(accounts),
        parse_mode="HTML"
    )
    return MAIN_MENU

# ─── ADD TRANSACTION ──────────────────────────────────────────

async def start_income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['tr_type'] = 'income'
    return await ask_account(update, context)

async def start_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['tr_type'] = 'expense'
    return await ask_account(update, context)

async def ask_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    accounts = db.get_accounts(user_id)
    if not accounts:
        await update.message.reply_text(
            "У вас нет счетов. Сначала добавьте счёт в ⚙️ Настройки."
        )
        return MAIN_MENU
    
    tr_type = context.user_data['tr_type']
    label = "дохода" if tr_type == 'income' else "расхода"
    await update.message.reply_text(
        f"Выберите счёт для записи {label}:",
        reply_markup=accounts_keyboard(accounts, "tr_acc")
    )
    return ADD_TRANSACTION_ACCOUNT

async def transaction_account_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("Отменено.")
        return MAIN_MENU
    
    acc_id = int(query.data.split(":")[1])
    context.user_data['tr_account_id'] = acc_id
    
    tr_type = context.user_data['tr_type']
    label = "дохода" if tr_type == 'income' else "расхода"
    await query.edit_message_text(f"Введите сумму {label} (в сумах):")
    return ADD_TRANSACTION_AMOUNT

async def transaction_amount_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.replace(" ", "").replace(",", "")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Введите корректную сумму, например: 50000")
        return ADD_TRANSACTION_AMOUNT
    
    context.user_data['tr_amount'] = amount
    user_id = update.effective_user.id
    tr_type = context.user_data['tr_type']
    
    categories = db.get_categories(user_id, tr_type)
    await update.message.reply_text(
        "Выберите категорию:",
        reply_markup=categories_keyboard(categories, tr_type)
    )
    return ADD_TRANSACTION_CATEGORY

async def transaction_category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("Отменено.")
        return MAIN_MENU
    
    cat_id = query.data.split(":")[1]
    
    if cat_id == "new":
        await query.edit_message_text("Введите название новой категории:")
        return ADD_CATEGORY_NAME
    
    context.user_data['tr_category_id'] = int(cat_id)
    await query.edit_message_text("Добавьте комментарий (или отправьте /skip чтобы пропустить):")
    return ADD_TRANSACTION_NOTE

async def new_category_in_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("Название не может быть пустым.")
        return ADD_CATEGORY_NAME
    
    user_id = update.effective_user.id
    tr_type = context.user_data['tr_type']
    emoji = "📦" if tr_type == 'expense' else "💵"
    cat_id = db.add_category(user_id, name, emoji, tr_type)
    context.user_data['tr_category_id'] = cat_id
    
    await update.message.reply_text(f"Категория «{name}» создана!\n\nДобавьте комментарий (или /skip):")
    return ADD_TRANSACTION_NOTE

async def transaction_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text if update.message.text != '/skip' else ""
    return await save_transaction(update, context, note)

async def transaction_skip_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await save_transaction(update, context, "")

async def save_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE, note: str):
    user_id = update.effective_user.id
    tr_type = context.user_data['tr_type']
    account_id = context.user_data['tr_account_id']
    amount = context.user_data['tr_amount']
    category_id = context.user_data.get('tr_category_id')
    
    db.add_transaction(user_id, tr_type, account_id, amount, category_id, note)
    
    account = db.get_account(account_id)
    sign = "+" if tr_type == 'income' else "-"
    emoji = "✅📈" if tr_type == 'income' else "✅📉"
    
    await update.message.reply_text(
        f"{emoji} <b>Записано!</b>\n\n"
        f"{'Доход' if tr_type == 'income' else 'Расход'}: <b>{sign}{amount:,.0f} сум</b>\n"
        f"Счёт: {account['name']}\n"
        f"Остаток: <b>{account['balance']:,.0f} сум</b>",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )
    context.user_data.clear()
    return MAIN_MENU

# ─── TRANSFER ─────────────────────────────────────────────────

async def start_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    accounts = db.get_accounts(user_id)
    if len(accounts) < 2:
        await update.message.reply_text("Для перевода нужно минимум 2 счёта.")
        return MAIN_MENU
    
    context.user_data['transfer'] = {}
    await update.message.reply_text(
        "Выберите счёт <b>откуда</b> перевести:",
        parse_mode="HTML",
        reply_markup=accounts_keyboard(accounts, "tfr_from")
    )
    return TRANSFER_FROM

async def transfer_from_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("Отменено.")
        return MAIN_MENU
    
    acc_id = int(query.data.split(":")[1])
    context.user_data['transfer']['from'] = acc_id
    user_id = update.effective_user.id
    accounts = [a for a in db.get_accounts(user_id) if a['id'] != acc_id]
    
    await query.edit_message_text(
        "Выберите счёт <b>куда</b> перевести:",
        parse_mode="HTML",
        reply_markup=accounts_keyboard(accounts, "tfr_to")
    )
    return TRANSFER_TO

async def transfer_to_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("Отменено.")
        return MAIN_MENU
    
    acc_id = int(query.data.split(":")[1])
    context.user_data['transfer']['to'] = acc_id
    await query.edit_message_text("Введите сумму перевода:")
    return TRANSFER_AMOUNT

async def transfer_amount_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.replace(" ", "").replace(",", "")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Введите корректную сумму.")
        return TRANSFER_AMOUNT
    
    user_id = update.effective_user.id
    from_id = context.user_data['transfer']['from']
    to_id = context.user_data['transfer']['to']
    
    success = db.transfer(user_id, from_id, to_id, amount)
    if not success:
        await update.message.reply_text("Недостаточно средств на счёте!")
        return MAIN_MENU
    
    from_acc = db.get_account(from_id)
    to_acc = db.get_account(to_id)
    
    await update.message.reply_text(
        f"🔄 <b>Перевод выполнен!</b>\n\n"
        f"Сумма: <b>{amount:,.0f} сум</b>\n"
        f"{from_acc['name']}: {from_acc['balance']:,.0f} сум\n"
        f"{to_acc['name']}: {to_acc['balance']:,.0f} сум",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )
    context.user_data.clear()
    return MAIN_MENU

# ─── STATISTICS ───────────────────────────────────────────────

async def show_stats_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Выберите период:",
        reply_markup=stats_period_keyboard()
    )
    return MAIN_MENU

async def stats_period_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("Закрыто.")
        return MAIN_MENU
    
    period = query.data.split(":")[1]
    user_id = update.effective_user.id
    
    period_names = {"today": "сегодня", "week": "эту неделю", "month": "этот месяц", "year": "этот год"}
    stats = db.get_stats(user_id, period)
    accounts = db.get_accounts(user_id)
    
    msg = format_stats_message(stats, period_names[period], accounts)
    await query.edit_message_text(msg, parse_mode="HTML")
    return MAIN_MENU

# ─── SETTINGS ─────────────────────────────────────────────────

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚙️ <b>Настройки</b>",
        parse_mode="HTML",
        reply_markup=settings_keyboard()
    )
    return MAIN_MENU

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if query.data == "cancel":
        await query.edit_message_text("Закрыто.")
        return MAIN_MENU
    
    action = query.data.split(":")[1]
    
    if action == "accounts":
        accounts = db.get_accounts(user_id)
        lines = ["🏦 <b>Ваши счета:</b>\n"]
        for a in accounts:
            lines.append(f"  {a['name']}: <b>{a['balance']:,.0f} сум</b>")
        lines.append("\nЧтобы добавить новый счёт, отправьте команду /addaccount")
        await query.edit_message_text("\n".join(lines), parse_mode="HTML")
    
    elif action == "categories_expense":
        cats = db.get_categories(user_id, 'expense')
        lines = ["🏷️ <b>Категории расходов:</b>\n"]
        for c in cats:
            lines.append(f"  {c['emoji']} {c['name']}")
        lines.append("\nДобавить категорию можно при записи расхода.")
        await query.edit_message_text("\n".join(lines), parse_mode="HTML")
    
    elif action == "categories_income":
        cats = db.get_categories(user_id, 'income')
        lines = ["🏷️ <b>Категории доходов:</b>\n"]
        for c in cats:
            lines.append(f"  {c['emoji']} {c['name']}")
        lines.append("\nДобавить категорию можно при записи дохода.")
        await query.edit_message_text("\n".join(lines), parse_mode="HTML")
    
    return MAIN_MENU

async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите название счёта (например: Наличные, Карта UzCard, Payme):")
    return ADD_ACCOUNT_NAME

async def add_account_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("Название не может быть пустым.")
        return ADD_ACCOUNT_NAME
    context.user_data['new_account_name'] = name
    await update.message.reply_text(f"Начальный баланс счёта «{name}» (введите 0 если пустой):")
    return ADD_ACCOUNT_BALANCE

async def add_account_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.replace(" ", "").replace(",", "")
    try:
        balance = float(text)
        if balance < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Введите корректную сумму (0 или больше).")
        return ADD_ACCOUNT_BALANCE
    
    user_id = update.effective_user.id
    name = context.user_data['new_account_name']
    db.add_account(user_id, name, balance)
    
    await update.message.reply_text(
        f"✅ Счёт <b>{name}</b> создан!\nБаланс: {balance:,.0f} сум",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )
    context.user_data.clear()
    return MAIN_MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Отменено.", reply_markup=main_keyboard())
    return MAIN_MENU

# ─── MAIN ─────────────────────────────────────────────────────

def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("Укажите BOT_TOKEN в переменных окружения или в файле .env")
    
    app = Application.builder().token(token).build()
    
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^💰 Баланс$"), show_balance),
            MessageHandler(filters.Regex("^➕ Доход$"), start_income),
            MessageHandler(filters.Regex("^➖ Расход$"), start_expense),
            MessageHandler(filters.Regex("^🔄 Перевод$"), start_transfer),
            MessageHandler(filters.Regex("^📊 Статистика$"), show_stats_menu),
            MessageHandler(filters.Regex("^⚙️ Настройки$"), show_settings),
            CommandHandler("addaccount", add_account_start),
        ],
        states={
            MAIN_MENU: [
                MessageHandler(filters.Regex("^💰 Баланс$"), show_balance),
                MessageHandler(filters.Regex("^➕ Доход$"), start_income),
                MessageHandler(filters.Regex("^➖ Расход$"), start_expense),
                MessageHandler(filters.Regex("^🔄 Перевод$"), start_transfer),
                MessageHandler(filters.Regex("^📊 Статистика$"), show_stats_menu),
                MessageHandler(filters.Regex("^⚙️ Настройки$"), show_settings),
                CommandHandler("addaccount", add_account_start),
                CallbackQueryHandler(stats_period_selected, pattern="^stats:"),
                CallbackQueryHandler(settings_callback, pattern="^settings:"),
                CallbackQueryHandler(settings_callback, pattern="^cancel$"),
            ],
            ADD_TRANSACTION_ACCOUNT: [
                CallbackQueryHandler(transaction_account_selected, pattern="^tr_acc:"),
                CallbackQueryHandler(transaction_account_selected, pattern="^cancel$"),
            ],
            ADD_TRANSACTION_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, transaction_amount_entered),
            ],
            ADD_TRANSACTION_CATEGORY: [
                CallbackQueryHandler(transaction_category_selected, pattern="^cat:"),
            ],
            ADD_CATEGORY_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, new_category_in_transaction),
            ],
            ADD_TRANSACTION_NOTE: [
                CommandHandler("skip", transaction_skip_note),
                MessageHandler(filters.TEXT & ~filters.COMMAND, transaction_note),
            ],
            ADD_ACCOUNT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_name),
            ],
            ADD_ACCOUNT_BALANCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_balance),
            ],
            TRANSFER_FROM: [
                CallbackQueryHandler(transfer_from_selected, pattern="^tfr_from:"),
                CallbackQueryHandler(transfer_from_selected, pattern="^cancel$"),
            ],
            TRANSFER_TO: [
                CallbackQueryHandler(transfer_to_selected, pattern="^tfr_to:"),
                CallbackQueryHandler(transfer_to_selected, pattern="^cancel$"),
            ],
            TRANSFER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_amount_entered),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_cmd))
    
    logger.info("Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
