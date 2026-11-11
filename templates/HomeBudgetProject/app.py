from flask import Flask, render_template, request, redirect, url_for
from database import get_db_connection
from analysis import get_analysis
from datetime import date, datetime

app = Flask(__name__)


# HOME DASHBOARD
@app.route("/")
def index():
    selected_month = request.args.get("month", "all")

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        if selected_month == "all":
            cursor.execute("""
                SELECT id, type, description, amount,
                       transaction_date, category
                FROM transactions
                ORDER BY transaction_date DESC, id DESC
            """)
        else:
            try:
                month_start = datetime.strptime(
                    selected_month, "%Y-%m"
                ).date()

                if month_start.strftime("%Y-%m") != selected_month:
                    raise ValueError

            except ValueError:
                return "Invalid month format", 400

            if month_start.month == 12:
                next_month = month_start.replace(
                    year=month_start.year + 1,
                    month=1
                )
            else:
                next_month = month_start.replace(
                    month=month_start.month + 1
                )

            cursor.execute("""
                SELECT id, type, description, amount,
                       transaction_date, category
                FROM transactions
                WHERE transaction_date >= %s
                  AND transaction_date < %s
                ORDER BY transaction_date DESC, id DESC
            """, (month_start, next_month))

        transactions = cursor.fetchall()

    finally:
        if cursor:
            cursor.close()
        connection.close()

    income_transactions = [
        t for t in transactions
        if str(t["type"]).lower() == "income"
    ]

    expense_transactions = [
        t for t in transactions
        if str(t["type"]).lower() == "expense"
    ]

    total_income = sum(
        float(t["amount"]) for t in income_transactions
    )

    total_expenses = sum(
        float(t["amount"]) for t in expense_transactions
    )

    balance = total_income - total_expenses

    # Category-wise expense summary
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




# ADD TRANSACTION
@app.route("/add", methods=["POST"])
def add_transaction():
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

    if transaction_type not in ["income", "expense"]:
        return "Invalid transaction type", 400

    if not description or not transaction_date:
        return "Please fill in all fields", 400

    if not category:
        category = "Other"

    try:
        amount = float(amount)

        if amount <= 0:
            return "Amount must be greater than zero", 400

        selected_date = datetime.strptime(
            transaction_date, "%Y-%m-%d"
        ).date()

        # Save selected date with the current time
        current_time = datetime.now().time().replace(
            microsecond=0
        )

        transaction_datetime = datetime.combine(
            selected_date, current_time
        )

    except (ValueError, TypeError):
        return "Please enter a valid amount and date", 400

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO transactions
                (type, description, amount,
                 transaction_date, category)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            transaction_type,
            description,
            amount,
            transaction_datetime,
            category
        ))

        connection.commit()

    finally:
        if cursor:
            cursor.close()
        connection.close()

    return redirect(url_for("index"))


# DELETE TRANSACTION
@app.route("/delete/<int:transaction_id>", methods=["POST"])
def delete_transaction(transaction_id):
    selected_month = request.form.get("month")

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor()

        cursor.execute(
            "DELETE FROM transactions WHERE id = %s",
            (transaction_id,)
        )

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


# EDIT TRANSACTION
@app.route("/edit/<int:transaction_id>", methods=["GET", "POST"])
def edit_transaction(transaction_id):
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

            if transaction_type not in ["income", "expense"]:
                return "Invalid transaction type", 400

            if not description or not transaction_date:
                return "Please fill in all fields", 400

            if not category:
                category = "Other"

            try:
                amount = float(amount)

                if amount <= 0:
                    return "Amount must be greater than zero", 400

                selected_date = datetime.strptime(
                    transaction_date, "%Y-%m-%d"
                ).date()

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
                    category = %s
                WHERE id = %s
            """, (
                transaction_type,
                description,
                amount,
                transaction_datetime,
                category,
                transaction_id
            ))

            connection.commit()

            return redirect(url_for("index"))

        cursor.execute(
            "SELECT * FROM transactions WHERE id = %s",
            (transaction_id,)
        )

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


# ANALYSIS DASHBOARD
@app.route("/analysis")
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

    analysis = get_analysis(selected_month)

    return render_template(
        "analysis.html",
        **analysis
    )


# MONTHLY BUDGET
@app.route("/budget", methods=["GET", "POST"])
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

    # Save monthly budget
    if request.method == "POST":
        try:
            budget_limit = float(
                request.form.get("budget_limit", "")
            )

            if budget_limit <= 0:
                return "Budget must be greater than zero", 400

        except (ValueError, TypeError):
            return "Enter a valid budget amount", 400

        connection = get_db_connection()
        cursor = None

        try:
            cursor = connection.cursor()

            cursor.execute("""
                INSERT INTO monthly_budgets
                    (budget_month, budget_limit)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE
                    budget_limit = VALUES(budget_limit)
            """, (selected_month, budget_limit))

            connection.commit()

        finally:
            if cursor:
                cursor.close()
            connection.close()

        return redirect(url_for(
            "budget_settings",
            month=selected_month
        ))

    # Fetch budget and transactions
    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT budget_limit
            FROM monthly_budgets
            WHERE budget_month = %s
        """, (selected_month,))

        result = cursor.fetchone()

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total_expenses
            FROM transactions
            WHERE LOWER(type) = 'expense'
              AND transaction_date >= %s
              AND transaction_date < DATE_ADD(
                  %s, INTERVAL 1 MONTH
              )
        """, (month_date, month_date))

        expense_result = cursor.fetchone()

        cursor.execute("""
            SELECT id, type, description, category,
                   amount, transaction_date
            FROM transactions
            WHERE transaction_date >= %s
              AND transaction_date < DATE_ADD(
                  %s, INTERVAL 1 MONTH
              )
            ORDER BY transaction_date DESC, id DESC
        """, (month_date, month_date))

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

    return render_template(
        "budget.html",
        selected_month=selected_month,
        budget_limit=budget_limit,
        total_expenses=total_expenses,
        remaining=remaining,
        usage_percent=usage_percent,
        transactions=transactions
    )
    
    # TWO-MONTH COMPARISON
@app.route("/compare-months")
def compare_months():
    today = date.today()

    # Default to the current month and the previous month
    current_month = today.strftime("%Y-%m")

    if today.month == 1:
        previous_month = f"{today.year - 1}-12"
    else:
        previous_month = f"{today.year}-{today.month - 1:02d}"

    month1 = request.args.get("month1", previous_month)
    month2 = request.args.get("month2", current_month)

    # Validate the selected months
    try:
        month1_date = datetime.strptime(month1, "%Y-%m").date()
        month2_date = datetime.strptime(month2, "%Y-%m").date()

        if (month1_date.strftime("%Y-%m") != month1 or
                month2_date.strftime("%Y-%m") != month2):
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
            # Calculate the start and end dates for each month
            if month_date.month == 12:
                next_month = month_date.replace(
                    year=month_date.year + 1,
                    month=1
                )
            else:
                next_month = month_date.replace(
                    month=month_date.month + 1
                )

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

                WHERE transaction_date >= %s
                  AND transaction_date < %s
            """, (month_date, next_month))

            totals = cursor.fetchone()

            cursor.execute("""
                SELECT budget_limit
                FROM monthly_budgets
                WHERE budget_month = %s
            """, (month,))

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

    # Calculate the change in expenses between the two months
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


# ALL TRANSACTIONS PAGE
@app.route("/transactions")
def transactions_page():
    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, type, description, category,
                   amount, transaction_date
            FROM transactions
            ORDER BY transaction_date DESC, id DESC
        """)

        transactions = cursor.fetchall()

        return render_template(
            "transactions.html",
            transactions=transactions
        )

    finally:
        if cursor:
            cursor.close()
        connection.close()


if __name__ == "__main__":
    app.run(debug=True)