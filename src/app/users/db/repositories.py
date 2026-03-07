from datetime import datetime, timedelta
from logger import get_logger
import psycopg
import os

log = get_logger(__name__)

log.info(
    "Connecting to DB host=%s port=%s db=%s",
    os.getenv("DB_HOST"),
    os.getenv("DB_PORT"),
    os.getenv("DB_NAME")
)

conn = psycopg.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)

class UserRepository:
    def create_tables(): 
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS users (
               user_id BIGINT PRIMARY KEY,
               balance FLOAT DEFAULT 0,
               referrer_id TEXT NULL,
               created_at TIMESTAMP
            )""")

            cur.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                vpn_key TEXT NOT NULL,
                remna_uuid TEXT,
                type TEXT NOT NULL,
                start_date TIMESTAMP NOT NULL,
                end_date TIMESTAMP NOT NULL,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS refs (
                    referrer_id TEXT,
                    invited_id BIGINT,
                    bonus FLOAT,
                    created_at TIMESTAMP
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    payment_id TEXT UNIQUE NOT NULL,
                    user_id BIGINT NOT NULL,
                    amount FLOAT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP
                );
            """)

        conn.commit()

    def user_has_referrer(self, user_id: int) -> bool:
        self.create_user_if_not_exists(user_id)
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE user_id = %s AND referrer_id IS NOT NULL", (user_id,))
            return cur.fetchone() is not None
    
    def user_has_invites(self, user_id: int) -> bool:
        self.create_user_if_not_exists(user_id)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM refs WHERE referrer_id = %s LIMIT 1",
                (str(user_id),)
            )
            return cur.fetchone() is not None
        
    def user_has_been_invited(self, user_id: int):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT referrer_id FROM refs WHERE invited_id = %s LIMIT 1",
                (str(user_id),)
            )
            result = cur.fetchone()
            if result:
                return result[0]  # Возвращаем первый элемент кортежа (referrer_id)
            return None  # Или можно вернуть 0, -1 или другое значение по умолчанию
    
    def get_balance(self, user_id: int):
        self.create_user_if_not_exists(user_id)
        with conn.cursor() as cur:
            cur.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
            result = cur.fetchone()
            if result is not None:
                balance = result[0]
            else:
                balance = 0
            return balance

    def add_balance(self, user_id, amount):
        self.create_user_if_not_exists(user_id)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET balance = balance + %s WHERE user_id = %s",
                (amount, user_id)
            )

            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO users (user_id, balance, created_at)
                    VALUES (%s, %s, %s)
                    """,
                    (user_id, amount, datetime.now())
                )
        
        conn.commit()

    def uncharge_balance(self, user_id, amount):
        self.create_user_if_not_exists(user_id)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET balance = balance - %s WHERE user_id = %s",
                (amount, user_id)
            )

        conn.commit()

    def user_has_trial(self, user_id: int) -> bool:
        self.create_user_if_not_exists(user_id)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM subscriptions
                WHERE user_id = %s
                  AND type = 'trial'
                LIMIT 1
                """,
                (user_id,)
            )
            return cur.fetchone() is not None
    
    def create_user_if_not_exists(self, user_id: int):
        log.info("create_user_if_not_exists user_id=%s", user_id)

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, created_at)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id, datetime.now()))

            log.info("rows affected=%s", cur.rowcount)

        conn.commit()

    def set_referrer(self, user_id: int, referrer_id: int):
        log.info("set_referrer user_id=%s referrer_id=%s", user_id, referrer_id)
        self.create_user_if_not_exists(user_id)

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET referrer_id = %s WHERE user_id = %s",
                (referrer_id, user_id)
            )

            log.info("rows affected=%s", cur.rowcount)

        conn.commit()

    def set_referrer_on_user(self, user_id: int, referrer_id: str):
        self.create_user_if_not_exists(user_id)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO refs (referrer_id, invited_id, bonus, created_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (invited_id) DO NOTHING
                """,
                (referrer_id, user_id, 0, datetime.now())
            )

            inserted = cur.rowcount == 1

        conn.commit()
        return inserted

    def get_referrer_code_by_user(self, user_id: int) -> str | None:
        self.create_user_if_not_exists(user_id)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT referrer_id FROM users WHERE user_id = %s",
                (user_id,)
            )
            
            return cur.fetchone()
        
    def get_user_by_reffer_code(self, referrer_id: int) -> str | None:
        log.info("get_user_by_reffer_code referrer_id=%s", referrer_id)

        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id FROM users WHERE referrer_id = %s",
                (referrer_id,)
            )

            row = cur.fetchone()

        log.info("ref_owner=%s", row)
        return row
        
    def save_payment(self, payment_id: int, user_id: int, amount: int, status: str):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO payments
                (payment_id, user_id, amount, created_at)
            """, (
                payment_id, user_id, amount, status, datetime.now()
            ))

        conn.commit()

    def is_payment_processed(self, payment_id: str) -> bool:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1
                FROM payments
                WHERE payment_id = %s
                LIMIT 1
            """, (payment_id,))

            return cur.fetchone() is not None
    
    def mark_payment_processed(self, payment_id, user_id, amount):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO payments (payment_id, user_id, amount, status)
                VALUES (%s, %s, %s, %s)
            """, (payment_id, user_id, amount, "success"))

        conn.commit()

    def get_all_users(self):
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users")
            users = cur.fetchall()

            return users
        
    def count_invited_users(self, user_id: int) -> int:
        """
        Сколько пользователей зарегистрировались по реф-коду пользователя
        """
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM refs
                WHERE referrer_id = %s
                """,
                (str(user_id),)
            )
            return cur.fetchone()[0]


    def count_invited_with_trial(self, user_id: int) -> int:
        """
        Сколько приглашённых оформили trial
        """
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(DISTINCT r.invited_id)
                FROM refs r
                JOIN subscriptions s
                    ON s.user_id = r.invited_id
                WHERE r.referrer_id = %s
                  AND s.type = 'trial'
                """,
                (str(user_id),)
            )
            return cur.fetchone()[0]
        
    def add_referral_bonus(self, invited_user_id: int, amount: float):
        """
        Начисляем bonus в таблице refs для конкретного приглашённого
        """
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE refs
                SET bonus = bonus + %s
                WHERE invited_id = %s
                """,
                (amount, invited_user_id)
            )
        conn.commit()
    
    def get_total_referral_earnings(self, user_id: int) -> float:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(bonus), 0)
                FROM refs
                WHERE referrer_id = %s
                """,
                (str(user_id),)
            )
            return cur.fetchone()[0]

class SubscriptionRepository:
    async def add_subscription(self, user_id: int, type: str, subscribe_link: str, days: int):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO subscriptions
                (user_id, vpn_key, type, start_date, end_date)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                user_id,
                subscribe_link,
                type,
                datetime.now(),
                datetime.now() + timedelta(days=days)
            ))

        conn.commit()
        return True

    def get_active_subscriptions(self, user_id: int):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT vpn_key, type
                FROM subscriptions
                WHERE user_id = %s
                  AND is_active = 1
            """, (user_id,))
            return cur.fetchall()
        
    def get_expired_trials(self):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT user_id FROM subscriptions
                WHERE type = 'trial'
                AND end_date <= NOW()
            """)

            return cur.fetchall()

    async def delete_expired_trials(self):
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM subscriptions
                WHERE type = 'trial'
                AND end_date <= NOW()
            """)

            return cur.rowcount
        
    def get_active_trial(self, user_id: int):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, end_date
                FROM subscriptions
                WHERE user_id = %s
                  AND type = 'trial'
                  AND is_active = 1
                LIMIT 1
            """, (user_id,))
            return cur.fetchone()
        
    def get_active_paid(self, user_id: int):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT vpn_key
                FROM subscriptions
                WHERE user_id = %s
                  AND type = 'paid'
                  AND is_active = 1
                LIMIT 1
            """, (user_id,))
            return cur.fetchone()

    def delete_sub_link(self, vpn_key: str):
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM subscriptions
                WHERE vpn_key = %s
            """, (vpn_key,))

        conn.commit()

    def delete_trial_sub_link(self, user_id: int):
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM subscriptions
                WHERE user_id = %s
                    AND type = 'trial'
            """, (user_id,))

        conn.commit()
        
        
    def get_subscription_type(self, vpn_key: str):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT type
                FROM subscriptions
                WHERE vpn_key = %s
            """, (vpn_key,))
            return cur.fetchone()

    def change_type_sub_link(self, user_id: int):
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE subscriptions
                    SET type = 'paid'
                WHERE user_id = %s
                    AND type = 'trial'
            """, (user_id,))

        conn.commit()