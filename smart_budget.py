
from collections import defaultdict


def calculate_salary_allocations(salary, current_budgets):
    """
    Suggest budget allocations based on monthly salary.
    Existing budget proportions are maintained.
    """

    if salary <= 0:
        return {}

    total_budget = sum(current_budgets.values())

    if total_budget <= 0:
        return {}

    allocations = {}

    for category, budget in current_budgets.items():
        allocations[category] = round(
            (budget / total_budget) * salary * 0.90, 2
        )

    return allocations


def detect_salary_change(current_salary, previous_salary):
    """Detect salary increase or decrease."""

    if not previous_salary or previous_salary <= 0:
        return None

    change = ((current_salary - previous_salary) / previous_salary) * 100

    if change >= 5:
        return {
            "type": "salary_increase",
            "percentage": round(change, 2),
            "reason": "Your salary increased. Consider reviewing your budgets."
        }

    if change <= -5:
        return {
            "type": "salary_decrease",
            "percentage": round(change, 2),
            "reason": "Your salary decreased. Consider adjusting flexible budgets."
        }

    return None


def detect_spending_patterns(spending_history, current_budgets):
    """
    Detect categories that exceed their budget
    in at least two of the last three months.
    """

    suggestions = []

    for category, monthly_amounts in spending_history.items():

        budget = current_budgets.get(category, 0)

        if budget <= 0 or not monthly_amounts:
            continue

        recent_months = monthly_amounts[-3:]

        exceeded = sum(amount > budget for amount in recent_months)

        if exceeded >= 2:
            average_spending = sum(recent_months) / len(recent_months)

            suggestions.append({
                "category": category,
                "current_budget": budget,
                "suggested_budget": round(average_spending * 1.10, 2),
                "reason": f"You exceeded your {category} budget in {exceeded} of the last 3 months.",
                "trigger_type": "overspending"
            })

    return suggestions


def detect_grocery_increase(spending_history, current_budgets):
    """
    Detect an increase in grocery spending.
    This detects spending changes, not actual market prices.
    """

    suggestions = []

    grocery_categories = ["grocery", "groceries"]

    for category in grocery_categories:

        amounts = spending_history.get(category, [])

        if len(amounts) < 3:
            continue

        previous_amounts = amounts[-3:-1]
        latest_amount = amounts[-1]

        previous_average = sum(previous_amounts) / len(previous_amounts)

        if previous_average <= 0:
            continue

        increase = (
            (latest_amount - previous_average) / previous_average
        ) * 100

        if increase >= 10:

            current_budget = current_budgets.get(category, 0)

            suggestions.append({
                "category": category,
                "current_budget": current_budget,
                "suggested_budget": round(latest_amount * 1.10, 2),
                "reason": (
                    f"Grocery spending increased by {round(increase, 2)}% "
                    "compared with the previous two months."
                ),
                "trigger_type": "grocery_increase"
            })

    return suggestions
