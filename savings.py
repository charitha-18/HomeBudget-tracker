
from database import get_db_connection
from datetime import date
import math


# 1. GET ALL SAVINGS GOALS
def get_savings_goals(user_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT id, goal_name, target_amount, saved_amount,
                   target_date, created_at
            FROM savings_goals
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (user_id,))

        goals = cursor.fetchall()

        for goal in goals:
            target = float(goal["target_amount"])
            saved = float(goal["saved_amount"])

            goal["remaining_amount"] = max(target - saved, 0)

            goal["progress"] = (
                min(round((saved / target) * 100, 2), 100)
                if target > 0 else 0
            )

            goal["completed"] = saved >= target

        return goals

    finally:
        cursor.close()
        connection.close()


# 2. CREATE A NEW SAVINGS GOAL
def add_savings_goal(user_id, goal_name, target_amount, target_date):
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO savings_goals
            (user_id, goal_name, target_amount, saved_amount, target_date)
            VALUES (%s, %s, %s, 0, %s)
        """, (user_id, goal_name, target_amount, target_date))

        connection.commit()

    finally:
        cursor.close()
        connection.close()


# 3. ADD MONEY TO A SAVINGS GOAL
# Also records the contribution as an expense
# so the Monthly Budget is updated.
def add_savings(user_id, goal_id, amount):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        amount = float(amount)

        if not math.isfinite(amount) or amount <= 0:
            return False

        cursor.execute("""
            SELECT goal_name, target_amount, saved_amount
            FROM savings_goals
            WHERE id = %s AND user_id = %s
            FOR UPDATE
        """, (goal_id, user_id))

        goal = cursor.fetchone()

        if not goal:
            connection.rollback()
            return False

        target = float(goal["target_amount"])
        saved = float(goal["saved_amount"])

        if saved + amount > target:
            connection.rollback()
            return False

        today = date.today()
        current_month = today.strftime("%Y-%m")

        # Update savings goal
        cursor.execute("""
            UPDATE savings_goals
            SET saved_amount = saved_amount + %s
            WHERE id = %s AND user_id = %s
        """, (amount, goal_id, user_id))

        # Record contribution as an expense
        cursor.execute("""
            INSERT INTO transactions
            (
                user_id,
                type,
                description,
                amount,
                transaction_date,
                category,
                budget_month
            )
            VALUES (%s, 'expense', %s, %s, %s, 'Savings', %s)
        """, (
            user_id,
            "Savings contribution: " + goal["goal_name"],
            amount,
            today,
            current_month
        ))

        connection.commit()
        return True

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


# 4. DELETE A SAVINGS GOAL
def delete_savings_goal(user_id, goal_id):
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            DELETE FROM savings_goals
            WHERE id = %s AND user_id = %s
        """, (goal_id, user_id))

        deleted = cursor.rowcount
        connection.commit()

        return deleted > 0

    finally:
        cursor.close()
        connection.close()
