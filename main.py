import asyncio
import random
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputFile, FSInputFile
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Настройки бота
BOT_TOKEN = str(os.environ.get("TOKEN"))

ADMIN_ID = 5301117772

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)


def get_db_connection():
    return sqlite3.connect('tictactoe.db')


# Инициализация SQLite базы данных
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            rating INTEGER DEFAULT 100,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            draws INTEGER DEFAULT 0,
            registered_at TEXT
        )
    ''')

    # Таблица игровых сессий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_sessions (
            game_id TEXT PRIMARY KEY,
            player1 INTEGER,
            player2 INTEGER,
            is_vs_bot BOOLEAN,
            is_rated BOOLEAN,
            board_state TEXT,
            current_player INTEGER,
            created_at TEXT
        )
    ''')

    # Таблица чатов бота
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_chats (
            chat_id INTEGER PRIMARY KEY,
            chat_type TEXT,
            title TEXT,
            members_count INTEGER,
            added_at TEXT
        )
    ''')

    # Таблица приглашений - обновленная структура
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invites (
            inviter_id INTEGER,
            invite_code TEXT PRIMARY KEY,
            created_at TEXT,
            used BOOLEAN DEFAULT FALSE,
            used_by INTEGER DEFAULT NULL
        )
    ''')

    conn.commit()
    conn.close()


def upgrade_db():
    """Обновляет структуру базы данных если нужно"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Проверяем существование таблицы invites
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='invites'")
        if cursor.fetchone():
            # Проверяем существование колонки 'used'
            cursor.execute("PRAGMA table_info(invites)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'used' not in columns:
                print("Обновляю структуру таблицы invites...")
                # Создаем временную таблицу с новой структурой
                cursor.execute('''
                    CREATE TABLE invites_new (
                        inviter_id INTEGER,
                        invite_code TEXT PRIMARY KEY,
                        created_at TEXT,
                        used BOOLEAN DEFAULT FALSE,
                        used_by INTEGER DEFAULT NULL
                    )
                ''')

                # Копируем данные из старой таблицы если они есть
                try:
                    cursor.execute('''
                        INSERT INTO invites_new (inviter_id, invite_code, created_at)
                        SELECT inviter_id, invite_code, created_at FROM invites
                    ''')
                except Exception as e:
                    print(f"Ошибка при копировании данных: {e}")

                # Удаляем старую таблицу и переименовываем новую
                cursor.execute('DROP TABLE IF EXISTS invites')
                cursor.execute('ALTER TABLE invites_new RENAME TO invites')

                print("Структура таблицы invites успешно обновлена!")
            else:
                print("Таблица invites уже имеет актуальную структуру")
        else:
            print("Таблица invites не существует, будет создана при инициализации")

    except Exception as e:
        print(f"Ошибка при обновлении базы данных: {e}")

    conn.commit()
    conn.close()


# Инициализируем и обновляем базу данных
init_db()
upgrade_db()

# Настройки рейтинга
RATING_CHANGE_BASE = 25
RANKS = {
    1: {"name": "Новичок", "min_rating": 0, "win_multiplier": 1.5, "lose_multiplier": 0.5, "bot_difficulty": 1},
    2: {"name": "Любитель", "min_rating": 100, "win_multiplier": 1.3, "lose_multiplier": 0.7, "bot_difficulty": 2},
    3: {"name": "Игрок", "min_rating": 300, "win_multiplier": 1.1, "lose_multiplier": 0.9, "bot_difficulty": 3},
    4: {"name": "Опытный", "min_rating": 600, "win_multiplier": 1.0, "lose_multiplier": 1.0, "bot_difficulty": 4},
    5: {"name": "Эксперт", "min_rating": 1000, "win_multiplier": 0.9, "lose_multiplier": 1.1, "bot_difficulty": 5},
    6: {"name": "Мастер", "min_rating": 1500, "win_multiplier": 0.8, "lose_multiplier": 1.2, "bot_difficulty": 6},
    7: {"name": "Гроссмейстер", "min_rating": 2100, "win_multiplier": 0.7, "lose_multiplier": 1.3, "bot_difficulty": 7}
}

# Случайные имена для ботов
BOT_NAMES = [
    "AlexPlayer", "GameMaster", "ProGamer", "TicTacPro", "XOXOKing",
    "GridWarrior", "BoardChamp", "MoveMaster", "StrategyPro", "WinSeeker",
    "CellDominator", "LineHunter", "CrossMaster", "ZeroExpert", "GridTactician"
]


class GameStates(StatesGroup):
    waiting_for_opponent = State()
    in_game = State()


class SMSStates(StatesGroup):
    waiting_text = State()
    waiting_photo = State()
    waiting_video = State()
    waiting_gif = State()
    waiting_buttons = State()


class TicTacToeGame:
    def __init__(self, player1: int, player2: int, is_vs_bot: bool = False, is_rated: bool = True):
        self.player1 = player1
        self.player2 = player2
        self.is_vs_bot = is_vs_bot
        self.is_rated = is_rated
        self.board = [[' ' for _ in range(3)] for _ in range(3)]
        self.current_player = player1
        self.symbols = {player1: '❌', player2: '⭕'}
        self.winner = None
        self.moves = 0
        self.message_ids = {}  # Храним ID сообщений для редактирования
        self.bot_name = random.choice(BOT_NAMES) if is_vs_bot else None

    def make_move(self, row: int, col: int, player_id: int) -> bool:
        if self.board[row][col] != ' ' or player_id != self.current_player:
            return False

        self.board[row][col] = self.symbols[player_id]
        self.moves += 1
        self.current_player = self.player2 if self.current_player == self.player1 else self.player1
        self.check_winner()
        return True

    def check_winner(self):
        # Проверка строк
        for row in self.board:
            if row[0] == row[1] == row[2] != ' ':
                self.winner = self.player1 if row[0] == self.symbols[self.player1] else self.player2
                return

        # Проверка столбцов
        for col in range(3):
            if self.board[0][col] == self.board[1][col] == self.board[2][col] != ' ':
                self.winner = self.player1 if self.board[0][col] == self.symbols[self.player1] else self.player2
                return

        # Проверка диагоналей
        if self.board[0][0] == self.board[1][1] == self.board[2][2] != ' ':
            self.winner = self.player1 if self.board[0][0] == self.symbols[self.player1] else self.player2
            return
        if self.board[0][2] == self.board[1][1] == self.board[2][0] != ' ':
            self.winner = self.player1 if self.board[0][2] == self.symbols[self.player1] else self.player2
            return

        # Ничья
        if self.moves == 9:
            self.winner = 'draw'

    def get_board_display(self) -> str:
        board_str = ""
        for i, row in enumerate(self.board):
            row_str = ""
            for j, cell in enumerate(row):
                if cell == ' ':
                    row_str += f"⬜️"
                else:
                    row_str += cell
            board_str += row_str + "\n"
        return board_str

    def get_keyboard(self) -> InlineKeyboardMarkup:
        keyboard = []
        for i in range(3):
            row = []
            for j in range(3):
                if self.board[i][j] == ' ':
                    row.append(InlineKeyboardButton(text="⬜️", callback_data=f"move_{i}_{j}"))
                else:
                    row.append(InlineKeyboardButton(text=self.board[i][j], callback_data="empty"))
            keyboard.append(row)
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    def save_to_db(self, game_id: str):
        conn = get_db_connection()
        cursor = conn.cursor()

        board_state = '|'.join([''.join(row) for row in self.board])

        cursor.execute('''
            INSERT OR REPLACE INTO game_sessions 
            (game_id, player1, player2, is_vs_bot, is_rated, board_state, current_player, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (game_id, self.player1, self.player2, self.is_vs_bot, self.is_rated,
              board_state, self.current_player, datetime.now().isoformat()))

        conn.commit()
        conn.close()


def get_user_rank(rating: int) -> dict:
    for rank_id in sorted(RANKS.keys(), reverse=True):
        if rating >= RANKS[rank_id]["min_rating"]:
            return RANKS[rank_id]
    return RANKS[1]


def calculate_rating_change(winner_rating: int, loser_rating: int, is_draw: bool = False) -> Tuple[int, int]:
    if is_draw:
        return 0, 0

    winner_rank = get_user_rank(winner_rating)
    loser_rank = get_user_rank(loser_rating)

    winner_change = int(RATING_CHANGE_BASE * winner_rank["win_multiplier"])
    loser_change = int(RATING_CHANGE_BASE * loser_rank["lose_multiplier"])

    return winner_change, loser_change


def get_global_ranking() -> List[Tuple[int, str, int]]:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT user_id, username, rating FROM users ORDER BY rating DESC LIMIT 10')
    ranked_users = cursor.fetchall()

    conn.close()
    return ranked_users


def get_user_position(user_id: int) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT user_id, rating FROM users ORDER BY rating DESC')
    ranked_users = cursor.fetchall()

    conn.close()

    for i, (uid, _) in enumerate(ranked_users, 1):
        if uid == user_id:
            return i
    return len(ranked_users) + 1


def get_user_data(user_id: int) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()

    conn.close()

    if user:
        return {
            'user_id': user[0],
            'username': user[1],
            'rating': user[2],
            'games_played': user[3],
            'wins': user[4],
            'losses': user[5],
            'draws': user[6],
            'registered_at': user[7]
        }
    return None


def save_user_data(user_data: dict):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, username, rating, games_played, wins, losses, draws, registered_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_data['user_id'], user_data['username'], user_data['rating'],
        user_data['games_played'], user_data['wins'], user_data['losses'],
        user_data['draws'], user_data['registered_at']
    ))

    conn.commit()
    conn.close()


def save_chat_info(chat_id: int, chat_type: str, title: str = None, members_count: int = 0):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR REPLACE INTO bot_chats 
        (chat_id, chat_type, title, members_count, added_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (chat_id, chat_type, title, members_count, datetime.now().isoformat()))

    conn.commit()
    conn.close()


def get_all_chats():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT chat_id FROM bot_chats')
    chats = [row[0] for row in cursor.fetchall()]

    conn.close()
    return chats


def create_invite(inviter_id: int) -> str:
    conn = get_db_connection()
    cursor = conn.cursor()

    invite_code = f"invite_{inviter_id}_{random.randint(1000, 9999)}"

    cursor.execute('''
        INSERT OR REPLACE INTO invites 
        (inviter_id, invite_code, created_at, used, used_by)
        VALUES (?, ?, ?, ?, ?)
    ''', (inviter_id, invite_code, datetime.now().isoformat(), False, None))

    conn.commit()
    conn.close()
    return invite_code


def get_invite(invite_code: str) -> Optional[Tuple[int, bool, int]]:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT inviter_id, used, used_by FROM invites WHERE invite_code = ?', (invite_code,))
    result = cursor.fetchone()

    conn.close()
    return result if result else None


def mark_invite_used(invite_code: str, used_by: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE invites 
        SET used = TRUE, used_by = ?
        WHERE invite_code = ?
    ''', (used_by, invite_code))

    conn.commit()
    conn.close()


def is_user_in_game(user_id: int) -> bool:
    """Проверяет, находится ли пользователь в активной игре"""
    for game in game_sessions.values():
        if user_id in [game.player1, game.player2]:
            return True
    return False


# Глобальные переменные для матчмейкинга
matchmaking_queue = []
game_sessions = {}
friend_invites = {}


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    # Сохраняем информацию о чате
    if message.chat.type == 'private':
        save_chat_info(user_id, 'private', username)
    else:
        save_chat_info(message.chat.id, message.chat.type, message.chat.title, getattr(message.chat, 'member_count', 0))

    user_data = get_user_data(user_id)
    if not user_data:
        user_data = {
            'user_id': user_id,
            'username': username,
            'rating': 100,
            'games_played': 0,
            'wins': 0,
            'losses': 0,
            'draws': 0,
            'registered_at': datetime.now().isoformat()
        }
        save_user_data(user_data)

    # Проверяем параметры команды start
    args = message.text.split()
    if len(args) > 1:
        if args[1].startswith('invite_'):
            invite_code = args[1]
            invite_data = get_invite(invite_code)

            if invite_data:
                inviter_id, used, used_by = invite_data

                if used:
                    await message.answer("❌ Эта ссылка приглашения уже была использована!")
                    return

                if inviter_id == user_id:
                    await message.answer("❌ Нельзя играть с самим собой!")
                    return

                # Проверяем, не находится ли пользователь уже в игре
                if is_user_in_game(user_id):
                    await message.answer(
                        "❌ Вы уже находитесь в активной игре! Завершите текущую игру перед началом новой.")
                    return

                # Помечаем приглашение как использованное
                mark_invite_used(invite_code, user_id)

                # Создаем игру между пригласившим и принявшим приглашение
                await start_game(inviter_id, user_id, is_rated=False)
                return
            else:
                await message.answer("❌ Неверная или устаревшая ссылка приглашения!")
                return

    # Проверяем, не находится ли пользователь уже в игре
    if is_user_in_game(user_id):
        await message.answer("🎮 Вы уже находитесь в активной игре! Завершите текущую игру перед началом новой.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Найти игру", callback_data="find_game")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🏆 Топ-10", callback_data="top_10")],
        [InlineKeyboardButton(text="👥 Играть с другом", callback_data="play_friend")]
    ])

    await message.answer(
        "🎯 Добро пожаловать в Крестики-Нолики!\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "create_invite")
async def create_invite_handler(callback: CallbackQuery):
    user_id = callback.from_user.id

    # Проверяем, не находится ли пользователь уже в игре
    if is_user_in_game(user_id):
        await callback.answer(
            "❌ Вы уже находитесь в активной игре! Завершите текущую игру перед созданием приглашения.", show_alert=True)
        return

    user_data = get_user_data(user_id)
    bot_username = (await bot.get_me()).username

    invite_code = create_invite(user_id)

    invite_text = (
        f"🎯 {user_data['username']} приглашает вас сыграть в Крестики-Нолики!\n\n"
        f"Чтобы принять вызов, перейдите по ссылке:\n"
        f"https://t.me/{bot_username}?start={invite_code}"
    )

    await callback.message.edit_text(
        invite_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Скопировать ссылку", callback_data=f"copy_{invite_code}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )


@router.callback_query(F.data.startswith("copy_"))
async def copy_invite_link(callback: CallbackQuery):
    invite_code = callback.data.replace("copy_", "")
    bot_username = (await bot.get_me()).username
    invite_link = f"https://t.me/{bot_username}?start={invite_code}"

    await callback.answer(f"Ссылка скопирована: {invite_link}", show_alert=True)


# ОБРАБОТЧИКИ КНОПОК ГЛАВНОГО МЕНЮ
@router.callback_query(F.data == "find_game")
async def find_game_handler(callback: CallbackQuery):
    user_id = callback.from_user.id

    # Проверяем, не находится ли пользователь уже в игре
    if is_user_in_game(user_id):
        await callback.answer("❌ Вы уже находитесь в активной игре! Завершите текущую игру перед поиском новой.",
                              show_alert=True)
        return

    if user_id in matchmaking_queue:
        await callback.answer("⏳ Вы уже в поиске игры!")
        return

    matchmaking_queue.append(user_id)
    await callback.message.edit_text(
        "🔍 Поиск соперника...\n\n"
        "Ищем игрока с похожим рейтингом (5 сек)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить поиск", callback_data="cancel_search")]
        ])
    )

    # Поиск соперника в течение 5 секунд
    await asyncio.sleep(5)

    if user_id not in matchmaking_queue:
        return

    # После 5 секунд ищем любого соперника или бота
    user_data = get_user_data(user_id)
    if not user_data:
        matchmaking_queue.remove(user_id)
        return

    user_rating = user_data['rating']
    opponent_found = False

    for opponent_id in matchmaking_queue:
        if opponent_id != user_id:
            opponent_data = get_user_data(opponent_id)
            if opponent_data:
                opponent_rating = opponent_data['rating']
                rating_diff = abs(user_rating - opponent_rating)
                if rating_diff <= 300:  # Увеличиваем диапазон после 5 секунд
                    matchmaking_queue.remove(user_id)
                    matchmaking_queue.remove(opponent_id)
                    await start_game(user_id, opponent_id, is_rated=True)
                    opponent_found = True
                    break

    if not opponent_found and user_id in matchmaking_queue:
        matchmaking_queue.remove(user_id)
        await start_game_with_bot(user_id, is_rated=True)


@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_data = get_user_data(user_id)

    if not user_data:
        await callback.answer("❌ Сначала зарегистрируйтесь через /start")
        return

    rank = get_user_rank(user_data['rating'])
    position = get_user_position(user_id)

    win_rate = (user_data['wins'] / user_data['games_played'] * 100) if user_data['games_played'] > 0 else 0

    profile_text = (
        f"👤 Профиль игрока\n\n"
        f"📛 Имя: {user_data['username']}\n"
        f"🏅 Звание: {rank['name']}\n"
        f"⭐ Рейтинг: {user_data['rating']}\n"
        f"📊 Позиция в рейтинге: #{position}\n\n"
        f"📈 Статистика:\n"
        f"🎮 Игр сыграно: {user_data['games_played']}\n"
        f"✅ Побед: {user_data['wins']}\n"
        f"❌ Поражений: {user_data['losses']}\n"
        f"🤝 Ничьих: {user_data['draws']}\n"
        f"📊 Win Rate: {win_rate:.1f}%"
    )

    await callback.message.edit_text(
        profile_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )


@router.callback_query(F.data == "top_10")
async def show_top_10(callback: CallbackQuery):
    top_players = get_global_ranking()

    top_text = "🏆 Топ-10 игроков:\n\n"
    for i, (user_id, username, rating) in enumerate(top_players, 1):
        rank_emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        emoji = rank_emoji[i - 1] if i <= 10 else f"{i}."
        top_text += f"{emoji} {username} - {rating}⭐\n"

    await callback.message.edit_text(
        top_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )


@router.callback_query(F.data == "play_friend")
async def play_with_friend(callback: CallbackQuery):
    # Проверяем, не находится ли пользователь уже в игре
    user_id = callback.from_user.id
    if is_user_in_game(user_id):
        await callback.answer(
            "❌ Вы уже находитесь в активной игре! Завершите текущую игру перед созданием приглашения.", show_alert=True)
        return

    await callback.message.edit_text(
        "👥 Чтобы играть с другом:\n\n"
        "1. Нажмите 'Создать приглашение'\n"
        "2. Отправьте полученную ссылку другу\n"
        "3. Когда друг перейдет по ссылке - игра начнется!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Создать приглашение", callback_data="create_invite")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Найти игру", callback_data="find_game")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🏆 Топ-10", callback_data="top_10")],
        [InlineKeyboardButton(text="👥 Играть с другом", callback_data="play_friend")]
    ])

    await callback.message.edit_text(
        "🎯 Главное меню Крестики-Нолики!\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "cancel_search")
async def cancel_search(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id in matchmaking_queue:
        matchmaking_queue.remove(user_id)

    await callback.message.edit_text(
        "❌ Поиск отменен",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )


# ОБРАБОТЧИКИ ИГРЫ
@router.callback_query(F.data.startswith("move_"))
async def process_move(callback: CallbackQuery):
    user_id = callback.from_user.id

    # Находим игру
    game = None
    game_id = None
    for gid, g in game_sessions.items():
        if user_id in [g.player1, g.player2]:
            game = g
            game_id = gid
            break

    if not game:
        await callback.answer("❌ Игра не найдена!")
        return

    if game.current_player != user_id:
        await callback.answer("⏳ Сейчас не ваш ход!")
        return

    # Парсим ход
    _, row, col = callback.data.split('_')
    row, col = int(row), int(col)

    # Делаем ход
    if game.make_move(row, col, user_id):
        game.save_to_db(game_id)

        if game.winner:
            await finish_game(game, game_id)
        else:
            # Обновляем сообщение для обоих игроков
            await update_game_messages(game, game_id, f"Ход сделан!")

            # Ход бота (если игра с ботом)
            if game.is_vs_bot and game.current_player == -1:
                await asyncio.sleep(1)  # Задержка для реалистичности
                await make_bot_move(game, game_id)

    await callback.answer()


async def update_game_messages(game: TicTacToeGame, game_id: str, action_text: str = ""):
    """Обновляет сообщения игры для всех игроков"""
    current_player_name = "Ваш ход"
    if not game.is_vs_bot:
        if game.current_player == game.player1:
            player_data = get_user_data(game.player1)
            current_player_name = f"Ход ❌ ({player_data['username']})"
        else:
            player_data = get_user_data(game.player2)
            current_player_name = f"Ход ⭕ ({player_data['username']})"
    else:
        # Для игры с ботом показываем случайное имя
        if game.current_player == game.player1:
            player_data = get_user_data(game.player1)
            current_player_name = f"Ход ❌ ({player_data['username']})"
        else:
            current_player_name = f"Ход ⭕ ({game.bot_name})"

    board_text = game.get_board_display()

    for player_id in [game.player1, game.player2]:
        if player_id != -1:  # Не бот
            if game.message_ids.get(player_id):
                try:
                    await bot.edit_message_text(
                        chat_id=player_id,
                        message_id=game.message_ids[player_id],
                        text=f"🎮 Игра идет...\n{current_player_name}\n\n{board_text}",
                        reply_markup=game.get_keyboard()
                    )
                except:
                    # Если не удалось редактировать, отправляем новое сообщение
                    msg = await bot.send_message(
                        player_id,
                        f"🎮 Игра идет...\n{current_player_name}\n\n{board_text}",
                        reply_markup=game.get_keyboard()
                    )
                    game.message_ids[player_id] = msg.message_id


async def make_bot_move(game: TicTacToeGame, game_id: str):
    """Ход бота с разной сложностью"""
    user_data = get_user_data(game.player1)
    rank = get_user_rank(user_data['rating'])
    difficulty = rank['bot_difficulty']

    # Умный ИИ в зависимости от сложности
    if difficulty >= 5:
        move = find_best_move(game)
    elif difficulty >= 3:
        if random.random() > 0.3:
            move = find_good_move(game)
        else:
            move = find_random_move(game)
    else:
        move = find_random_move(game)

    if move:
        row, col = move
        game.make_move(row, col, -1)
        game.save_to_db(game_id)

        if game.winner:
            await finish_game(game, game_id)
        else:
            await update_game_messages(game, game_id, "Бот сделал ход")


def find_random_move(game):
    available_moves = []
    for i in range(3):
        for j in range(3):
            if game.board[i][j] == ' ':
                available_moves.append((i, j))
    return random.choice(available_moves) if available_moves else None


def find_good_move(game):
    if game.board[1][1] == ' ':
        return (1, 1)

    corners = [(0, 0), (0, 2), (2, 0), (2, 2)]
    random.shuffle(corners)
    for i, j in corners:
        if game.board[i][j] == ' ':
            return (i, j)

    return find_random_move(game)


def find_best_move(game):
    available_moves = []
    for i in range(3):
        for j in range(3):
            if game.board[i][j] == ' ':
                available_moves.append((i, j))

    # Проверяем выигрышные ходы
    for i, j in available_moves:
        temp_game = TicTacToeGame(game.player1, game.player2, game.is_vs_bot, game.is_rated)
        temp_game.board = [row[:] for row in game.board]
        temp_game.current_player = game.current_player
        temp_game.make_move(i, j, -1)
        if temp_game.winner == -1:
            return (i, j)

    # Блокируем выигрышные ходы противника
    for i, j in available_moves:
        temp_game = TicTacToeGame(game.player1, game.player2, game.is_vs_bot, game.is_rated)
        temp_game.board = [row[:] for row in game.board]
        temp_game.current_player = game.player1
        temp_game.make_move(i, j, game.player1)
        if temp_game.winner == game.player1:
            return (i, j)

    return find_good_move(game)


async def finish_game(game: TicTacToeGame, game_id: str):
    winner_text = ""
    rating_changes = {}

    if game.winner == 'draw':
        winner_text = "🤝 Ничья!"
        # Обновляем статистику
        for player_id in [game.player1, game.player2]:
            if player_id != -1:  # Не бот
                user_data = get_user_data(player_id)
                if user_data:
                    user_data['games_played'] += 1
                    user_data['draws'] += 1
                    save_user_data(user_data)
    else:
        winner_id = game.winner
        loser_id = game.player1 if winner_id == game.player2 else game.player2

        if winner_id != -1:  # Победил не бот
            winner_data = get_user_data(winner_id)
            loser_data = get_user_data(loser_id) if loser_id != -1 else None

            if winner_data:
                if game.is_rated:
                    if loser_id != -1:  # Против реального игрока
                        winner_rating = winner_data['rating']
                        loser_rating = loser_data['rating'] if loser_data else 100
                        win_change, lose_change = calculate_rating_change(winner_rating, loser_rating)

                        # Обновляем рейтинг победителя
                        winner_data['rating'] += win_change
                        winner_data['games_played'] += 1
                        winner_data['wins'] += 1
                        save_user_data(winner_data)

                        rating_changes[winner_id] = win_change

                        # Обновляем рейтинг проигравшего
                        if loser_data:
                            loser_data['rating'] -= lose_change  # ОТНИМАЕМ рейтинг
                            loser_data['games_played'] += 1
                            loser_data['losses'] += 1
                            save_user_data(loser_data)
                            rating_changes[loser_id] = -lose_change
                    else:  # Против бота
                        # За победу над ботом даем меньше рейтинга
                        win_change = int(RATING_CHANGE_BASE * 0.7)
                        winner_data['rating'] += win_change
                        winner_data['games_played'] += 1
                        winner_data['wins'] += 1
                        save_user_data(winner_data)
                        rating_changes[winner_id] = win_change
                else:
                    # Без рейтинга
                    winner_data['games_played'] += 1
                    winner_data['wins'] += 1
                    save_user_data(winner_data)

                # Формируем текст победителя
                if game.is_vs_bot and winner_id != -1:
                    winner_text = f"🎉 Победитель: {winner_data['username']}"
                elif game.is_vs_bot and winner_id == -1:
                    winner_text = f"🎉 Победитель: {game.bot_name}"
                else:
                    winner_name = winner_data['username']
                    rating_change = rating_changes.get(winner_id)
                    winner_text = f"🎉 Победитель: {winner_name}"
            else:
                winner_text = "🎉 Игра завершена!"
        else:
            # Победил бот
            winner_text = f"🎉 Победитель: {game.bot_name}"
            user_data = get_user_data(game.player1)
            if user_data and game.is_rated:
                # При поражении от бота отнимаем рейтинг
                lose_change = int(RATING_CHANGE_BASE * 0.5)
                user_data['rating'] -= lose_change
                user_data['games_played'] += 1
                user_data['losses'] += 1
                save_user_data(user_data)
                rating_changes[game.player1] = -lose_change

    # Отправляем результаты
    for player_id in [game.player1, game.player2]:
        if player_id != -1:  # Не бот
            user_data = get_user_data(player_id)
            if user_data:
                rating_change = rating_changes.get(player_id)
                rating_text = f"\nИзменение рейтинга: {rating_change}⭐" if rating_change else ""

                final_message = (
                    f"🎮 Игра завершена!\n\n"
                    f"{game.get_board_display()}\n"
                    f"{winner_text}{rating_text}\n\n"
                    f"Ваш рейтинг: {user_data['rating']}⭐"
                )

                await bot.send_message(
                    player_id,
                    final_message,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🎮 Новая игра", callback_data="find_game")],
                        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")]
                    ])
                )

    # Удаляем игру
    if game_id in game_sessions:
        del game_sessions[game_id]


# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ИГРЫ
async def start_game(player1: int, player2: int, is_rated: bool = True, chat_id: int = None):
    game_id = f"{player1}_{player2}_{datetime.now().timestamp()}"
    game = TicTacToeGame(player1, player2, is_rated=is_rated)
    game_sessions[game_id] = game

    player1_data = get_user_data(player1)
    player2_data = get_user_data(player2)

    if not player1_data or not player2_data:
        return

    rated_text = " (на рейтинг)" if is_rated else " (без рейтинга)"

    # Отправляем сообщения игрокам и сохраняем ID сообщений
    for player_id in [player1, player2]:
        opponent_data = player2_data if player_id == player1 else player1_data

        text = (
            f"🎮 Игра началась{rated_text}!\n"
            f"Соперник: {opponent_data['username']}\n"
            f"Ваш символ: {game.symbols[player_id]}\n\n"
            f"{game.get_board_display()}"
        )

        msg = await bot.send_message(
            player_id,
            text,
            reply_markup=game.get_keyboard()
        )
        game.message_ids[player_id] = msg.message_id

    game.save_to_db(game_id)


async def start_game_with_bot(player_id: int, is_rated: bool = True, chat_id: int = None):
    game_id = f"{player_id}_bot_{datetime.now().timestamp()}"
    user_data = get_user_data(player_id)

    # Создаем игру с ботом, но не показываем что это бот
    game = TicTacToeGame(player_id, -1, is_vs_bot=True, is_rated=is_rated)
    game_sessions[game_id] = game

    rated_text = " (на рейтинг)" if is_rated else " (без рейтинга)"

    text = (
        f"🎮 Игра началась{rated_text}!\n"
        f"Соперник: {game.bot_name}\n"
        f"Ваш символ: {game.symbols[player_id]}\n\n"
        f"{game.get_board_display()}"
    )

    msg = await bot.send_message(
        player_id,
        text,
        reply_markup=game.get_keyboard()
    )
    game.message_ids[player_id] = msg.message_id

    game.save_to_db(game_id)


# КОМАНДА SMS ДЛЯ АДМИНА и остальные обработчики остаются без изменений...

async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

