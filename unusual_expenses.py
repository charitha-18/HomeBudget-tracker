import statistics
from database import get_db_connection


# ==========================================
# UNUSUAL EXPENSE DETECTION
# ==========================================

MIN_HISTORY_RECORDS = 3
UNUSUAL_MULTIPLIER = 2
MINIMUM_DIFFERENCE = 500


def detect_unusual_expenses(user_id):

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                id,
                description,
                category,
                amount,
                transaction_date
            FROM transactions
            WHERE user_id = %s
              AND LOWER(TRIM(type)) = 'expense'
            ORDER BY transaction_date ASC, id ASC
        """, (user_id,))

        transactions = cursor.fetchall()

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()

    # Store earlier expense amounts category-wise.
    category_history = {}

    unusual_expenses = []
    monitored_count = 0

    total_expenses = len(transactions)

    for transaction in transactions:

        category = (
            transaction.get("category") or "Other"
        ).strip()

        normalized_category = category.lower()

        try:
            amount = float(transaction["amount"])
        except (ValueError, TypeError):
            continue

        if amount <= 0:
            continue

        # Get only previous expenses in this category.
        previous_amounts = category_history.get(
            normalized_category, []
        )

        # We need at least 3 previous transactions.
        if len(previous_amounts) >= MIN_HISTORY_RECORDS:

            monitored_count += 1

            # Median gives a stable typical spending value.
            median_amount = statistics.median(
                previous_amounts
            )

            difference = amount - median_amount

            threshold_amount = max(
                median_amount * UNUSUAL_MULTIPLIER,
                median_amount + MINIMUM_DIFFERENCE
            )

            # Check whether this expense is unusual.
            if amount > threshold_amount:

                unusual_expenses.append({
                    "id": transaction["id"],
                    "description": transaction["description"],
                    "category": category,
                    "amount": round(amount, 2),
                    "typical_amount": round(
                        median_amount, 2
                    ),
                    "difference": round(
                        difference, 2
                    ),
                    "transaction_date": transaction[
                        "transaction_date"
                    ],
                    "previous_count": len(previous_amounts),
                    "reason": (
                        f"This expense is ₹{difference:,.2f} "
                        f"higher than the typical {category} "
                        f"expense of ₹{median_amount:,.2f}."
                    )
                })

        # Add the current transaction to history only
        # after checking it against earlier transactions.
        category_history.setdefault(
            normalized_category, []
        ).append(amount)

    # Show the newest unusual expenses first.
    unusual_expenses.reverse()

    return {
        "unusual_expenses": unusual_expenses,
        "total_expenses": total_expenses,
        "monitored_count": monitored_count,
        "unusual_count": len(unusual_expenses)
    }