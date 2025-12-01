import asyncio
import random
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputFile, FSInputFile
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Настройки бота
BOT_TOKEN = os.environ.get("TOKEN")


ADMIN_ID = 5301117772

# Инициализация бота и диспетчера
bot = Bot(token=str(BOT_TOKEN))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# Реферальная система - константы
REF_REQUIRED_GAMES = 3
REF_REQUIRED_RANK = "Любитель"
REF_FOR_ROULETTE = 10
STATUSES = [
    "Путь", "Рост", "Цель", "Форсаж", "Бросок", "Вершина", "Легенда", "Тактик",
    "Гений", "Стихия", "Ход", "Калькулятор", "Блиц", "Вызов", "Вихрь", "Феникс",
    "Азарт", "Дзен", "Искра", "Гравитация", "Рок", "Крест", "Ноль", "Поле",
    "Пат", "Матч", "Титан", "Воля", "Упорство", "Взлёт"
]
DEFAULT_STATUS = "без статуса"

# Таймаут хода в игре (в секундах)
MOVE_TIMEOUT = 60  # 1 минута


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
            rating INTEGER DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            draws INTEGER DEFAULT 0,
            registered_at TEXT,
            last_game_at TEXT,
            is_blocked BOOLEAN DEFAULT FALSE
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
            created_at TEXT,
            last_move_time TEXT
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

    # Таблица приглашений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invites (
            inviter_id INTEGER,
            invite_code TEXT PRIMARY KEY,
            created_at TEXT,
            used BOOLEAN DEFAULT FALSE,
            used_by INTEGER DEFAULT NULL
        )
    ''')

    # Таблица рассылок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS broadcasts (
            broadcast_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sent_at TEXT,
            success_count INTEGER,
            fail_count INTEGER
        )
    ''')

    # Таблица рефералов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            referrer_id INTEGER,
            referred_id INTEGER,
            games_played INTEGER DEFAULT 0,
            is_completed BOOLEAN DEFAULT FALSE,
            created_at TEXT,
            PRIMARY KEY (referrer_id, referred_id)
        )
    ''')

    # Таблица инвентаря
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            user_id INTEGER,
            item_type TEXT,
            item_name TEXT,
            quantity INTEGER DEFAULT 1,
            obtained_at TEXT,
            PRIMARY KEY (user_id, item_type, item_name)
        )
    ''')

    # Таблица статусов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_statuses (
            user_id INTEGER,
            status_name TEXT,
            is_active BOOLEAN DEFAULT FALSE,
            obtained_at TEXT,
            PRIMARY KEY (user_id, status_name)
        )
    ''')

    conn.commit()
    conn.close()


def upgrade_db():
    """Обновляет структуру базы данных если нужно"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Проверяем существование таблицы users и добавляем новые колонки
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]

            # Добавляем недостающие колонки
            if 'last_game_at' not in columns:
                cursor.execute('ALTER TABLE users ADD COLUMN last_game_at TEXT')
            if 'is_blocked' not in columns:
                cursor.execute('ALTER TABLE users ADD COLUMN is_blocked BOOLEAN DEFAULT FALSE')

        # Проверяем существование таблицы game_sessions и добавляем last_move_time
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='game_sessions'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(game_sessions)")
            columns = [column[1] for column in cursor.fetchall()]
            if 'last_move_time' not in columns:
                cursor.execute('ALTER TABLE game_sessions ADD COLUMN last_move_time TEXT')

        # Создаем таблицу broadcasts если не существует
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS broadcasts (
                broadcast_id INTEGER PRIMARY KEY AUTOINCREMENT,
                sent_at TEXT,
                success_count INTEGER,
                fail_count INTEGER
            )
        ''')

        # Создаем таблицу referrals если не существует
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                referrer_id INTEGER,
                referred_id INTEGER,
                games_played INTEGER DEFAULT 0,
                is_completed BOOLEAN DEFAULT FALSE,
                created_at TEXT,
                PRIMARY KEY (referrer_id, referred_id)
            )
        ''')

        # Создаем таблицу inventory если не существует
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                user_id INTEGER,
                item_type TEXT,
                item_name TEXT,
                quantity INTEGER DEFAULT 1,
                obtained_at TEXT,
                PRIMARY KEY (user_id, item_type, item_name)
            )
        ''')

        # Создаем таблицу user_statuses если не существует
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_statuses (
                user_id INTEGER,
                status_name TEXT,
                is_active BOOLEAN DEFAULT FALSE,
                obtained_at TEXT,
                PRIMARY KEY (user_id, status_name)
            )
        ''')

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


class ReportStates(StatesGroup):
    waiting_report_text = State()


class AdminStates(StatesGroup):
    waiting_username_for_block = State()
    waiting_username_for_unblock = State()
    waiting_stats_period = State()


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
        self.last_move_time = datetime.now()  # Время последнего хода
        self.timeout_task = None  # Задача для таймаута

    def make_move(self, row: int, col: int, player_id: int) -> bool:
        if self.board[row][col] != ' ' or player_id != self.current_player:
            return False

        self.board[row][col] = self.symbols[player_id]
        self.moves += 1
        self.current_player = self.player2 if self.current_player == self.player1 else self.player1
        self.last_move_time = datetime.now()  # Обновляем время последнего хода
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

        # Добавляем кнопку "Сдаться"
        keyboard.append([InlineKeyboardButton(text="🏳️ Сдаться", callback_data="surrender")])

        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    def save_to_db(self, game_id: str):
        conn = get_db_connection()
        cursor = conn.cursor()

        board_state = '|'.join([''.join(row) for row in self.board])

        cursor.execute('''
            INSERT OR REPLACE INTO game_sessions 
            (game_id, player1, player2, is_vs_bot, is_rated, board_state, current_player, created_at, last_move_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (game_id, self.player1, self.player2, self.is_vs_bot, self.is_rated,
              board_state, self.current_player, datetime.now().isoformat(), self.last_move_time.isoformat()))

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

    cursor.execute('SELECT user_id, username, rating FROM users WHERE is_blocked = FALSE ORDER BY rating DESC LIMIT 10')
    ranked_users = cursor.fetchall()

    conn.close()
    return ranked_users


def get_user_position(user_id: int) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT user_id, rating FROM users WHERE is_blocked = FALSE ORDER BY rating DESC')
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
            'registered_at': user[7],
            'last_game_at': user[8],
            'is_blocked': bool(user[9]) if user[9] is not None else False
        }
    return None


def save_user_data(user_data: dict):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, username, rating, games_played, wins, losses, draws, registered_at, last_game_at, is_blocked)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_data['user_id'], user_data['username'], user_data['rating'],
        user_data['games_played'], user_data['wins'], user_data['losses'],
        user_data['draws'], user_data['registered_at'],
        user_data.get('last_game_at'), user_data.get('is_blocked', False)
    ))

    conn.commit()
    conn.close()


def update_last_game_time(user_id: int):
    """Обновляет время последней игры пользователя"""
    user_data = get_user_data(user_id)
    if user_data:
        user_data['last_game_at'] = datetime.now().isoformat()
        save_user_data(user_data)


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


def get_all_users():
    """Получает всех пользователей"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT user_id FROM users WHERE is_blocked = FALSE')
    users = [row[0] for row in cursor.fetchall()]

    conn.close()
    return users


def get_inactive_users(hours: int = 24):
    """Получает пользователей, которые не играли более указанных часов"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()

    cursor.execute('''
        SELECT user_id, username, last_game_at 
        FROM users 
        WHERE is_blocked = FALSE AND (last_game_at IS NULL OR last_game_at < ?)
    ''', (cutoff_time,))

    users = cursor.fetchall()
    conn.close()
    return users


def get_stats(period_hours: int):
    """Получает статистику за указанный период"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cutoff_time = (datetime.now() - timedelta(hours=period_hours)).isoformat()

    # Новые пользователи
    cursor.execute('SELECT COUNT(*) FROM users WHERE registered_at > ? AND is_blocked = FALSE', (cutoff_time,))
    new_users = cursor.fetchone()[0]

    # Количество игр
    cursor.execute('SELECT COUNT(*) FROM game_sessions WHERE created_at > ?', (cutoff_time,))
    games_played = cursor.fetchone()[0]

    # Неактивные пользователи
    cursor.execute('SELECT COUNT(*) FROM users WHERE last_game_at < ? AND is_blocked = FALSE', (cutoff_time,))
    inactive_users = cursor.fetchone()[0]

    # Новые чаты
    cursor.execute('SELECT COUNT(*) FROM bot_chats WHERE added_at > ?', (cutoff_time,))
    new_chats = cursor.fetchone()[0]

    conn.close()

    return {
        'new_users': new_users,
        'games_played': games_played,
        'inactive_users': inactive_users,
        'new_chats': new_chats
    }


def block_user(username: str):
    """Блокирует пользователя по username"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('UPDATE users SET is_blocked = TRUE WHERE username = ?', (username,))
    success = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return success


def unblock_user(username: str):
    """Разблокирует пользователя по username"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('UPDATE users SET is_blocked = FALSE WHERE username = ?', (username,))
    success = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return success


def save_broadcast_stats(success_count: int, fail_count: int):
    """Сохраняет статистику рассылки"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO broadcasts (sent_at, success_count, fail_count)
        VALUES (?, ?, ?)
    ''', (datetime.now().isoformat(), success_count, fail_count))

    conn.commit()
    conn.close()


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


# РЕФЕРАЛЬНАЯ СИСТЕМА - ФУНКЦИИ
def get_referral_data(referrer_id: int, referred_id: int):
    """Получает данные о реферале"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM referrals 
        WHERE referrer_id = ? AND referred_id = ?
    ''', (referrer_id, referred_id))

    result = cursor.fetchone()
    conn.close()

    if result:
        return {
            'referrer_id': result[0],
            'referred_id': result[1],
            'games_played': result[2],
            'is_completed': bool(result[3]),
            'created_at': result[4]
        }
    return None


def create_referral(referrer_id: int, referred_id: int):
    """Создает запись о реферале"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR REPLACE INTO referrals 
        (referrer_id, referred_id, games_played, is_completed, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (referrer_id, referred_id, 0, False, datetime.now().isoformat()))

    conn.commit()
    conn.close()


def update_referral_games(referrer_id: int, referred_id: int):
    """Обновляет количество сыгранных игр рефералом"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE referrals 
        SET games_played = games_played + 1 
        WHERE referrer_id = ? AND referred_id = ?
    ''', (referrer_id, referred_id))

    conn.commit()
    conn.close()


def complete_referral(referrer_id: int, referred_id: int):
    """Отмечает реферала как завершенного"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE referrals 
        SET is_completed = TRUE 
        WHERE referrer_id = ? AND referred_id = ?
    ''', (referrer_id, referred_id))

    conn.commit()
    conn.close()


def get_completed_referrals_count(referrer_id: int) -> int:
    """Получает количество завершенных рефералов"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT COUNT(*) FROM referrals 
        WHERE referrer_id = ? AND is_completed = TRUE
    ''', (referrer_id,))

    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_pending_referrals_count(referrer_id: int) -> int:
    """Получает количество незавершенных рефералов"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT COUNT(*) FROM referrals 
        WHERE referrer_id = ? AND is_completed = FALSE
    ''', (referrer_id,))

    count = cursor.fetchone()[0]
    conn.close()
    return count


def add_inventory_item(user_id: int, item_type: str, item_name: str):
    """Добавляет предмет в инвентарь"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR REPLACE INTO inventory 
        (user_id, item_type, item_name, quantity, obtained_at)
        VALUES (?, ?, ?, COALESCE((SELECT quantity FROM inventory WHERE user_id = ? AND item_type = ? AND item_name = ?), 0) + 1, ?)
    ''', (user_id, item_type, item_name, user_id, item_type, item_name, datetime.now().isoformat()))

    conn.commit()
    conn.close()


def get_inventory(user_id: int):
    """Получает инвентарь пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT item_type, item_name, quantity FROM inventory 
        WHERE user_id = ? ORDER BY item_type, item_name
    ''', (user_id,))

    items = cursor.fetchall()
    conn.close()
    return items


def add_user_status(user_id: int, status_name: str):
    """Добавляет статус пользователю"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR REPLACE INTO user_statuses 
        (user_id, status_name, is_active, obtained_at)
        VALUES (?, ?, ?, ?)
    ''', (user_id, status_name, False, datetime.now().isoformat()))

    conn.commit()
    conn.close()


def get_user_statuses(user_id: int):
    """Получает все статусы пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT status_name, is_active FROM user_statuses 
        WHERE user_id = ? ORDER BY obtained_at
    ''', (user_id,))

    statuses = cursor.fetchall()
    conn.close()
    return statuses


def set_active_status(user_id: int, status_name: str):
    """Устанавливает активный статус"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Сначала сбрасываем все статусы
    cursor.execute('''
        UPDATE user_statuses 
        SET is_active = FALSE 
        WHERE user_id = ?
    ''', (user_id,))

    # Устанавливаем выбранный статус как активный
    cursor.execute('''
        UPDATE user_statuses 
        SET is_active = TRUE 
        WHERE user_id = ? AND status_name = ?
    ''', (user_id, status_name))

    conn.commit()
    conn.close()


def get_active_status(user_id: int):
    """Получает активный статус пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT status_name FROM user_statuses 
        WHERE user_id = ? AND is_active = TRUE
    ''', (user_id,))

    result = cursor.fetchone()
    conn.close()
    return result[0] if result else DEFAULT_STATUS


# Глобальные переменные для матчмейкинга
matchmaking_queue = []
game_sessions = {}
friend_invites = {}
move_timeout_tasks = {}  # Задачи для отслеживания таймаута ходов


async def check_move_timeout(game_id: str):
    """Проверяет таймаут хода в игре"""
    await asyncio.sleep(MOVE_TIMEOUT)  # Ждем 1 минуту

    if game_id not in game_sessions:
        return

    game = game_sessions[game_id]

    # Проверяем, сколько времени прошло с последнего хода
    time_since_last_move = (datetime.now() - game.last_move_time).total_seconds()

    if time_since_last_move >= MOVE_TIMEOUT:
        # Таймаут! Игрок проигрывает
        await process_move_timeout(game, game_id)


async def process_move_timeout(game: TicTacToeGame, game_id: str):
    """Обрабатывает таймаут хода"""
    if game.winner:
        return  # Игра уже завершена

    timeout_player = game.current_player
    winner_id = game.player1 if timeout_player == game.player2 else game.player2

    # Обновляем статистику
    winner_data = get_user_data(winner_id)
    loser_data = get_user_data(timeout_player)

    if game.is_rated and winner_data and loser_data:
        # Даем победителю рейтинг
        win_change = int(RATING_CHANGE_BASE * 0.5)  # 50% от стандартной победы
        winner_data['rating'] += win_change
        winner_data['games_played'] += 1
        winner_data['wins'] += 1
        save_user_data(winner_data)

        # Отнимаем рейтинг у проигравшего по таймауту
        lose_change = int(RATING_CHANGE_BASE * 1.0)  # 100% штраф за таймаут
        loser_data['rating'] -= lose_change
        loser_data['games_played'] += 1
        loser_data['losses'] += 1
        save_user_data(loser_data)

        # Обновляем время последней игры
        update_last_game_time(winner_id)
        update_last_game_time(timeout_player)

        # Отправляем сообщения игрокам
        for player_id in [game.player1, game.player2]:
            if player_id != -1:  # Не бот
                user_data = get_user_data(player_id)
                if user_data:
                    if player_id == winner_id:
                        message_text = (
                            f"⏰ Игра завершена по таймауту!\n\n"
                            f"Противник не сделал ход вовремя!\n\n"
                            f"🏆 Вы победили!\n"
                            f"Ваш рейтинг: {user_data['rating']}⭐"
                        )
                    else:
                        message_text = (
                            f"⏰ Игра завершена по таймауту!\n\n"
                            f"Вы не сделали ход вовремя! ⏰\n\n"
                            f"📉 Изменение рейтинга: -{lose_change}⭐\n"
                            f"Ваш рейтинг: {user_data['rating']}⭐"
                        )

                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🎮 Новая игра", callback_data="find_game")],
                        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
                        [InlineKeyboardButton(text="📋 Меню", callback_data="back_to_main")]
                    ])

                    await bot.send_message(
                        player_id,
                        message_text,
                        reply_markup=keyboard
                    )
    else:
        # Без рейтинга
        if winner_data:
            winner_data['games_played'] += 1
            winner_data['wins'] += 1
            save_user_data(winner_data)
        if loser_data:
            loser_data['games_played'] += 1
            loser_data['losses'] += 1
            save_user_data(loser_data)

        # Обновляем время последней игры
        update_last_game_time(winner_id)
        update_last_game_time(timeout_player)

        # Отправляем сообщения
        for player_id in [game.player1, game.player2]:
            if player_id != -1:
                if player_id == winner_id:
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🎮 Новая игра", callback_data="find_game")],
                        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
                        [InlineKeyboardButton(text="📋 Меню", callback_data="back_to_main")]
                    ])
                    await bot.send_message(player_id, "⏰ Противник не сделал ход вовремя! Вы победили! 🏆",
                                           reply_markup=keyboard)
                else:
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🎮 Новая игра", callback_data="find_game")],
                        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
                        [InlineKeyboardButton(text="📋 Меню", callback_data="back_to_main")]
                    ])
                    await bot.send_message(player_id, "⏰ Вы не сделали ход вовремя! Вы проиграли! ⏰",
                                           reply_markup=keyboard)

    # Удаляем игру
    if game_id in game_sessions:
        if game_id in move_timeout_tasks:
            move_timeout_tasks[game_id].cancel()
            del move_timeout_tasks[game_id]
        del game_sessions[game_id]


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    # Проверяем блокировку
    user_data = get_user_data(user_id)
    if user_data and user_data.get('is_blocked'):
        await message.answer("❌ Вы заблокированы и не можете использовать бота.")
        return

    # Сохраняем информацию о чате
    if message.chat.type == 'private':
        save_chat_info(user_id, 'private', username)
    else:
        save_chat_info(message.chat.id, message.chat.type, message.chat.title, getattr(message.chat, 'member_count', 0))

    # Проверяем, новый ли это пользователь
    is_new_user = False
    if not user_data:
        is_new_user = True
        user_data = {
            'user_id': user_id,
            'username': username,
            'rating': 100,
            'games_played': 0,
            'wins': 0,
            'losses': 0,
            'draws': 0,
            'registered_at': datetime.now().isoformat(),
            'last_game_at': None,
            'is_blocked': False
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
        elif args[1].startswith('ref_'):
            # Обработка реферальной ссылки
            referrer_id = int(args[1].replace('ref_', ''))

            if referrer_id == user_id:
                await message.answer("❌ Нельзя использовать собственную реферальную ссылку!")
                return

            # Проверяем, является ли пользователь новым
            if not is_new_user:
                await message.answer(
                    "❌ Реферальная ссылка работает только для новых пользователей!\n"
                    "Вы уже зарегистрированы в боте ранее."
                )
                return

            # Создаем запись о реферале
            create_referral(referrer_id, user_id)

            # Отправляем уведомление рефереру
            try:
                referrer_data = get_user_data(referrer_id)
                await bot.send_message(
                    referrer_id,
                    f"🎉 У вас новый реферал!\n\n"
                    f"👤 Пользователь: @{username}\n"
                    f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                    f"Теперь ему нужно сыграть {REF_REQUIRED_GAMES} игры и достичь звания '{REF_REQUIRED_RANK}' "
                    f"чтобы реферал засчитался."
                )
            except Exception as e:
                print(f"Ошибка отправки уведомления рефереру: {e}")

            await message.answer(
                "🎉 Вы присоединились по реферальной ссылке! "
                f"Теперь вам нужно сыграть {REF_REQUIRED_GAMES} игры и достичь звания '{REF_REQUIRED_RANK}' "
                "чтобы реферал засчитался."
            )

    # Проверяем, не находится ли пользователь уже в игре
    if is_user_in_game(user_id):
        await message.answer("🎮 Вы уже находитесь в активной игре! Завершите текущую игру перед началом новой.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Найти игру", callback_data="find_game")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🏆 Топ-10", callback_data="top_10")],
        [InlineKeyboardButton(text="👥 Играть с другом", callback_data="play_friend")],
        [InlineKeyboardButton(text="🎁 Реферальная программа", callback_data="ref_program")]
    ])

    await message.answer(
        "🎯 Добро пожаловать в Крестики-Нолики!\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )


@router.message(Command("ref"))
async def cmd_ref(message: Message):
    """Реферальная программа"""
    user_id = message.from_user.id
    bot_username = (await bot.get_me()).username

    completed_refs = get_completed_referrals_count(user_id)
    pending_refs = get_pending_referrals_count(user_id)

    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    ref_text = (
        "🎁 Реферальная программа\n\n"
        "💼 Механика:\n"
        "• Дайте другу вашу реферальную ссылку\n"
        "• Друг должен сыграть 3 любые игры (с другом или ботом)\n"
        "• Друг должен достичь звания 'Любитель' (100+ рейтинга)\n"
        "• После этого реферал засчитывается\n\n"
        f"✅ Завершенных рефералов: {completed_refs}\n"
        f"⏳ Ожидающих завершения: {pending_refs}\n"
        f"🎰 Доступно прокруток рулетки: {completed_refs // REF_FOR_ROULETTE}\n\n"
        f"🔗 Ваша реферальная ссылка:\n{ref_link}\n\n"
        f"За каждые {REF_FOR_ROULETTE} рефералов вы получаете прокрутку рулетки!"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Крутить рулетку", callback_data="roulette")],
        [InlineKeyboardButton(text="ℹ️ Посмотреть призы", callback_data="view_prizes")],
        [InlineKeyboardButton(text="🔗 Скопировать ссылку", callback_data=f"copy_ref_{user_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

    await message.answer(ref_text, reply_markup=keyboard)


@router.callback_query(F.data == "ref_program")
async def ref_program_handler(callback: CallbackQuery):
    """Обработчик кнопки реферальной программы"""
    await cmd_ref(callback.message)


@router.callback_query(F.data == "view_prizes")
async def view_prizes_handler(callback: CallbackQuery):
    """Показывает информацию о призах"""
    await cmd_rouletteprize(callback.message)


@router.message(Command("rouletteprize"))
async def cmd_rouletteprize(message: Message):
    """Информация о призах в рулетке"""
    prize_text = (
        "🎰 Призы рулетки и шансы выпадения:\n\n"
        "🎁 NFT подарок - 0.1%\n"
        "   • Уникальные коллекционные предметы\n"
        "   • Высокая ценность\n\n"
        "🎁 Обычный подарок - 10%\n"
        "   • Полезные бонусы для игры\n"
        "   • Разные виды подарков\n\n"
        "🧸 Мишка - 5%\n"
        "   • Милый плюшевый мишка\n"
        "   • Добавляет уют в коллекцию\n\n"
        "❤️ Сердечко - 5%\n"
        "   • Символ любви и удачи\n"
        "   • Приносит хорошее настроение\n\n"
        "😞 Ничего - 30%\n"
        "   • Увы, в этот раз не повезло\n"
        "   • Попробуйте еще раз!\n\n"
        "✨ Статус - 49.9%\n"
        "   • Один из 30 уникальных статусов\n"
        "   • Показывается в вашем профиле\n"
        "   • Коллекционируйте все статусы!\n\n"
        "📊 Шансы указаны на одну прокрутку\n"
        "🎯 Качество призов повышается с количеством рефералов!"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Крутить рулетку", callback_data="roulette")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="ref_program")]
    ])

    if isinstance(message, Message):
        await message.answer(prize_text, reply_markup=keyboard)
    else:
        await message.edit_text(prize_text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("copy_ref_"))
async def copy_ref_link(callback: CallbackQuery):
    """Копирование реферальной ссылки"""
    user_id = int(callback.data.replace("copy_ref_", ""))
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    await callback.answer(f"Реферальная ссылка скопирована: {ref_link}", show_alert=True)


@router.callback_query(F.data == "roulette")
async def roulette_handler(callback: CallbackQuery):
    """Обработчик рулетки"""
    user_id = callback.from_user.id

    if callback.message.chat.type != 'private':
        await callback.answer("❌ Рулетка доступна только в личных сообщениях с ботом!", show_alert=True)
        return

    completed_refs = get_completed_referrals_count(user_id)
    available_spins = completed_refs // REF_FOR_ROULETTE

    if available_spins <= 0:
        await callback.answer(
            f"❌ У вас нет доступных прокруток! Нужно {REF_FOR_ROULETTE} рефералов для одной прокрутки.",
            show_alert=True
        )
        return

    # Показываем информацию о рулетке
    roulette_info = (
        "🎰 Рулетка призов\n\n"
        "🎲 Шансы выпадения:\n"
        "• NFT подарок - 0.1%\n"
        "• Обычный подарок - 10%\n"
        "• Мишка - 5%\n"
        "• Сердечко - 5%\n"
        "• Ничего - 30%\n"
        "• Статус - 49.9%\n\n"
        f"🔄 Доступно прокруток: {available_spins}"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Крутить рулетку!", callback_data="spin_roulette")],
        [InlineKeyboardButton(text="ℹ️ Посмотреть призы", callback_data="view_prizes")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="ref_program")]
    ])

    await callback.message.edit_text(roulette_info, reply_markup=keyboard)


@router.callback_query(F.data == "spin_roulette")
async def spin_roulette_handler(callback: CallbackQuery):
    """Прокрутка рулетки"""
    user_id = callback.from_user.id

    completed_refs = get_completed_referrals_count(user_id)
    available_spins = completed_refs // REF_FOR_ROULETTE

    if available_spins <= 0:
        await callback.answer("❌ Нет доступных прокруток!", show_alert=True)
        return

    # Спин рулетки
    spin_result = spin_roulette()

    # Добавляем приз в инвентарь
    if spin_result['type'] != 'nothing':
        add_inventory_item(user_id, spin_result['type'], spin_result['name'])

        # Отправляем уведомление админу о выигрыше подарка
        try:
            user_data = get_user_data(user_id)
            gift_text = (
                f"🎁 ПОЛУЧЕН ПОДАРОК!\n\n"
                f"👤 Пользователь: @{user_data['username']} (ID: {user_id})\n"
                f"🏆 Выиграл: {spin_result['name']}\n"
                f"📦 Тип: {spin_result['type']}\n"
                f"🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"🎮 Игр сыграно: {user_data['games_played']}\n"
                f"⭐ Рейтинг: {user_data['rating']}"
            )
            await bot.send_message(ADMIN_ID, gift_text)
        except Exception as e:
            print(f"Ошибка отправки уведомления о подарке: {e}")

    # Уменьшаем количество доступных прокруток
    # Не обновляем базу данных здесь, т.к. это демонстрационная логика
    # В реальном боте нужно было бы обновить счетчик прокруток

    result_text = (
        f"🎰 Результат прокрутки:\n\n"
        f"🏆 Вы выиграли: {spin_result['name']}!\n"
        f"📦 Тип: {spin_result['type']}\n\n"
    )

    if spin_result['type'] == 'status':
        result_text += "✨ Новый статус добавлен в вашу коллекцию! Используйте /mystatus чтобы посмотреть."
    elif spin_result['type'] != 'nothing':
        result_text += "🎁 Предмет добавлен в инвентарь!"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Крутить еще раз", callback_data="spin_roulette")],
        [InlineKeyboardButton(text="📦 Мой инвентарь", callback_data="my_inventory")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="ref_program")]
    ])

    await callback.message.edit_text(result_text, reply_markup=keyboard)


def spin_roulette():
    """Логика прокрутки рулетки"""
    rand = random.random() * 100

    if rand < 0.1:  # 0.1%
        return {'type': 'nft', 'name': 'NFT подарок'}
    elif rand < 10.1:  # 10%
        return {'type': 'gift', 'name': 'Обычный подарок'}
    elif rand < 15.1:  # 5%
        return {'type': 'gift', 'name': 'Мишка'}
    elif rand < 20.1:  # 5%
        return {'type': 'gift', 'name': 'Сердечко'}
    elif rand < 50.1:  # 30%
        return {'type': 'nothing', 'name': 'Ничего'}
    else:  # 49.9%
        status = random.choice(STATUSES)
        return {'type': 'status', 'name': status}


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Показывает список команд бота"""
    help_text = (
        "🎮 Крестики-Нолики - Список команд\n\n"
        "📋 Основные команды:\n"
        "/start - Начать игру, главное меню\n"
        "/help - Показать это сообщение\n"
        "/profile - Ваш профиль\n"
        "/top - Топ-10 игроков\n"
        "/ref - Реферальная программа\n"
        "/status - Список всех статусов\n"
        "/mystatus - Ваши статусы\n"
        "/inventory - Ваш инвентарь\n"
        "/report - Отправить отчет администратору\n\n"
        "🎮 Игровые команды:\n"
        "• Просто нажмите 'Найти игру' в меню\n"
        "• Или 'Играть с другом' для игры с друзьями\n\n"
        "🎁 Дополнительно:\n"
        "/rouletteprize - Информация о призах рулетки\n\n"

    )

    await message.answer(help_text)


@router.message(Command("status"))
async def cmd_status(message: Message):
    """Показывает все возможные статусы"""
    status_text = "📋 Все возможные статусы:\n\n"

    for i, status in enumerate(STATUSES, 1):
        status_text += f"{i}. {status}\n"

    status_text += f"\nИспользуйте /mystatus чтобы посмотреть ваши статусы"

    await message.answer(status_text)


@router.message(Command("mystatus"))
async def cmd_mystatus(message: Message):
    """Показывает статусы пользователя"""
    user_id = message.from_user.id
    user_statuses = get_user_statuses(user_id)
    active_status = get_active_status(user_id)

    if not user_statuses:
        status_text = f"📊 Ваши статусы:\n\n• {DEFAULT_STATUS}\n\nУ вас пока нет статусов. Получите их через рулетку!"
    else:
        status_text = f"📊 Ваши статусы:\n\n"
        status_text += f"🎯 Активный статус: {active_status}\n\n"
        status_text += "📜 Ваша коллекция:\n"

        for i, (status_name, is_active) in enumerate(user_statuses, 1):
            emoji = "⭐" if is_active else "◯"
            status_text += f"{i}. {emoji} {status_name}\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Сменить статус", callback_data="change_status")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

    await message.answer(status_text, reply_markup=keyboard)


@router.callback_query(F.data == "change_status")
async def change_status_handler(callback: CallbackQuery):
    """Смена статуса"""
    user_id = callback.from_user.id
    user_statuses = get_user_statuses(user_id)

    if not user_statuses:
        await callback.answer("❌ У вас нет статусов для выбора!", show_alert=True)
        return

    # Создаем клавиатуру с номерами статусов
    keyboard_buttons = []
    row = []
    for i, (status_name, is_active) in enumerate(user_statuses, 1):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"set_status_{i}"))
        if i % 5 == 0:  # 5 кнопок в ряду
            keyboard_buttons.append(row)
            row = []
    if row:
        keyboard_buttons.append(row)

    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="mystatus_back")])

    status_list = "\n".join([f"{i}. {status_name}" for i, (status_name, _) in enumerate(user_statuses, 1)])

    await callback.message.edit_text(
        f"🔄 Выберите статус (введите номер):\n\n{status_list}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    )


@router.callback_query(F.data.startswith("set_status_"))
async def set_status_handler(callback: CallbackQuery):
    """Установка статуса по номеру"""
    user_id = callback.from_user.id
    status_num = int(callback.data.replace("set_status_", "")) - 1

    user_statuses = get_user_statuses(user_id)

    if 0 <= status_num < len(user_statuses):
        status_name = user_statuses[status_num][0]
        set_active_status(user_id, status_name)

        await callback.answer(f"✅ Статус изменен на: {status_name}", show_alert=True)
        await cmd_mystatus(callback.message)
    else:
        await callback.answer("❌ Неверный номер статуса!", show_alert=True)


@router.callback_query(F.data == "mystatus_back")
async def mystatus_back_handler(callback: CallbackQuery):
    """Назад к просмотру статусов"""
    await cmd_mystatus(callback.message)


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Установка статуса по номеру"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /stats <номер_статуса>")
        return

    try:
        status_num = int(args[1]) - 1
        user_id = message.from_user.id
        user_statuses = get_user_statuses(user_id)

        if not user_statuses:
            await message.answer("❌ У вас нет статусов!")
            return

        if 0 <= status_num < len(user_statuses):
            status_name = user_statuses[status_num][0]
            set_active_status(user_id, status_name)
            await message.answer(f"✅ Статус изменен на: {status_name}")
        else:
            await message.answer("❌ Неверный номер статуса!")

    except ValueError:
        await message.answer("❌ Номер статуса должен быть числом!")


@router.message(Command("report"))
async def cmd_report(message: Message, state: FSMContext):
    """Отправка отчета администратору"""
    user_id = message.from_user.id
    user_data = get_user_data(user_id)

    if not user_data:
        await message.answer("❌ Сначала зарегистрируйтесь через /start")
        return

    await message.answer(
        "📝 Отправьте текст отчета:\n\n"
        "Опишите вашу проблему, предложение или сообщение для администратора."
    )
    await state.set_state(ReportStates.waiting_report_text)


@router.message(ReportStates.waiting_report_text)
async def process_report(message: Message, state: FSMContext):
    """Обработка текста отчета"""
    user_id = message.from_user.id
    user_data = get_user_data(user_id)

    if not user_data:
        await message.answer("❌ Сначала зарегистрируйтесь через /start")
        await state.clear()
        return

    # Отправляем отчет админу
    report_text = (
        f"📨 НОВЫЙ ОТЧЕТ\n\n"
        f"👤 От: @{user_data['username']} (ID: {user_id})\n"
        f"🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"📝 Текст:\n{message.text}\n\n"
        f"🎮 Игр сыграно: {user_data['games_played']}\n"
        f"⭐ Рейтинг: {user_data['rating']}"
    )

    try:
        await bot.send_message(ADMIN_ID, report_text)
        await message.answer("✅ Ваш отчет отправлен администратору!")
    except Exception as e:
        await message.answer("❌ Ошибка отправки отчета. Попробуйте позже.")
        print(f"Ошибка отправки отчета: {e}")

    await state.clear()


@router.callback_query(F.data == "my_inventory")
async def my_inventory_handler(callback: CallbackQuery):
    """Показывает инвентарь пользователя"""
    user_id = callback.from_user.id
    inventory = get_inventory(user_id)

    if not inventory:
        inventory_text = "🎒 Ваш инвентарь пуст.\n\nПолучите предметы через рулетку!"
    else:
        inventory_text = "🎒 Ваш инвентарь:\n\n"

        # Группируем предметы по типам
        items_by_type = {}
        for item_type, item_name, quantity in inventory:
            if item_type not in items_by_type:
                items_by_type[item_type] = []
            items_by_type[item_type].append((item_name, quantity))

        for item_type, items in items_by_type.items():
            inventory_text += f"📦 {item_type.upper()}:\n"
            for item_name, quantity in items:
                inventory_text += f"  • {item_name} ×{quantity}\n"
            inventory_text += "\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Крутить рулетку", callback_data="roulette")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="ref_program")]
    ])

    await callback.message.edit_text(inventory_text, reply_markup=keyboard)


@router.message(Command("inventory"))
async def cmd_inventory(message: Message):
    """Показывает инвентарь через команду"""
    user_id = message.from_user.id
    inventory = get_inventory(user_id)

    if not inventory:
        inventory_text = "🎒 Ваш инвентарь пуст.\n\nПолучите предметы через рулетку!"
    else:
        inventory_text = "🎒 Ваш инвентарь:\n\n"

        # Группируем предметы по типам
        items_by_type = {}
        for item_type, item_name, quantity in inventory:
            if item_type not in items_by_type:
                items_by_type[item_type] = []
            items_by_type[item_type].append((item_name, quantity))

        for item_type, items in items_by_type.items():
            inventory_text += f"📦 {item_type.upper()}:\n"
            for item_name, quantity in items:
                inventory_text += f"  • {item_name} ×{quantity}\n"
            inventory_text += "\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Крутить рулетку", callback_data="roulette")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

    await message.answer(inventory_text, reply_markup=keyboard)


@router.callback_query(F.data == "create_invite")
async def create_invite_handler(callback: CallbackQuery):
    user_id = callback.from_user.id

    # Проверяем блокировку
    user_data = get_user_data(user_id)
    if user_data and user_data.get('is_blocked'):
        await callback.answer("❌ Вы заблокированы и не можете использовать бота.", show_alert=True)
        return

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

    # Проверяем блокировку
    user_data = get_user_data(user_id)
    if user_data and user_data.get('is_blocked'):
        await callback.answer("❌ Вы заблокированы и не можете использовать бота.", show_alert=True)
        return

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
    active_status = get_active_status(user_id)

    win_rate = (user_data['wins'] / user_data['games_played'] * 100) if user_data['games_played'] > 0 else 0

    profile_text = (
        f"👤 Профиль игрока\n\n"
        f"📛 Имя: {user_data['username']}\n"
        f"🎯 Статус: {active_status}\n"
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


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    """Показывает профиль через команду"""
    user_id = message.from_user.id
    user_data = get_user_data(user_id)

    if not user_data:
        await message.answer("❌ Сначала зарегистрируйтесь через /start")
        return

    rank = get_user_rank(user_data['rating'])
    position = get_user_position(user_id)
    active_status = get_active_status(user_id)

    win_rate = (user_data['wins'] / user_data['games_played'] * 100) if user_data['games_played'] > 0 else 0

    profile_text = (
        f"👤 Профиль игрока\n\n"
        f"📛 Имя: {user_data['username']}\n"
        f"🎯 Статус: {active_status}\n"
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

    await message.answer(
        profile_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )


@router.message(Command("top"))
async def cmd_top(message: Message):
    """Показывает топ-10 через команду"""
    top_players = get_global_ranking()

    top_text = "🏆 Топ-10 игроков:\n\n"
    for i, (user_id, username, rating) in enumerate(top_players, 1):
        rank_emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        emoji = rank_emoji[i - 1] if i <= 10 else f"{i}."
        top_text += f"{emoji} {username} - {rating}⭐\n"

    await message.answer(
        top_text,
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
    user_id = callback.from_user.id

    # Проверяем блокировку
    user_data = get_user_data(user_id)
    if user_data and user_data.get('is_blocked'):
        await callback.answer("❌ Вы заблокированы и не можете использовать бота.", show_alert=True)
        return

    # Проверяем, не находится ли пользователь уже в игре
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
        [InlineKeyboardButton(text="👥 Играть с другом", callback_data="play_friend")],
        [InlineKeyboardButton(text="🎁 Реферальная программа", callback_data="ref_program")]
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

        # Отменяем старую задачу таймаута и запускаем новую
        if game_id in move_timeout_tasks:
            move_timeout_tasks[game_id].cancel()
        move_timeout_tasks[game_id] = asyncio.create_task(check_move_timeout(game_id))

        if game.winner:
            if game_id in move_timeout_tasks:
                move_timeout_tasks[game_id].cancel()
                del move_timeout_tasks[game_id]
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
            if game_id in move_timeout_tasks:
                move_timeout_tasks[game_id].cancel()
                del move_timeout_tasks[game_id]
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

    # Обновляем реферальную статистику для всех игроков
    for player_id in [game.player1, game.player2]:
        if player_id != -1:  # Не бот
            # Ищем реферальные связи где этот игрок является рефералом
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT referrer_id FROM referrals WHERE referred_id = ? AND is_completed = FALSE',
                           (player_id,))
            referrals = cursor.fetchall()
            conn.close()

            for (referrer_id,) in referrals:
                update_referral_games(referrer_id, player_id)

                # Проверяем условия завершения реферала
                referral_data = get_referral_data(referrer_id, player_id)
                user_data = get_user_data(player_id)

                if (referral_data and user_data and
                        referral_data['games_played'] >= REF_REQUIRED_GAMES and
                        user_data['rating'] >= 100):  # Звание Любитель
                    complete_referral(referrer_id, player_id)

                    # Уведомляем реферера
                    try:
                        referrer_data = get_user_data(referrer_id)
                        await bot.send_message(
                            referrer_id,
                            f"🎉 Ваш реферал выполнил все условия!\n\n"
                            f"👤 Пользователь: @{user_data['username']}\n"
                            f"✅ Игр сыграно: {referral_data['games_played']}\n"
                            f"🏅 Достиг звания: {get_user_rank(user_data['rating'])['name']}\n\n"
                            f"Теперь у вас +1 завершенный реферал!\n"
                            f"Всего завершенных: {get_completed_referrals_count(referrer_id)}"
                        )
                    except:
                        pass

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
                    update_last_game_time(player_id)
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
                    rating_text = f" (+{rating_change}⭐)" if rating_change else ""
                    winner_text = f"🎉 Победитель: {winner_name}{rating_text}"
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

        # Обновляем время последней игры
        if winner_id != -1:
            update_last_game_time(winner_id)
        if loser_id != -1:
            update_last_game_time(loser_id)

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

                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🎮 Новая игра", callback_data="find_game")],
                    [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
                    [InlineKeyboardButton(text="📋 Меню", callback_data="back_to_main")]
                ])

                await bot.send_message(
                    player_id,
                    final_message,
                    reply_markup=keyboard
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

    # Запускаем задачу проверки таймаута
    move_timeout_tasks[game_id] = asyncio.create_task(check_move_timeout(game_id))

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

    # Запускаем задачу проверки таймаута
    move_timeout_tasks[game_id] = asyncio.create_task(check_move_timeout(game_id))

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


# КОМАНДА /SMS ДЛЯ АДМИНА
@router.message(Command("sms"))
async def cmd_sms(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ У вас нет прав для использования этой команды.")
        return

    if message.chat.type != 'private':
        await message.answer("❌ Эта команда доступна только в личных сообщениях с ботом.")
        return

    await message.answer(
        "📢 Режим рассылки сообщений\n\n"
        "Отправьте текст сообщения или нажмите 'Пропустить':",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить текст", callback_data="skip_text")]
        ])
    )
    await state.set_state(SMSStates.waiting_text)


@router.callback_query(F.data == "skip_text")
async def skip_text(callback: CallbackQuery, state: FSMContext):
    await state.update_data(text=None)
    await callback.message.edit_text(
        "📷 Хотите добавить фото? Отправьте фото или нажмите 'Пропустить':",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить фото", callback_data="skip_photo")]
        ])
    )
    await state.set_state(SMSStates.waiting_photo)


@router.message(SMSStates.waiting_text)
async def process_sms_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    await message.answer(
        "📷 Хотите добавить фото? Отправьте фото или нажмите 'Пропустить':",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить фото", callback_data="skip_photo")]
        ])
    )
    await state.set_state(SMSStates.waiting_photo)


@router.callback_query(F.data == "skip_photo")
async def skip_photo(callback: CallbackQuery, state: FSMContext):
    await state.update_data(photo=None)
    await callback.message.edit_text(
        "🎥 Хотите добавить видео? Отправьте видео или нажмите 'Пропустить':",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить видео", callback_data="skip_video")]
        ])
    )
    await state.set_state(SMSStates.waiting_video)


@router.message(SMSStates.waiting_photo)
async def process_sms_photo(message: Message, state: FSMContext):
    if message.photo:
        await state.update_data(photo=message.photo[-1].file_id)
    else:
        await state.update_data(photo=None)

    await message.answer(
        "🎥 Хотите добавить видео? Отправьте видео или нажмите 'Пропустить':",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить видео", callback_data="skip_video")]
        ])
    )
    await state.set_state(SMSStates.waiting_video)


@router.callback_query(F.data == "skip_video")
async def skip_video(callback: CallbackQuery, state: FSMContext):
    await state.update_data(video=None)
    await callback.message.edit_text(
        "🔄 Хотите добавить GIF? Отправьте GIF или нажмите 'Пропустить':",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить GIF", callback_data="skip_gif")]
        ])
    )
    await state.set_state(SMSStates.waiting_gif)


@router.message(SMSStates.waiting_video)
async def process_sms_video(message: Message, state: FSMContext):
    if message.video:
        await state.update_data(video=message.video.file_id)
    else:
        await state.update_data(video=None)

    await message.answer(
        "🔄 Хотите добавить GIF? Отправьте GIF или нажмите 'Пропустить':",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить GIF", callback_data="skip_gif")]
        ])
    )
    await state.set_state(SMSStates.waiting_gif)


@router.callback_query(F.data == "skip_gif")
async def skip_gif(callback: CallbackQuery, state: FSMContext):
    await state.update_data(gif=None)
    await callback.message.edit_text(
        "🔘 Хотите добавить кнопки? Отправьте текст кнопок в формате:\n"
        "Текст кнопки1 - ссылка1\n"
        "Текст кнопки2 - ссылка2\n\n"
        "Или нажмите 'Пропустить':",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить кнопки", callback_data="skip_buttons")]
        ])
    )
    await state.set_state(SMSStates.waiting_buttons)


@router.message(SMSStates.waiting_gif)
async def process_sms_gif(message: Message, state: FSMContext):
    if message.animation:
        await state.update_data(gif=message.animation.file_id)
    else:
        await state.update_data(gif=None)

    await message.answer(
        "🔘 Хотите добавить кнопки? Отправьте текст кнопок в формате:\n"
        "Текст кнопки1 - ссылка1\n"
        "Текст кнопки2 - ссылка2\n\n"
        "Или нажмите 'Пропустить':",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить кнопки", callback_data="skip_buttons")]
        ])
    )
    await state.set_state(SMSStates.waiting_buttons)


@router.callback_query(F.data == "skip_buttons")
async def skip_buttons(callback: CallbackQuery, state: FSMContext):
    await state.update_data(buttons=None)
    await send_broadcast_message(callback, state)


@router.message(SMSStates.waiting_buttons)
async def process_sms_buttons(message: Message, state: FSMContext):
    buttons_data = None
    if message.text and message.text != "⏭ Пропустить кнопки":
        buttons_data = message.text

    await state.update_data(buttons=buttons_data)
    await send_broadcast_message(message, state)


async def send_broadcast_message(update, state: FSMContext):
    data = await state.get_data()

    # Создаем клавиатуру из кнопок
    keyboard = None
    if data.get('buttons'):
        try:
            buttons = []
            for line in data['buttons'].split('\n'):
                if ' - ' in line:
                    text, url = line.split(' - ', 1)
                    buttons.append([InlineKeyboardButton(text=text.strip(), url=url.strip())])
            if buttons:
                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        except Exception as e:
            print(f"Ошибка создания кнопок: {e}")

    # Получаем всех пользователей (только ЛС, не чаты)
    users = get_all_users()
    success_count = 0
    fail_count = 0

    if isinstance(update, CallbackQuery):
        await update.answer("🔄 Начинаю рассылку сообщений...")
    else:
        await update.answer("🔄 Начинаю рассылку сообщений...")

    for user_id in users:
        try:
            if data.get('photo'):
                await bot.send_photo(
                    chat_id=user_id,
                    photo=data['photo'],
                    caption=data.get('text', ''),
                    reply_markup=keyboard
                )
            elif data.get('video'):
                await bot.send_video(
                    chat_id=user_id,
                    video=data['video'],
                    caption=data.get('text', ''),
                    reply_markup=keyboard
                )
            elif data.get('gif'):
                await bot.send_animation(
                    chat_id=user_id,
                    animation=data['gif'],
                    caption=data.get('text', ''),
                    reply_markup=keyboard
                )
            else:
                await bot.send_message(
                    chat_id=user_id,
                    text=data.get('text', '📢 Сообщение от администратора'),
                    reply_markup=keyboard
                )
            success_count += 1
        except Exception as e:
            print(f"Ошибка отправки пользователю {user_id}: {e}")
            fail_count += 1
        await asyncio.sleep(0.1)  # Задержка чтобы не превысить лимиты

    # Сохраняем статистику рассылки
    save_broadcast_stats(success_count, fail_count)

    # Отправляем отчет админу
    report_message = (
        f"✅ Рассылка завершена!\n\n"
        f"✅ Успешно: {success_count}\n"
        f"❌ Ошибок: {fail_count}"
    )

    if isinstance(update, CallbackQuery):
        await update.message.answer(report_message)
    else:
        await update.answer(report_message)

    await state.clear()


# АДМИН ПАНЕЛЬ
@router.message(Command("apanel"))
async def cmd_apanel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ У вас нет прав для использования этой команды.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🚫 Заблокировать пользователя", callback_data="admin_block")],
        [InlineKeyboardButton(text="✅ Разблокировать пользователя", callback_data="admin_unblock")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")]
    ])

    await message.answer(
        "👨‍💻 Админ панель\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 день", callback_data="stats_24")],
        [InlineKeyboardButton(text="1 неделя", callback_data="stats_168")],
        [InlineKeyboardButton(text="1 месяц", callback_data="stats_720")]
    ])

    await callback.message.edit_text(
        "📊 Выберите период для статистики:",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("stats_"))
async def show_stats(callback: CallbackQuery):
    period = callback.data.replace("stats_", "")
    period_hours = int(period)

    stats = get_stats(period_hours)

    period_text = ""
    if period_hours == 24:
        period_text = "за последние 24 часа"
    elif period_hours == 168:
        period_text = "за последнюю неделю"
    else:
        period_text = "за последний месяц"

    stats_text = (
        f"📊 Статистика {period_text}:\n\n"
        f"👤 Новые пользователи: {stats['new_users']}\n"
        f"🎮 Сыграно игр: {stats['games_played']}\n"
        f"😴 Неактивных пользователей: {stats['inactive_users']}\n"
        f"💬 Новых чатов: {stats['new_chats']}"
    )

    await callback.message.edit_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_apanel")]
        ])
    )


@router.callback_query(F.data == "admin_block")
async def admin_block(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🚫 Введите username пользователя для блокировки (без @):"
    )
    await state.set_state(AdminStates.waiting_username_for_block)


@router.message(AdminStates.waiting_username_for_block)
async def process_block_user(message: Message, state: FSMContext):
    username = message.text.strip()

    if block_user(username):
        await message.answer(f"✅ Пользователь @{username} заблокирован!")
    else:
        await message.answer(f"❌ Пользователь @{username} не найден!")

    await state.clear()


@router.callback_query(F.data == "admin_unblock")
async def admin_unblock(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✅ Введите username пользователя для разблокировки (без @):"
    )
    await state.set_state(AdminStates.waiting_username_for_unblock)


@router.message(AdminStates.waiting_username_for_unblock)
async def process_unblock_user(message: Message, state: FSMContext):
    username = message.text.strip()

    if unblock_user(username):
        await message.answer(f"✅ Пользователь @{username} разблокирован!")
    else:
        await message.answer(f"❌ Пользователь @{username} не найден или не был заблокирован!")

    await state.clear()


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery):
    await callback.message.edit_text(
        "📢 Для начала рассылки используйте команду /sms"
    )


@router.callback_query(F.data == "back_to_apanel")
async def back_to_apanel(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🚫 Заблокировать пользователя", callback_data="admin_block")],
        [InlineKeyboardButton(text="✅ Разблокировать пользователя", callback_data="admin_unblock")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")]
    ])

    await callback.message.edit_text(
        "👨‍💻 Админ панель\n\n"
        "Выберите действие:",
        reply_markup=keyboard
    )


# ФУНКЦИЯ РАССЫЛКИ НЕАКТИВНЫМ ПОЛЬЗОВАТЕЛЯМ
async def send_inactive_users_reminder():
    """Рассылает напоминания неактивным пользователям"""
    inactive_users = get_inactive_users(24)  # Не играли более 24 часов

    success_count = 0
    fail_count = 0

    for user_id, username, last_game in inactive_users:
        try:
            await bot.send_message(
                user_id,
                "👋 Эй, ты не забыл? Твой ранг все еще меньше Мастера, неужели ты не хочешь стать лучшим? 🏆"
            )
            success_count += 1
        except Exception as e:
            print(f"Ошибка отправки напоминания пользователю {user_id}: {e}")
            fail_count += 1
        await asyncio.sleep(0.1)

    # Отправляем отчет админу
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📢 Рассылка неактивным пользователям завершена!\n\n"
            f"✅ Успешно: {success_count}\n"
            f"❌ Ошибок: {fail_count}"
        )
    except:
        pass


# ОБРАБОТЧИК СДАЧИ В ИГРЕ
@router.callback_query(F.data == "surrender")
async def process_surrender(callback: CallbackQuery):
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

    # Отменяем задачу таймаута
    if game_id in move_timeout_tasks:
        move_timeout_tasks[game_id].cancel()
        del move_timeout_tasks[game_id]

    # Определяем победителя и проигравшего
    if user_id == game.player1:
        winner_id = game.player2
        loser_id = game.player1
    else:
        winner_id = game.player1
        loser_id = game.player2

    # Обновляем статистику
    winner_data = get_user_data(winner_id)
    loser_data = get_user_data(loser_id)

    if game.is_rated and winner_data and loser_data:
        # Отнимаем рейтинг за сдачу
        lose_change = int(RATING_CHANGE_BASE * 0.8)  # 80% от стандартного штрафа
        loser_data['rating'] -= lose_change
        loser_data['games_played'] += 1
        loser_data['losses'] += 1
        save_user_data(loser_data)

        # Обновляем время последней игры
        update_last_game_time(winner_id)
        update_last_game_time(loser_id)

        # Отправляем сообщения игрокам
        for player_id in [game.player1, game.player2]:
            if player_id != -1:  # Не бот
                user_data = get_user_data(player_id)
                if user_data:
                    if player_id == winner_id:
                        message_text = (
                            f"🎮 Игра завершена!\n\n"
                            f"Противник сдался!\n\n"
                            f"🏆 Вы победили!\n"
                            f"Ваш рейтинг: {user_data['rating']}⭐"
                        )
                    else:
                        message_text = (
                            f"🎮 Игра завершена!\n\n"
                            f"Вы сдались! 🏳️\n\n"
                            f"📉 Изменение рейтинга: -{lose_change}⭐\n"
                            f"Ваш рейтинг: {user_data['rating']}⭐"
                        )

                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🎮 Новая игра", callback_data="find_game")],
                        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
                        [InlineKeyboardButton(text="📋 Меню", callback_data="back_to_main")]
                    ])

                    await bot.send_message(
                        player_id,
                        message_text,
                        reply_markup=keyboard
                    )
    else:
        # Без рейтинга
        if winner_data:
            winner_data['games_played'] += 1
            winner_data['wins'] += 1
            save_user_data(winner_data)
        if loser_data:
            loser_data['games_played'] += 1
            loser_data['losses'] += 1
            save_user_data(loser_data)

        # Обновляем время последней игры
        update_last_game_time(winner_id)
        update_last_game_time(loser_id)

        # Отправляем сообщения
        for player_id in [game.player1, game.player2]:
            if player_id != -1:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🎮 Новая игра", callback_data="find_game")],
                    [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
                    [InlineKeyboardButton(text="📋 Меню", callback_data="back_to_main")]
                ])

                if player_id == winner_id:
                    await bot.send_message(player_id, "🎮 Противник сдался! Вы победили! 🏆", reply_markup=keyboard)
                else:
                    await bot.send_message(player_id, "🎮 Вы сдались! 🏳️", reply_markup=keyboard)

    # Удаляем игру
    if game_id in game_sessions:
        del game_sessions[game_id]

    await callback.answer("Вы сдались!")


async def main():
    print("Бот запущен!")

    # Запускаем периодическую рассылку неактивным пользователям (каждые 24 часа)
    async def periodic_reminder():
        while True:
            await asyncio.sleep(24 * 60 * 60)  # 24 часа
            await send_inactive_users_reminder()

    # Запускаем периодическую задачу в фоне
    asyncio.create_task(periodic_reminder())

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())