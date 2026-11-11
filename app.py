import math
import os

from functools import wraps
from datetime import date, datetime

from unusual_expenses import detect_unusual_expenses
from smart_budget import (
    detect_salary_change,
    detect_spending_patterns,
    detect_grocery_increase
)
from savings import (
    get_savings_goals,
    add_savings_goal,
    add_savings,
    delete_savings_goal
)

from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from database import get_db_connection
from analysis import get_analysis


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-to-a-long-random-secret-key"
)


# ==========================================
# LOGIN REQUIRED DECORATOR
# ==========================================

def login_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))

        return route_function(*args, **kwargs)

    return wrapper


# ==========================================
# REGISTER
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or len(password) < 8:
            return (
                "Enter your name, valid email and password "
                "(minimum 8 characters).",
                400
            )

        connection = get_db_connection()
        cursor = None

        try:
            cursor = connection.cursor()

            hashed_password = generate_password_hash(password)

            cursor.execute("""
                INSERT INTO users (name, email, password)
                VALUES (%s, %s, %s)
            """, (name, email, hashed_password))

            connection.commit()

            flash("Registration successful. Please login.", "success")

            return redirect(url_for("login"))

        except Exception:
            connection.rollback()

            return (
                "Registration failed. This email may already "
                "be registered.",
                400
            )

        finally:
            if cursor:
                cursor.close()

            connection.close()

    return render_template("register.html")


# ==========================================
# LOGIN
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = get_db_connection()
        cursor = None

        try:
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT id, name, email, password
                FROM users
                WHERE email = %s
            """, (email,))

            user = cursor.fetchone()

            if user and check_password_hash(
                user["password"], password
            ):

                session.clear()

                session["user_id"] = user["id"]
                session["user_name"] = user["name"]

                flash("Login successful!", "success")

                return redirect(url_for("index"))

            return "Invalid email or password.", 401

        finally:
            if cursor:
                cursor.close()

            connection.close()

    return render_template("login.html")


# ==========================================
# LOGOUT
# ==========================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# ==========================================
# LANDING PAGE
# ==========================================


@app.route("/")
def landing():
    return render_template("landing.html")



# ==========================================
# HOME DASHBOARD
# ==========================================

@app.route("/dashboard")
@login_required
def index():

    user_id = session["user_id"]
    selected_month = request.args.get("month", "all")

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(
            dictionary=True,
            buffered=True
        )

        if selected_month == "all":

            cursor.execute("""
                SELECT
                    id,
                    type,
                    description,
                    amount,
                    transaction_date,
                    category,
                    budget_month
                FROM transactions
                WHERE user_id = %s
                ORDER BY transaction_date DESC, id DESC
            """, (user_id,))

        else:

            try:
                month_start = datetime.strptime(
                    selected_month, "%Y-%m"
                ).date()

                if month_start.strftime("%Y-%m") != selected_month:
                    raise ValueError

            except ValueError:
                return "Invalid month format. Use YYYY-MM.", 400

            cursor.execute("""
                SELECT
                    id,
                    type,
                    description,
                    amount,
                    transaction_date,
                    category,
                    budget_month
                FROM transactions
                WHERE user_id = %s
                  AND COALESCE(
                      budget_month,
                      DATE_FORMAT(transaction_date, '%Y-%m')
                  ) = %s
                ORDER BY transaction_date DESC, id DESC
            """, (user_id, selected_month))

        transactions = cursor.fetchall()

    finally:
        if cursor:
            cursor.close()

        connection.close()

    income_transactions = [
        transaction for transaction in transactions
        if str(transaction["type"]).lower() == "income"
    ]

    expense_transactions = [
        transaction for transaction in transactions
        if str(transaction["type"]).lower() == "expense"
    ]

    total_income = sum(
        float(transaction["amount"])
        for transaction in income_transactions
    )

    total_expenses = sum(
        float(transaction["amount"])
        for transaction in expense_transactions
    )

    balance = total_income - total_expenses

    category_totals = {}

    for transaction in expense_transactions:

        category = transaction["category"] or "Other"
        amount = float(transaction["amount"])

        category_totals[category] = (
            category_totals.get(category, 0) + amount
        )

    category_expenses = [
        {
            "category": category,
            "total": total
        }
        for category, total in sorted(category_totals.items())
    ]

    return render_template(
        "index.html",
        transactions=transactions,
        income_transactions=income_transactions,
        expense_transactions=expense_transactions,
        category_expenses=category_expenses,
        total_income=total_income,
        total_expenses=total_expenses,
        balance=balance,
        selected_month=selected_month
    )


# ==========================================
# ADD TRANSACTION
# ==========================================

@app.route("/add", methods=["POST"])
@login_required
def add_transaction():

    user_id = session["user_id"]

    transaction_type = request.form.get(
        "type", ""
    ).strip().lower()

    description = request.form.get(
        "description", ""
    ).strip()

    category = request.form.get(
        "category", "Other"
    ).strip()

    amount = request.form.get("amount")

    transaction_date = request.form.get(
        "transaction_date", ""
    ).strip()

    budget_month = request.form.get(
        "budget_month", ""
    ).strip()

    if transaction_type not in ["income", "expense"]:
        return "Invalid transaction type", 400

    if not description or not transaction_date:
        return "Please fill in all fields", 400

    if not category:
        category = "Other"

    try:
        amount = float(amount)

        if not math.isfinite(amount) or amount <= 0:
            return "Amount must be greater than zero", 400

        selected_date = datetime.strptime(
            transaction_date, "%Y-%m-%d"
        ).date()

        if not budget_month:
            budget_month = selected_date.strftime("%Y-%m")

        parsed_month = datetime.strptime(
            budget_month, "%Y-%m"
        )

        if parsed_month.strftime("%Y-%m") != budget_month:
            raise ValueError

        current_time = datetime.now().time().replace(
            microsecond=0
        )

        transaction_datetime = datetime.combine(
            selected_date, current_time
        )

    except (ValueError, TypeError):
        return (
            "Please enter a valid amount, date and budget month",
            400
        )

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO transactions
                (user_id, type, description, amount,
                 transaction_date, category, budget_month)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            transaction_type,
            description,
            amount,
            transaction_datetime,
            category,
            budget_month
        ))

        connection.commit()

    finally:
        if cursor:
            cursor.close()

        connection.close()

    flash("Transaction added successfully!", "success")

    return redirect(url_for("index"))


# ==========================================
# DELETE TRANSACTION
# ==========================================

@app.route("/delete/<int:transaction_id>", methods=["POST"])
@login_required
def delete_transaction(transaction_id):

    user_id = session["user_id"]
    selected_month = request.form.get("month")

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor()

        cursor.execute("""
            DELETE FROM transactions
            WHERE id = %s AND user_id = %s
        """, (transaction_id, user_id))

        connection.commit()

    finally:
        if cursor:
            cursor.close()

        connection.close()

    if selected_month:
        return redirect(url_for(
            "budget_settings",
            month=selected_month
        ))

    return redirect(url_for("index"))


# ==========================================
# EDIT TRANSACTION
# ==========================================

@app.route("/edit/<int:transaction_id>", methods=["GET", "POST"])
@login_required
def edit_transaction(transaction_id):

    user_id = session["user_id"]
    connection = get_db_connection()
    cursor = None

    transaction = None

    try:
        cursor = connection.cursor(dictionary=True)

        if request.method == "POST":

            transaction_type = request.form.get(
                "type", ""
            ).strip().lower()

            description = request.form.get(
                "description", ""
            ).strip()

            category = request.form.get(
                "category", "Other"
            ).strip()

            amount = request.form.get("amount")

            transaction_date = request.form.get(
                "transaction_date", ""
            ).strip()

            budget_month = request.form.get(
                "budget_month", ""
            ).strip()

            if not budget_month:
                cursor.execute("""
                    SELECT budget_month
                    FROM transactions
                    WHERE id = %s AND user_id = %s
                """, (transaction_id, user_id))

                old_month = cursor.fetchone()

                budget_month = (
                    old_month["budget_month"]
                    if old_month and old_month["budget_month"]
                    else ""
                )

            if transaction_type not in ["income", "expense"]:
                return "Invalid transaction type", 400

            if not description or not transaction_date:
                return "Please fill in all fields", 400

            if not category:
                category = "Other"

            try:
                amount = float(amount)

                if not math.isfinite(amount) or amount <= 0:
                    return "Amount must be greater than zero", 400

                selected_date = datetime.strptime(
                    transaction_date, "%Y-%m-%d"
                ).date()

                if not budget_month:
                    budget_month = selected_date.strftime("%Y-%m")

                parsed_budget_month = datetime.strptime(
                    budget_month, "%Y-%m"
                )

                if (
                    parsed_budget_month.strftime("%Y-%m")
                    != budget_month
                ):
                    raise ValueError

                current_time = datetime.now().time().replace(
                    microsecond=0
                )

                transaction_datetime = datetime.combine(
                    selected_date, current_time
                )

            except (ValueError, TypeError):
                return "Please enter a valid amount and date", 400

            cursor.execute("""
                UPDATE transactions
                SET type = %s,
                    description = %s,
                    amount = %s,
                    transaction_date = %s,
                    category = %s,
                    budget_month = %s
                WHERE id = %s AND user_id = %s
            """, (
                transaction_type,
                description,
                amount,
                transaction_datetime,
                category,
                budget_month,
                transaction_id,
                user_id
            ))

            connection.commit()

            return redirect(url_for("index"))

        cursor.execute("""
            SELECT *
            FROM transactions
            WHERE id = %s AND user_id = %s
        """, (transaction_id, user_id))

        transaction = cursor.fetchone()

    finally:
        if cursor:
            cursor.close()

        connection.close()

    if transaction is None:
        return "Transaction not found", 404

    return render_template(
        "edit.html",
        transaction=transaction
    )


# ==========================================
# ANALYSIS DASHBOARD
# ==========================================

@app.route("/analysis")
@login_required
def analysis_dashboard():

    selected_month = request.args.get("month", "all")

    if selected_month != "all":

        try:
            parsed_month = datetime.strptime(
                selected_month, "%Y-%m"
            )

            if parsed_month.strftime("%Y-%m") != selected_month:
                raise ValueError

        except ValueError:
            return "Invalid month format", 400

    analysis = get_analysis(
        session["user_id"],
        selected_month
    )

    return render_template(
        "analysis.html",
        **analysis
    )


# ==========================================
# MONTHLY BUDGET
# ==========================================

@app.route("/budget", methods=["GET", "POST"])
@login_required
def budget_settings():

    selected_month = request.values.get(
        "month", date.today().strftime("%Y-%m")
    )

    try:
        month_date = datetime.strptime(
            selected_month, "%Y-%m"
        ).date()

        if month_date.strftime("%Y-%m") != selected_month:
            raise ValueError

    except ValueError:
        return "Invalid month format", 400

    # SAVE MONTHLY BUDGET
    if request.method == "POST":

        try:
            budget_limit = float(
                request.form.get("budget_limit", "")
            )

            if (
                not math.isfinite(budget_limit)
                or budget_limit <= 0
            ):
                return "Budget must be greater than zero", 400

        except (ValueError, TypeError):
            return "Enter a valid budget amount", 400

        connection = get_db_connection()
        cursor = None

        try:
            cursor = connection.cursor()

            cursor.execute("""
                INSERT INTO monthly_budgets
                    (user_id, budget_month, budget_limit)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    budget_limit = VALUES(budget_limit)
            """, (
                session["user_id"],
                selected_month,
                budget_limit
            ))

            connection.commit()

        finally:
            if cursor:
                cursor.close()

            connection.close()

        return redirect(url_for(
            "budget_settings",
            month=selected_month
        ))

    # FETCH BUDGET AND TRANSACTIONS
    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT budget_limit
            FROM monthly_budgets
            WHERE user_id = %s
              AND budget_month = %s
        """, (session["user_id"], selected_month))

        result = cursor.fetchone()

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total_expenses
            FROM transactions
            WHERE user_id = %s
              AND LOWER(type) = 'expense'
              AND COALESCE(
                  budget_month,
                  DATE_FORMAT(transaction_date, '%Y-%m')
              ) = %s
        """, (session["user_id"], selected_month))

        expense_result = cursor.fetchone()

        cursor.execute("""
            SELECT
                id,
                type,
                description,
                category,
                amount,
                transaction_date
            FROM transactions
            WHERE user_id = %s
              AND COALESCE(
                  budget_month,
                  DATE_FORMAT(transaction_date, '%Y-%m')
              ) = %s
            ORDER BY transaction_date DESC, id DESC
        """, (session["user_id"], selected_month))

        transactions = cursor.fetchall()

    finally:
        if cursor:
            cursor.close()

        connection.close()

    budget_limit = (
        float(result["budget_limit"]) if result else 0
    )

    total_expenses = float(
        expense_result["total_expenses"]
    )

    remaining = budget_limit - total_expenses

    usage_percent = (
        round(total_expenses / budget_limit * 100, 1)
        if budget_limit > 0 else 0
    )

    savings_goals = get_savings_goals(
        session["user_id"]
    )

    return render_template(
        "budget.html",
        selected_month=selected_month,
        budget_limit=budget_limit,
        total_expenses=total_expenses,
        remaining=remaining,
        usage_percent=usage_percent,
        transactions=transactions,
        savings_goals=savings_goals
    )


# ==========================================
# TRANSFER REMAINING BUDGET TO SAVINGS
# ==========================================

@app.route(
    "/transfer-budget-to-savings",
    methods=["POST"]
)
@login_required
def transfer_budget_to_savings():

    user_id = session["user_id"]

    goal_id = request.form.get("goal_id", "").strip()
    selected_month = request.form.get("month", "").strip()

    # VALIDATE MONTH AND GOAL ID
    try:
        parsed_month = datetime.strptime(
            selected_month, "%Y-%m"
        )

        if parsed_month.strftime("%Y-%m") != selected_month:
            raise ValueError

        goal_id = int(goal_id)

        if goal_id <= 0:
            raise ValueError

    except (ValueError, TypeError):
        return "Invalid month or savings goal.", 400

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        # START TRANSACTION
        connection.start_transaction()

        # FETCH MONTHLY BUDGET
        cursor.execute("""
            SELECT budget_limit
            FROM monthly_budgets
            WHERE user_id = %s
              AND budget_month = %s
            FOR UPDATE
        """, (user_id, selected_month))

        budget = cursor.fetchone()

        if not budget:
            connection.rollback()
            flash("Please set a monthly budget first.", "warning")

            return redirect(url_for(
                "budget_settings",
                month=selected_month
            ))

        budget_limit = float(budget["budget_limit"])

        # CALCULATE TOTAL MONTHLY EXPENSES
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total_expenses
            FROM transactions
            WHERE user_id = %s
              AND LOWER(type) = 'expense'
              AND COALESCE(
                  budget_month,
                  DATE_FORMAT(transaction_date, '%Y-%m')
              ) = %s
        """, (user_id, selected_month))

        expense_result = cursor.fetchone()

        total_expenses = float(
            expense_result["total_expenses"]
        )

        remaining = round(
            budget_limit - total_expenses,
            2
        )

        if remaining <= 0:
            connection.rollback()

            flash(
                "There is no remaining budget available to transfer.",
                "warning"
            )

            return redirect(url_for(
                "budget_settings",
                month=selected_month
            ))

        # FETCH AND LOCK THE SELECTED SAVINGS GOAL
        cursor.execute("""
            SELECT
                id,
                goal_name,
                target_amount,
                saved_amount
            FROM savings_goals
            WHERE id = %s
              AND user_id = %s
            FOR UPDATE
        """, (goal_id, user_id))

        goal = cursor.fetchone()

        if not goal:
            connection.rollback()

            flash("Selected savings goal was not found.", "error")

            return redirect(url_for(
                "budget_settings",
                month=selected_month
            ))

        target_amount = float(goal["target_amount"])
        saved_amount = float(goal["saved_amount"])

        goal_remaining = round(
            target_amount - saved_amount,
            2
        )

        if goal_remaining <= 0:
            connection.rollback()

            flash(
                "This savings goal is already completed.",
                "info"
            )

            return redirect(url_for(
                "budget_settings",
                month=selected_month
            ))

        # TRANSFER ONLY THE AMOUNT THE GOAL NEEDS
        transfer_amount = round(
            min(remaining, goal_remaining),
            2
        )

        if transfer_amount <= 0:
            connection.rollback()

            flash("No amount is available to transfer.", "warning")

            return redirect(url_for(
                "budget_settings",
                month=selected_month
            ))

        # UPDATE SAVINGS GOAL
        cursor.execute("""
            UPDATE savings_goals
            SET saved_amount = saved_amount + %s
            WHERE id = %s
              AND user_id = %s
        """, (
            transfer_amount,
            goal_id,
            user_id
        ))

        # RECORD THE TRANSFER AS AN EXPENSE
        # IN THE SELECTED MONTH
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
            "Remaining budget transferred to " + goal["goal_name"],
            transfer_amount,
            date.today(),
            selected_month
        ))

        # SAVE BOTH CHANGES TOGETHER
        connection.commit()

        flash(
            f"₹{transfer_amount:,.2f} transferred successfully "
            f"to {goal['goal_name']}!",
            "success"
        )

    except Exception:
        connection.rollback()
        raise

    finally:
        if cursor:
            cursor.close()

        connection.close()

    return redirect(url_for(
        "budget_settings",
        month=selected_month
    ))
    # ==========================================
# TWO-MONTH COMPARISON
# ==========================================

@app.route("/compare-months")
@login_required
def compare_months():

    today = date.today()
    current_month = today.strftime("%Y-%m")

    if today.month == 1:
        previous_month = f"{today.year - 1}-12"
    else:
        previous_month = f"{today.year}-{today.month - 1:02d}"

    month1 = request.args.get("month1", previous_month)
    month2 = request.args.get("month2", current_month)

    try:
        month1_date = datetime.strptime(month1, "%Y-%m").date()
        month2_date = datetime.strptime(month2, "%Y-%m").date()

        if (
            month1_date.strftime("%Y-%m") != month1
            or month2_date.strftime("%Y-%m") != month2
        ):
            raise ValueError

    except ValueError:
        return "Invalid month format", 400

    connection = get_db_connection()
    cursor = None
    comparison = []

    try:
        cursor = connection.cursor(dictionary=True)

        for month, month_date in [
            (month1, month1_date),
            (month2, month2_date)
        ]:

            cursor.execute("""
                SELECT
                    COALESCE(
                        SUM(
                            CASE
                                WHEN LOWER(type) = 'income'
                                THEN amount
                                ELSE 0
                            END
                        ), 0
                    ) AS total_income,

                    COALESCE(
                        SUM(
                            CASE
                                WHEN LOWER(type) = 'expense'
                                THEN amount
                                ELSE 0
                            END
                        ), 0
                    ) AS total_expenses

                FROM transactions
                WHERE user_id = %s
                  AND COALESCE(
                      NULLIF(budget_month, ''),
                      DATE_FORMAT(transaction_date, '%Y-%m')
                  ) = %s
            """, (session["user_id"], month))

            totals = cursor.fetchone()

            cursor.execute("""
                SELECT budget_limit
                FROM monthly_budgets
                WHERE user_id = %s
                  AND budget_month = %s
            """, (session["user_id"], month))

            budget = cursor.fetchone()

            total_income = float(totals["total_income"])
            total_expenses = float(totals["total_expenses"])

            budget_limit = (
                float(budget["budget_limit"]) if budget else 0
            )

            comparison.append({
                "month": month,
                "total_income": total_income,
                "total_expenses": total_expenses,
                "balance": total_income - total_expenses,
                "budget_limit": budget_limit,
                "remaining_budget": budget_limit - total_expenses
            })

    finally:
        if cursor:
            cursor.close()

        connection.close()

    expense_difference = (
        comparison[1]["total_expenses"]
        - comparison[0]["total_expenses"]
    )

    if expense_difference > 0:
        expense_message = (
            f"Expenses increased by ₹{expense_difference:,.2f}"
        )

    elif expense_difference < 0:
        expense_message = (
            f"Expenses decreased by ₹{abs(expense_difference):,.2f}"
        )

    else:
        expense_message = "Expenses remained the same"

    return render_template(
        "compare_months.html",
        month1=month1,
        month2=month2,
        comparison=comparison,
        expense_difference=expense_difference,
        expense_message=expense_message
    )


# ==========================================
# ALL TRANSACTIONS PAGE
# ==========================================

@app.route("/transactions")
@login_required
def transactions_page():

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                id,
                type,
                description,
                category,
                amount,
                transaction_date
            FROM transactions
            WHERE user_id = %s
            ORDER BY transaction_date DESC, id DESC
        """, (session["user_id"],))

        transactions = cursor.fetchall()

        return render_template(
            "transactions.html",
            transactions=transactions
        )

    finally:
        if cursor:
            cursor.close()

        connection.close()


# ==========================================
# CATEGORY BUDGETS
# ==========================================

@app.route("/category-budgets", methods=["GET", "POST"])
@login_required
def category_budgets():

    user_id = session["user_id"]
    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        if request.method == "POST":

            month = request.form.get(
                "budget_month", ""
            ).strip()

            category = request.form.get(
                "category", ""
            ).strip()

            limit_value = request.form.get("budget_limit", "")

            try:
                parsed_month = datetime.strptime(month, "%Y-%m")

                if parsed_month.strftime("%Y-%m") != month:
                    raise ValueError

                budget_limit = float(limit_value)

                if (
                    not category
                    or not math.isfinite(budget_limit)
                    or budget_limit <= 0
                ):
                    raise ValueError

            except (ValueError, TypeError):
                return (
                    "Please enter a valid month, category "
                    "and positive budget.",
                    400
                )

            cursor.execute("""
                INSERT INTO category_budgets
                    (user_id, budget_month, category, budget_limit)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    budget_limit = VALUES(budget_limit)
            """, (user_id, month, category, budget_limit))

            connection.commit()

            return redirect(url_for(
                "category_budgets",
                month=month
            ))

        selected_month = request.args.get(
            "month", date.today().strftime("%Y-%m")
        )

        parsed_month = datetime.strptime(
            selected_month, "%Y-%m"
        )

        if parsed_month.strftime("%Y-%m") != selected_month:
            raise ValueError

        cursor.execute("""
            SELECT
                b.id,
                b.category,
                b.budget_limit,
                COALESCE(SUM(t.amount), 0) AS spent

            FROM category_budgets b

            LEFT JOIN transactions t
                ON t.user_id = b.user_id
                AND LOWER(t.category) = LOWER(b.category)
                AND LOWER(t.type) = 'expense'
                AND COALESCE(
                    t.budget_month,
                    DATE_FORMAT(t.transaction_date, '%Y-%m')
                ) = b.budget_month

            WHERE b.user_id = %s
              AND b.budget_month = %s

            GROUP BY
                b.id,
                b.category,
                b.budget_limit

            ORDER BY b.category
        """, (user_id, selected_month))

        budgets = cursor.fetchall()

        for budget in budgets:

            budget["remaining"] = (
                float(budget["budget_limit"])
                - float(budget["spent"])
            )

            budget["exceeded"] = (
                float(budget["spent"])
                > float(budget["budget_limit"])
            )

        return render_template(
            "category_budgets.html",
            budgets=budgets,
            selected_month=selected_month
        )

    except ValueError:
        return "Invalid month format. Use YYYY-MM.", 400

    finally:
        if cursor:
            cursor.close()

        connection.close()


# ==========================================
# EDIT CATEGORY BUDGET
# ==========================================

@app.route(
    "/category-budgets/edit/<int:budget_id>",
    methods=["GET", "POST"]
)
@login_required
def edit_category_budget(budget_id):

    user_id = session["user_id"]
    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, budget_month, category, budget_limit
            FROM category_budgets
            WHERE id = %s AND user_id = %s
        """, (budget_id, user_id))

        budget = cursor.fetchone()

        if not budget:
            return "Category budget not found.", 404

        month = str(budget["budget_month"])[:7]

        if request.method == "POST":

            try:
                budget_limit = float(
                    request.form.get("budget_limit", "")
                )

                if (
                    not math.isfinite(budget_limit)
                    or budget_limit <= 0
                ):
                    raise ValueError

            except (ValueError, TypeError):
                return (
                    "Enter a valid positive budget amount.",
                    400
                )

            cursor.execute("""
                UPDATE category_budgets
                SET budget_limit = %s
                WHERE id = %s AND user_id = %s
            """, (budget_limit, budget_id, user_id))

            connection.commit()

            flash(
                "Category budget updated successfully!",
                "success"
            )

            return redirect(url_for(
                "category_budgets",
                month=month
            ))

        return render_template(
            "edit_category_budget.html",
            budget=budget
        )

    finally:
        if cursor:
            cursor.close()

        connection.close()


# ==========================================
# DELETE CATEGORY BUDGET
# ==========================================

@app.route(
    "/category-budgets/delete/<int:budget_id>",
    methods=["POST"]
)
@login_required
def delete_category_budget(budget_id):

    user_id = session["user_id"]
    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT budget_month
            FROM category_budgets
            WHERE id = %s AND user_id = %s
        """, (budget_id, user_id))

        budget = cursor.fetchone()

        if not budget:
            return "Category budget not found.", 404

        month = str(budget["budget_month"])[:7]

        cursor.execute("""
            DELETE FROM category_budgets
            WHERE id = %s AND user_id = %s
        """, (budget_id, user_id))

        connection.commit()

        flash(
            "Category budget deleted successfully!",
            "success"
        )

        return redirect(url_for(
            "category_budgets",
            month=month
        ))

    finally:
        if cursor:
            cursor.close()

        connection.close()


# ==========================================
# SMART MONEY PLANNER
# ==========================================

def get_next_month(month):

    month_date = datetime.strptime(
        month, "%Y-%m"
    ).date()

    if month_date.month == 12:
        return f"{month_date.year + 1}-01"

    return f"{month_date.year}-{month_date.month + 1:02d}"


@app.route("/money-planner")
@login_required
def money_planner():

    user_id = session["user_id"]

    selected_month = request.args.get(
        "month", date.today().strftime("%Y-%m")
    )

    try:
        parsed_selected_month = datetime.strptime(
            selected_month, "%Y-%m"
        )

        if parsed_selected_month.strftime("%Y-%m") != selected_month:
            raise ValueError

    except ValueError:
        return "Invalid month format.", 400

    next_month = get_next_month(selected_month)

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                b.id,
                b.category,
                b.budget_limit,
                COALESCE(SUM(t.amount), 0) AS spent

            FROM category_budgets b

            LEFT JOIN transactions t
                ON t.user_id = b.user_id
                AND LOWER(t.type) = 'expense'
                AND LOWER(t.category) = LOWER(b.category)
                AND COALESCE(
                    t.budget_month,
                    DATE_FORMAT(t.transaction_date, '%Y-%m')
                ) = b.budget_month

            WHERE b.user_id = %s
              AND b.budget_month = %s

            GROUP BY
                b.id, b.category, b.budget_limit

            ORDER BY b.category
        """, (user_id, selected_month))

        budgets = cursor.fetchall()

        for item in budgets:

            item["budget_limit"] = float(item["budget_limit"])
            item["spent"] = float(item["spent"])

            item["remaining"] = (
                item["budget_limit"] - item["spent"]
            )

            item["unused"] = max(0, item["remaining"])
            item["overspent"] = max(0, -item["remaining"])

            cursor.execute("""
                SELECT id, adjustment_type, amount, status
                FROM money_adjustments
                WHERE user_id = %s
                  AND source_month = %s
                  AND category = %s
            """, (
                user_id,
                selected_month,
                item["category"]
            ))

            item["adjustment"] = cursor.fetchone()

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total_income
            FROM transactions
            WHERE user_id = %s
              AND LOWER(type) = 'income'
              AND COALESCE(
                  NULLIF(budget_month, ''),
                  DATE_FORMAT(transaction_date, '%Y-%m')
              ) = %s
        """, (user_id, selected_month))

        income = float(
            cursor.fetchone()["total_income"]
        )

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total_expenses
            FROM transactions
            WHERE user_id = %s
              AND LOWER(type) = 'expense'
              AND COALESCE(
                  budget_month,
                  DATE_FORMAT(transaction_date, '%Y-%m')
              ) = %s
        """, (user_id, selected_month))

        expenses = float(
            cursor.fetchone()["total_expenses"]
        )

        cursor.execute("""
            SELECT *
            FROM money_adjustments
            WHERE user_id = %s
              AND source_month = %s
            ORDER BY created_at DESC
        """, (user_id, selected_month))

        adjustments = cursor.fetchall()

        cursor.execute("""
            SELECT *
            FROM budget_suggestions
            WHERE user_id = %s
              AND suggestion_month = %s
              AND status = 'pending'
            ORDER BY created_at DESC
        """, (user_id, next_month))

        pending_suggestions = cursor.fetchall()

        return render_template(
            "money_planner.html",
            selected_month=selected_month,
            next_month=next_month,
            budgets=budgets,
            income=income,
            expenses=expenses,
            adjustments=adjustments,
            pending_suggestions=pending_suggestions
        )

    finally:
        if cursor:
            cursor.close()

        connection.close()


# ==========================================
# UNUSED MONEY DECISION
# ==========================================

@app.route(
    "/money-planner/unused/<int:budget_id>",
    methods=["POST"]
)
@login_required
def handle_unused_money(budget_id):

    user_id = session["user_id"]

    action = request.form.get("action")
    source_month = request.form.get("month", "").strip()

    if action not in [
        "carry_forward",
        "savings",
        "leave_unused"
    ]:
        return "Invalid choice.", 400

    try:
        parsed_month = datetime.strptime(
            source_month, "%Y-%m"
        )

        if parsed_month.strftime("%Y-%m") != source_month:
            raise ValueError

    except ValueError:
        return "Invalid month.", 400

    target_month = get_next_month(source_month)

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                b.id,
                b.category,
                b.budget_limit,
                COALESCE(SUM(t.amount), 0) AS spent

            FROM category_budgets b

            LEFT JOIN transactions t
                ON t.user_id = b.user_id
                AND LOWER(t.type) = 'expense'
                AND LOWER(t.category) = LOWER(b.category)
                AND COALESCE(
                    t.budget_month,
                    DATE_FORMAT(t.transaction_date, '%Y-%m')
                ) = b.budget_month

            WHERE b.id = %s
              AND b.user_id = %s
              AND b.budget_month = %s

            GROUP BY b.id, b.category, b.budget_limit
            FOR UPDATE
        """, (budget_id, user_id, source_month))

        budget = cursor.fetchone()

        if not budget:
            return "Budget not found.", 404

        budget_limit = float(budget["budget_limit"])
        spent = float(budget["spent"])

        unused = round(budget_limit - spent, 2)

        if unused <= 0:
            return "There is no unused budget to adjust.", 400

        category = budget["category"]

        cursor.execute("""
            SELECT id
            FROM money_adjustments
            WHERE user_id = %s
              AND source_month = %s
              AND target_month = %s
              AND category = %s
        """, (
            user_id,
            source_month,
            target_month,
            category
        ))

        if cursor.fetchone():
            return (
                "You have already made a decision "
                "for this category.",
                400
            )

        if action == "carry_forward":

            cursor.execute("""
                INSERT INTO category_budgets
                    (user_id, budget_month, category, budget_limit)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    budget_limit = budget_limit + VALUES(budget_limit)
            """, (
                user_id,
                target_month,
                category,
                unused
            ))

            reason = (
                f"Unused {category} budget carried forward "
                f"from {source_month}."
            )

        elif action == "savings":

            reason = (
                f"Unused {category} budget moved to savings "
                f"from {source_month}."
            )

        else:

            reason = (
                f"Unused {category} budget left unallocated "
                f"from {source_month}."
            )

        cursor.execute("""
            INSERT INTO money_adjustments
                (user_id, source_month, target_month,
                 category, adjustment_type, amount,
                 status, reason)
            VALUES (%s, %s, %s, %s, %s, %s, 'completed', %s)
        """, (
            user_id,
            source_month,
            target_month,
            category,
            action,
            unused,
            reason
        ))

        connection.commit()

        flash(
            "Your unused budget decision has been saved.",
            "success"
        )

        return redirect(url_for(
            "money_planner",
            month=source_month
        ))

    except Exception:
        connection.rollback()
        raise

    finally:
        if cursor:
            cursor.close()

        connection.close()


# ==========================================
# GENERATE OVERSPENDING APPROVAL SUGGESTIONS
# ==========================================

@app.route(
    "/money-planner/generate",
    methods=["POST"]
)
@login_required
def generate_money_suggestions():

    user_id = session["user_id"]

    source_month = request.form.get(
        "month", ""
    ).strip()

    try:
        parsed_month = datetime.strptime(
            source_month, "%Y-%m"
        )

        if parsed_month.strftime("%Y-%m") != source_month:
            raise ValueError

    except ValueError:
        return "Invalid month.", 400

    target_month = get_next_month(source_month)

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                b.category,
                b.budget_limit,
                COALESCE(SUM(t.amount), 0) AS spent

            FROM category_budgets b

            LEFT JOIN transactions t
                ON t.user_id = b.user_id
                AND LOWER(t.type) = 'expense'
                AND LOWER(t.category) = LOWER(b.category)
                AND COALESCE(
                    NULLIF(t.budget_month, ''),
                    DATE_FORMAT(t.transaction_date, '%Y-%m')
                ) = b.budget_month

            WHERE b.user_id = %s
              AND b.budget_month = %s

            GROUP BY b.category, b.budget_limit
        """, (user_id, source_month))

        budgets = cursor.fetchall()

        created = 0

        for budget in budgets:

            overspent = (
                float(budget["spent"])
                - float(budget["budget_limit"])
            )

            if overspent <= 0:
                continue

            category = budget["category"]

            cursor.execute("""
                SELECT budget_limit
                FROM category_budgets
                WHERE user_id = %s
                  AND budget_month = %s
                  AND LOWER(category) = LOWER(%s)
            """, (user_id, target_month, category))

            next_budget = cursor.fetchone()

            if next_budget:
                current_next_budget = float(
                    next_budget["budget_limit"]
                )
            else:
                current_next_budget = float(
                    budget["budget_limit"]
                )

            suggested = round(
                current_next_budget + overspent,
                2
            )

            cursor.execute("""
                SELECT id
                FROM budget_suggestions
                WHERE user_id = %s
                  AND suggestion_month = %s
                  AND category = %s
                  AND trigger_type = 'overspending_carry_forward'
                  AND status = 'pending'
            """, (
                user_id,
                target_month,
                category
            ))

            existing = cursor.fetchone()

            reason = (
                f"{category} exceeded its {source_month} "
                f"budget by ₹{overspent:.2f}. "
                f"We suggest adjusting the {target_month} "
                f"budget. Approve or reject this change."
            )

            if existing:

                cursor.execute("""
                    UPDATE budget_suggestions
                    SET current_budget = %s,
                        suggested_budget = %s,
                        reason = %s
                    WHERE id = %s
                      AND user_id = %s
                """, (
                    current_next_budget,
                    suggested,
                    reason,
                    existing["id"],
                    user_id
                ))

                continue

            cursor.execute("""
                INSERT INTO budget_suggestions
                    (
                        user_id,
                        suggestion_month,
                        category,
                        current_budget,
                        suggested_budget,
                        reason,
                        trigger_type
                    )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id,
                target_month,
                category,
                current_next_budget,
                suggested,
                reason,
                "overspending_carry_forward"
            ))

            created += 1

        connection.commit()

        flash(
            f"{created} overspending suggestion(s) created. "
            "Review them in Smart Budget.",
            "success"
        )

        return redirect(url_for(
            "money_planner",
            month=source_month
        ))

    except Exception:
        connection.rollback()
        raise

    finally:
        if cursor:
            cursor.close()

        connection.close()


# ==========================================
# SMART BUDGET PLANNER
# ==========================================

@app.route("/smart-budget", methods=["GET", "POST"])
@login_required
def smart_budget():

    user_id = session["user_id"]

    today = date.today()
    current_month = today.strftime("%Y-%m")
    month_date = today.replace(day=1)

    # PREVIOUS MONTH
    if month_date.month == 1:
        previous_month = f"{month_date.year - 1}-12"
    else:
        previous_month = (
            f"{month_date.year}-{month_date.month - 1:02d}"
        )

    # NEXT MONTH
    if month_date.month == 12:
        next_month_date = date(
            month_date.year + 1, 1, 1
        )
    else:
        next_month_date = date(
            month_date.year, month_date.month + 1, 1
        )

    next_month = next_month_date.strftime("%Y-%m")

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        # SAVE MONTHLY SALARY
        if request.method == "POST":

            try:
                salary = float(
                    request.form.get("salary", "")
                )

                if not math.isfinite(salary) or salary <= 0:
                    raise ValueError

            except (ValueError, TypeError):
                return "Enter a valid positive salary.", 400

            cursor.execute("""
                INSERT INTO monthly_salary_plans
                    (user_id, plan_month, salary)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    salary = VALUES(salary)
            """, (user_id, current_month, salary))

            connection.commit()

            # FETCH PREVIOUS MONTH SALARY
            cursor.execute("""
                SELECT salary
                FROM monthly_salary_plans
                WHERE user_id = %s
                  AND plan_month = %s
            """, (user_id, previous_month))

            previous_result = cursor.fetchone()

            previous_salary = (
                float(previous_result["salary"])
                if previous_result else 0
            )

            # FETCH CURRENT CATEGORY BUDGETS
            cursor.execute("""
                SELECT category, budget_limit
                FROM category_budgets
                WHERE user_id = %s
                  AND budget_month = %s
            """, (user_id, current_month))

            budget_rows = cursor.fetchall()

            current_budgets = {
                row["category"]: float(row["budget_limit"])
                for row in budget_rows
            }

            # SAVE SUGGESTION HELPER
            def save_suggestion(
                category,
                current_budget,
                suggested_budget,
                reason,
                trigger_type,
                target_month=current_month
            ):

                if suggested_budget < 0:
                    return

                cursor.execute("""
                    SELECT id
                    FROM budget_suggestions
                    WHERE user_id = %s
                      AND suggestion_month = %s
                      AND category = %s
                      AND trigger_type = %s
                      AND status = 'pending'
                """, (
                    user_id,
                    target_month,
                    category,
                    trigger_type
                ))

                existing = cursor.fetchone()

                if existing:

                    cursor.execute("""
                        UPDATE budget_suggestions
                        SET current_budget = %s,
                            suggested_budget = %s,
                            reason = %s
                        WHERE id = %s
                          AND user_id = %s
                    """, (
                        current_budget,
                        suggested_budget,
                        reason,
                        existing["id"],
                        user_id
                    ))

                else:

                    cursor.execute("""
                        INSERT INTO budget_suggestions
                            (
                                user_id,
                                suggestion_month,
                                category,
                                current_budget,
                                suggested_budget,
                                reason,
                                trigger_type
                            )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        user_id,
                        target_month,
                        category,
                        current_budget,
                        suggested_budget,
                        reason,
                        trigger_type
                    ))

            # 1. SALARY CHANGE DETECTION
            salary_change = detect_salary_change(
                salary,
                previous_salary
            )

            if (
                salary_change
                and previous_salary > 0
                and current_budgets
            ):

                for category, budget in current_budgets.items():

                    suggested = round(
                        budget * salary / previous_salary,
                        2
                    )

                    save_suggestion(
                        category,
                        budget,
                        suggested,
                        (
                            salary_change["reason"]
                            + " Salary changed by "
                            + f'{salary_change["percentage"]}%.'
                        ),
                        salary_change["type"]
                    )

            # 2. FETCH LAST THREE MONTHS EXPENSES
            cursor.execute("""
                SELECT
                    category,
                    DATE_FORMAT(
                        transaction_date, '%Y-%m'
                    ) AS expense_month,
                    SUM(amount) AS total_spending

                FROM transactions

                WHERE user_id = %s
                  AND LOWER(type) = 'expense'
                  AND transaction_date >= DATE_SUB(
                      %s, INTERVAL 3 MONTH
                  )
                  AND transaction_date < %s

                GROUP BY category, expense_month
                ORDER BY expense_month
            """, (
                user_id,
                month_date,
                month_date
            ))

            spending_rows = cursor.fetchall()

            spending_history = {}
            category_names = {}

            for row in spending_rows:

                original_category = row["category"] or "Other"
                normalized = original_category.strip().lower()

                category_names[normalized] = original_category

                spending_history.setdefault(
                    normalized, []
                ).append(
                    float(row["total_spending"])
                )

            normalized_budgets = {
                category.strip().lower(): budget
                for category, budget in current_budgets.items()
            }

            # 3. DETECT REPEATED OVERSPENDING
            pattern_suggestions = detect_spending_patterns(
                spending_history,
                normalized_budgets
            )

            for item in pattern_suggestions:

                category = category_names.get(
                    item["category"],
                    item["category"]
                )

                save_suggestion(
                    category,
                    item["current_budget"],
                    item["suggested_budget"],
                    item["reason"],
                    item["trigger_type"]
                )

            # 4. DETECT GROCERY SPENDING INCREASE
            grocery_history = {}

            for category, amounts in spending_history.items():

                if "grocery" in category:
                    grocery_history["grocery"] = amounts

            grocery_budgets = {}

            for category, budget in normalized_budgets.items():

                if "grocery" in category:
                    grocery_budgets["grocery"] = budget

            grocery_suggestions = detect_grocery_increase(
                grocery_history,
                grocery_budgets
            )

            for item in grocery_suggestions:

                grocery_category = next(
                    (
                        name for name in current_budgets
                        if "grocery" in name.lower()
                    ),
                    "Grocery"
                )

                save_suggestion(
                    grocery_category,
                    item["current_budget"],
                    item["suggested_budget"],
                    item["reason"],
                    item["trigger_type"]
                )

            # 5. GROCERY STOCK VALUE CALCULATION
            ensure_grocery_table(cursor)

            cursor.execute("""
                SELECT category, budget_limit
                FROM category_budgets
                WHERE user_id = %s
                  AND budget_month = %s
                  AND LOWER(category) LIKE '%grocery%'
                ORDER BY category
                LIMIT 1
            """, (user_id, next_month))

            next_grocery_budget = cursor.fetchone()

            cursor.execute("""
                SELECT category, budget_limit
                FROM category_budgets
                WHERE user_id = %s
                  AND budget_month = %s
                  AND LOWER(category) LIKE '%grocery%'
                ORDER BY category
                LIMIT 1
            """, (user_id, current_month))

            current_grocery_budget = cursor.fetchone()

            grocery_budget_row = (
                next_grocery_budget
                or current_grocery_budget
            )

            cursor.execute("""
                SELECT
                    COALESCE(
                        SUM(remaining_quantity * unit_price),
                        0
                    ) AS stock_value
                FROM grocery_purchases
                WHERE user_id = %s
                  AND intended_month = %s
                  AND remaining_quantity > 0
            """, (user_id, next_month))

            stock_result = cursor.fetchone()

            remaining_stock_value = float(
                stock_result["stock_value"] or 0
            )

            # 6. GENERATE NEXT MONTH GROCERY SUGGESTION
            if grocery_budget_row and remaining_stock_value > 0:

                grocery_category = grocery_budget_row["category"]

                base_grocery_budget = float(
                    grocery_budget_row["budget_limit"]
                )

                suggested_grocery_budget = round(
                    max(
                        0.01,
                        base_grocery_budget - remaining_stock_value
                    ),
                    2
                )

                if suggested_grocery_budget < base_grocery_budget:

                    reason = (
                        f"Your next month's grocery budget is "
                        f"₹{base_grocery_budget:,.2f}. "
                        f"Your remaining grocery stock is worth "
                        f"₹{remaining_stock_value:,.2f}. "
                        f"Therefore, the suggested grocery budget "
                        f"is ₹{suggested_grocery_budget:,.2f}."
                    )

                    save_suggestion(
                        grocery_category,
                        base_grocery_budget,
                        suggested_grocery_budget,
                        reason,
                        "grocery_stock_adjustment",
                        next_month
                    )

            connection.commit()

            flash(
                "Salary saved and budget suggestions generated!",
                "success"
            )

        # FETCH CURRENT MONTH SALARY
        cursor.execute("""
            SELECT salary
            FROM monthly_salary_plans
            WHERE user_id = %s
              AND plan_month = %s
        """, (user_id, current_month))

        salary_result = cursor.fetchone()

        current_salary = (
            float(salary_result["salary"])
            if salary_result else None
        )

        # FETCH ALL FUTURE PENDING SUGGESTIONS
        cursor.execute("""
            SELECT *
            FROM budget_suggestions
            WHERE user_id = %s
              AND suggestion_month >= %s
              AND status = 'pending'
            ORDER BY suggestion_month, created_at DESC
        """, (
            user_id,
            current_month
        ))

        suggestions = cursor.fetchall()

        return render_template(
            "smart_budget.html",
            current_salary=current_salary,
            suggestions=suggestions
        )

    finally:
        if cursor:
            cursor.close()

        connection.close()


# ==========================================
# APPROVE / REJECT BUDGET SUGGESTION
# ==========================================

@app.route(
    "/smart-budget/suggestion/<int:suggestion_id>",
    methods=["POST"]
)
@login_required
def handle_suggestion(suggestion_id):

    user_id = session["user_id"]
    action = request.form.get("action")

    if action not in ["approve", "reject"]:
        return "Invalid action.", 400

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT *
            FROM budget_suggestions
            WHERE id = %s
              AND user_id = %s
              AND status = 'pending'
        """, (suggestion_id, user_id))

        suggestion = cursor.fetchone()

        if not suggestion:
            return "Suggestion not found.", 404

        if action == "approve":

            try:
                new_budget = float(
                    request.form.get("suggested_budget", "")
                )

                if not math.isfinite(new_budget) or new_budget < 0:
                    raise ValueError

            except (ValueError, TypeError):
                return "Enter a valid non-negative budget.", 400

            cursor.execute("""
                INSERT INTO category_budgets
                    (user_id, budget_month, category, budget_limit)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    budget_limit = VALUES(budget_limit)
            """, (
                user_id,
                suggestion["suggestion_month"],
                suggestion["category"],
                new_budget
            ))

            cursor.execute("""
                UPDATE budget_suggestions
                SET suggested_budget = %s,
                    status = 'approved'
                WHERE id = %s AND user_id = %s
            """, (new_budget, suggestion_id, user_id))

            flash("Budget suggestion approved!", "success")

        else:

            cursor.execute("""
                UPDATE budget_suggestions
                SET status = 'rejected'
                WHERE id = %s AND user_id = %s
            """, (suggestion_id, user_id))

            flash("Budget suggestion rejected.", "info")

        connection.commit()

        return redirect(url_for("smart_budget"))

    except Exception:
        connection.rollback()
        raise

    finally:
        if cursor:
            cursor.close()

        connection.close()


# ==========================================
# GROCERY INVENTORY MANAGER
# ==========================================

def ensure_grocery_table(cursor):

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS grocery_purchases (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            item_name VARCHAR(150) NOT NULL,
            purchased_quantity DECIMAL(12,3) NOT NULL,
            remaining_quantity DECIMAL(12,3) NOT NULL,
            unit VARCHAR(30) DEFAULT 'item',
            unit_price DECIMAL(12,2) NOT NULL,
            purchase_date DATE NOT NULL,
            intended_month CHAR(7) NOT NULL,
            expiry_date DATE NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_grocery_user (user_id)
        ) ENGINE=InnoDB
    """)


# ==========================================
# GROCERY MANAGER ROUTE
# ==========================================

@app.route("/grocery", methods=["GET", "POST"])
@login_required
def grocery_manager():

    user_id = session["user_id"]
    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        ensure_grocery_table(cursor)

        # ADD GROCERY PURCHASE
        if request.method == "POST":

            item = request.form.get(
                "item_name", ""
            ).strip()

            unit = request.form.get(
                "unit", "item"
            ).strip()

            try:
                quantity = float(
                    request.form.get("quantity", "")
                )

                total_price = float(
                    request.form.get("total_price", "")
                )

                purchase_date = request.form.get("purchase_date")
                intended_month = request.form.get("intended_month")
                expiry_date = request.form.get("expiry_date") or None

                if (
                    not item
                    or quantity <= 0
                    or total_price < 0
                    or not math.isfinite(quantity)
                    or not math.isfinite(total_price)
                ):
                    raise ValueError

                datetime.strptime(purchase_date, "%Y-%m-%d")
                datetime.strptime(intended_month, "%Y-%m")

                if expiry_date:
                    datetime.strptime(expiry_date, "%Y-%m-%d")

            except (ValueError, TypeError):
                flash(
                    "Please enter valid grocery details.",
                    "error"
                )

                return redirect(url_for("grocery_manager"))

            unit_price = total_price / quantity

            # RECORD PURCHASE AS EXPENSE
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
                VALUES (%s, 'expense', %s, %s, %s, 'Grocery', %s)
            """, (
                user_id,
                "Grocery purchase: " + item,
                total_price,
                purchase_date,
                intended_month
            ))

            # SAVE GROCERY INVENTORY
            cursor.execute("""
                INSERT INTO grocery_purchases
                (
                    user_id,
                    item_name,
                    purchased_quantity,
                    remaining_quantity,
                    unit,
                    unit_price,
                    purchase_date,
                    intended_month,
                    expiry_date
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id,
                item,
                quantity,
                quantity,
                unit,
                unit_price,
                purchase_date,
                intended_month,
                expiry_date
            ))

            connection.commit()

            flash(
                "Grocery purchase saved successfully!",
                "success"
            )

            return redirect(url_for("grocery_manager"))

        # FETCH GROCERY ITEMS
        cursor.execute("""
            SELECT *
            FROM grocery_purchases
            WHERE user_id = %s
            ORDER BY expiry_date ASC, purchase_date DESC
        """, (user_id,))

        items = cursor.fetchall()

        # LOW STOCK DETECTION
        low_stock = [
            item for item in items
            if (
                0 < float(item["remaining_quantity"])
                <= float(item["purchased_quantity"]) * 0.20
            )
        ]

        today = date.today()

        # EXPIRY DETECTION
        expiring = [
            item for item in items
            if (
                item["expiry_date"]
                and item["remaining_quantity"] > 0
                and 0 <= (item["expiry_date"] - today).days <= 7
            )
        ]

        # TOTAL REMAINING STOCK VALUE
        total_stock_value = sum(
            float(item["remaining_quantity"])
            * float(item["unit_price"])
            for item in items
        )

        # MONTH-WISE PLANNED STOCK
        cursor.execute("""
            SELECT
                intended_month,
                SUM(remaining_quantity * unit_price) AS stock_value
            FROM grocery_purchases
            WHERE user_id = %s
              AND remaining_quantity > 0
            GROUP BY intended_month
            ORDER BY intended_month
        """, (user_id,))

        planned_stock = cursor.fetchall()

        return render_template(
            "grocery_manager.html",
            items=items,
            low_stock=low_stock,
            expiring=expiring,
            total_stock_value=total_stock_value,
            planned_stock=planned_stock,
            today=today.isoformat(),
            current_month=today.strftime("%Y-%m")
        )

    except Exception:
        connection.rollback()
        raise

    finally:
        if cursor:
            cursor.close()

        connection.close()


# ==========================================
# CONSUME GROCERY STOCK
# ==========================================

@app.route("/grocery/use/<int:item_id>", methods=["POST"])
@login_required
def consume_grocery(item_id):

    user_id = session["user_id"]

    try:
        used_quantity = float(
            request.form.get("used_quantity", "")
        )

        if (
            not math.isfinite(used_quantity)
            or used_quantity <= 0
        ):
            raise ValueError

    except (ValueError, TypeError):
        flash(
            "Enter a valid consumed quantity.",
            "error"
        )

        return redirect(url_for("grocery_manager"))

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT remaining_quantity
            FROM grocery_purchases
            WHERE id = %s
              AND user_id = %s
            FOR UPDATE
        """, (item_id, user_id))

        item = cursor.fetchone()

        if not item:
            return "Grocery item not found.", 404

        remaining = float(item["remaining_quantity"])

        if used_quantity > remaining:

            flash(
                "Consumed quantity exceeds available stock.",
                "error"
            )

        else:

            cursor.execute("""
                UPDATE grocery_purchases
                SET remaining_quantity =
                    remaining_quantity - %s
                WHERE id = %s
                  AND user_id = %s
            """, (
                used_quantity,
                item_id,
                user_id
            ))

            flash("Grocery stock updated!", "success")

        connection.commit()

        return redirect(url_for("grocery_manager"))

    except Exception:
        connection.rollback()
        raise

    finally:
        if cursor:
            cursor.close()

        connection.close()


# ==========================================
# UNUSUAL EXPENSE DETECTION
# ==========================================

@app.route("/unusual-expenses")
@login_required
def unusual_expenses():

    user_id = session["user_id"]

    result = detect_unusual_expenses(user_id)

    return render_template(
        "unusual_expenses.html",
        **result
    )


# ==========================================
# SAVINGS GOALS
# ==========================================

@app.route("/savings-goals")
@login_required
def savings_goals_page():

    user_id = session["user_id"]
    goals = get_savings_goals(user_id)

    return render_template(
        "savings.html",
        goals=goals
    )


# ==========================================
# ADD SAVINGS GOAL
# ==========================================

@app.route("/add-savings-goal", methods=["POST"])
@login_required
def create_savings_goal():

    user_id = session["user_id"]

    goal_name = request.form.get("goal_name")
    target_amount = request.form.get("target_amount")
    target_date = request.form.get("target_date")

    add_savings_goal(
        user_id,
        goal_name,
        target_amount,
        target_date
    )

    return redirect(url_for("savings_goals_page"))


# ==========================================
# CONTRIBUTE SAVINGS
# ==========================================

@app.route("/add-savings/<int:goal_id>", methods=["POST"])
@login_required
def contribute_savings(goal_id):

    user_id = session["user_id"]
    amount = request.form.get("amount")

    add_savings(
        user_id,
        goal_id,
        amount
    )

    return redirect(url_for("savings_goals_page"))


# ==========================================
# DELETE SAVINGS GOAL
# ==========================================

@app.route("/delete-savings-goal/<int:goal_id>", methods=["POST"])
@login_required
def remove_savings_goal(goal_id):

    user_id = session["user_id"]

    delete_savings_goal(
        user_id,
        goal_id
    )

    return redirect(url_for("savings_goals_page"))


# ==========================================
# RUN APPLICATION
# ==========================================

if __name__ == "__main__":
    app.run(debug=True)