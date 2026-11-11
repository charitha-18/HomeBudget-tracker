import pandas as pd
import plotly.express as px
from database import get_db_connection


def get_analysis(user_id, selected_month="all"):

    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT type, description, amount,
                   transaction_date, category, budget_month
            FROM transactions
            WHERE user_id = %s
            ORDER BY transaction_date
        """, (user_id,))

        rows = cursor.fetchall()

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()

    df = pd.DataFrame(rows)

    # Default values when no transactions exist
    empty_result = {
        "total_income": 0,
        "total_expenses": 0,
        "balance": 0,
        "savings_rate": 0,
        "monthly_chart": None,
        "comparison_chart": None,
        "category_chart": None,
        "income_expense_trend_chart": None,
        "salary_trend_chart": None,
        "financial_insights": [
            "Add your income and expense transactions to view financial insights.",
            "Add an Income transaction with category Salary to enable salary analysis."
        ],
        "salary_change": None,
        "salary_change_percent": None,
        "latest_salary": None,
        "selected_month": selected_month
    }

    if df.empty:
        return empty_result

    # ------------------------------------------
    # 1. CLEAN AND PREPARE DATA
    # ------------------------------------------

    df["amount"] = pd.to_numeric(
        df["amount"], errors="coerce"
    ).fillna(0)

    df["type"] = (
        df["type"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    df["category"] = (
        df["category"]
        .fillna("Other")
        .astype(str)
        .str.strip()
        .replace("", "Other")
    )

    df["transaction_date"] = pd.to_datetime(
        df["transaction_date"], errors="coerce"
    )

    # Use budget_month when available.
    # Otherwise, use the transaction date.
    df["analysis_month"] = (
        df["budget_month"]
        .fillna(df["transaction_date"].dt.strftime("%Y-%m"))
        .astype(str)
    )

    invalid_months = df["analysis_month"].isin(["", "None", "nan"])
    df.loc[invalid_months, "analysis_month"] = (
        df.loc[invalid_months, "transaction_date"].dt.strftime("%Y-%m")
    )

    # Keep a copy of all transactions for monthly trends.
    all_df = df.copy()

    # ------------------------------------------
    # 2. SALARY ANALYSIS
    # ------------------------------------------

    salary_df = all_df[
        (all_df["type"] == "income") &
        (all_df["category"].str.lower() == "salary")
    ].copy()

    salary_monthly = pd.DataFrame(
        columns=["analysis_month", "amount"]
    )

    salary_trend_chart = None
    latest_salary = None
    salary_change = None
    salary_change_percent = None

    if not salary_df.empty:

        salary_monthly = (
            salary_df
            .groupby("analysis_month", as_index=False)["amount"]
            .sum()
            .sort_values("analysis_month")
        )

        latest_salary = float(
            salary_monthly.iloc[-1]["amount"]
        )

        if len(salary_monthly) >= 2:

            previous_salary = float(
                salary_monthly.iloc[-2]["amount"]
            )

            salary_change = latest_salary - previous_salary

            if previous_salary > 0:
                salary_change_percent = (
                    salary_change / previous_salary
                ) * 100

        fig = px.bar(
            salary_monthly,
            x="analysis_month",
            y="amount",
            title="Monthly Salary Trend",
            labels={
                "analysis_month": "Month",
                "amount": "Salary (₹)"
            },
            color_discrete_sequence=["#2563eb"]
        )

        fig.update_layout(
            paper_bgcolor="white",
            plot_bgcolor="white",
            font=dict(color="#14213d"),
            margin=dict(l=30, r=20, t=60, b=40),
            xaxis_title="Month",
            yaxis_title="Salary (₹)"
        )

        salary_trend_chart = fig.to_html(
            full_html=False,
            include_plotlyjs=False,
            config={"responsive": True}
        )

    # ------------------------------------------
    # 3. FILTER DATA BY SELECTED MONTH
    # ------------------------------------------

    if selected_month != "all":
        df = df[
            df["analysis_month"] == selected_month
        ].copy()

    if df.empty:

        result = empty_result.copy()

        result["salary_trend_chart"] = salary_trend_chart
        result["latest_salary"] = latest_salary
        result["salary_change"] = salary_change
        result["salary_change_percent"] = (
            round(salary_change_percent, 2)
            if salary_change_percent is not None else None
        )
        result["financial_insights"] = [
            "No transactions were found for the selected month."
        ]

        return result

    # ------------------------------------------
    # 4. TOTAL INCOME, EXPENSES AND SAVINGS
    # ------------------------------------------

    total_income = df.loc[
        df["type"] == "income", "amount"
    ].sum()

    total_expenses = df.loc[
        df["type"] == "expense", "amount"
    ].sum()

    balance = total_income - total_expenses

    savings_rate = (
        balance / total_income * 100
        if total_income > 0 else 0
    )

    expenses = df[
        df["type"] == "expense"
    ].copy()

    # ------------------------------------------
    # 5. MONTHLY EXPENSES CHART
    # ------------------------------------------

    monthly_chart = None

    monthly_expenses = (
        expenses
        .groupby("analysis_month", as_index=False)["amount"]
        .sum()
        .sort_values("analysis_month")
    )

    if not monthly_expenses.empty:

        fig = px.bar(
            monthly_expenses,
            x="analysis_month",
            y="amount",
            title="Monthly Expenses",
            labels={
                "analysis_month": "Month",
                "amount": "Expenses (₹)"
            },
            color_discrete_sequence=["#10b981"]
        )

        fig.update_layout(
            paper_bgcolor="white",
            plot_bgcolor="white",
            font=dict(color="#14213d"),
            margin=dict(l=30, r=20, t=60, b=40)
        )

        monthly_chart = fig.to_html(
            full_html=False,
            include_plotlyjs=False,
            config={"responsive": True}
        )

    # ------------------------------------------
    # 6. INCOME VS EXPENSES CHART
    # ------------------------------------------

    comparison_chart = None

    comparison = pd.DataFrame({
        "Type": ["Income", "Expenses"],
        "Amount": [
            float(total_income),
            float(total_expenses)
        ]
    })

    comparison = comparison[
        comparison["Amount"] > 0
    ]

    if not comparison.empty:

        fig = px.pie(
            comparison,
            names="Type",
            values="Amount",
            title="Income vs Expenses",
            hole=0.4,
            color="Type",
            color_discrete_map={
                "Income": "#10b981",
                "Expenses": "#ef4444"
            }
        )

        fig.update_traces(
            textposition="inside",
            textinfo="label+percent",
            hovertemplate=(
                "<b>%{label}</b><br>"
                "Amount: ₹%{value:.2f}<br>"
                "Share: %{percent}"
                "<extra></extra>"
            )
        )

        comparison_chart = fig.to_html(
            full_html=False,
            include_plotlyjs=False,
            config={"responsive": True}
        )

    # ------------------------------------------
    # 7. CATEGORY-WISE EXPENSE CHART
    # ------------------------------------------

    category_chart = None

    if not expenses.empty:

        category_totals = (
            expenses
            .groupby("category", as_index=False)["amount"]
            .sum()
        )

        category_totals = category_totals[
            category_totals["amount"] > 0
        ].sort_values("amount", ascending=False)

        if not category_totals.empty:

            fig = px.pie(
                category_totals,
                names="category",
                values="amount",
                title="Expenses by Category",
                hole=0.4,
                color_discrete_sequence=[
                    "#2563eb",
                    "#10b981",
                    "#f59e0b",
                    "#ef4444",
                    "#8b5cf6",
                    "#06b6d4",
                    "#f97316",
                    "#64748b"
                ]
            )

            fig.update_traces(
                textposition="inside",
                textinfo="label+percent",
                hovertemplate=(
                    "<b>%{label}</b><br>"
                    "Amount: ₹%{value:.2f}<br>"
                    "Share: %{percent}"
                    "<extra></extra>"
                )
            )

            category_chart = fig.to_html(
                full_html=False,
                include_plotlyjs=False,
                config={"responsive": True}
            )

    # ------------------------------------------
    # 8. MONTHLY INCOME, EXPENSES AND SAVINGS
    # ------------------------------------------

    monthly_summary = (
        all_df
        .pivot_table(
            index="analysis_month",
            columns="type",
            values="amount",
            aggfunc="sum",
            fill_value=0
        )
        .reset_index()
        .sort_values("analysis_month")
    )

    for column in ["income", "expense"]:
        if column not in monthly_summary.columns:
            monthly_summary[column] = 0

    monthly_summary["savings"] = (
        monthly_summary["income"] -
        monthly_summary["expense"]
    )

    income_expense_trend_chart = None

    if not monthly_summary.empty:

        trend_data = monthly_summary.melt(
            id_vars=["analysis_month"],
            value_vars=["income", "expense", "savings"],
            var_name="Financial Type",
            value_name="Amount"
        )

        fig = px.line(
            trend_data,
            x="analysis_month",
            y="Amount",
            color="Financial Type",
            markers=True,
            title="Monthly Income, Expenses and Savings",
            color_discrete_map={
                "income": "#10b981",
                "expense": "#ef4444",
                "savings": "#2563eb"
            },
            labels={
                "analysis_month": "Month",
                "Amount": "Amount (₹)"
            }
        )

        fig.update_layout(
            paper_bgcolor="white",
            plot_bgcolor="white",
            font=dict(color="#14213d"),
            margin=dict(l=30, r=20, t=60, b=40)
        )

        income_expense_trend_chart = fig.to_html(
            full_html=False,
            include_plotlyjs=False,
            config={"responsive": True}
        )

    # ------------------------------------------
    # 9. PERSONALIZED FINANCIAL INSIGHTS
    # ------------------------------------------

    financial_insights = []

    if total_income > 0:

        financial_insights.append(
            f"Your total income for the selected period is ₹{total_income:,.2f}."
        )

        financial_insights.append(
            f"You spent ₹{total_expenses:,.2f} during this period."
        )

        financial_insights.append(
            f"Your remaining balance is ₹{balance:,.2f}."
        )

        financial_insights.append(
            f"Your savings rate is {savings_rate:.2f}%."
        )

        if total_expenses > total_income:
            financial_insights.append(
                "Warning: Your expenses are higher than your income. "
                "Consider reducing non-essential spending."
            )

        elif savings_rate < 20:
            financial_insights.append(
                "Your savings rate is below 20%. "
                "Try to increase savings by controlling unnecessary expenses."
            )

        elif savings_rate >= 20:
            financial_insights.append(
                "Good work! You are saving at least 20% of your income."
            )

    else:
        financial_insights.append(
            "No income was recorded for the selected period. "
            "Add your income to receive more accurate financial insights."
        )

    if latest_salary is not None:

        financial_insights.append(
            f"Your latest recorded monthly salary is ₹{latest_salary:,.2f}."
        )

        if salary_change is not None:

            if salary_change > 0:
                financial_insights.append(
                    f"Your recorded salary increased by ₹{salary_change:,.2f} "
                    "compared with the previous recorded month."
                )

            elif salary_change < 0:
                financial_insights.append(
                    f"Your recorded salary decreased by ₹{abs(salary_change):,.2f} "
                    "compared with the previous recorded month."
                )

            else:
                financial_insights.append(
                    "Your recorded salary is unchanged from the previous recorded month."
                )

    else:
        financial_insights.append(
            "Add an Income transaction with category Salary "
            "to view your monthly salary trend."
        )

    # ------------------------------------------
    # 10. RETURN ALL ANALYSIS DATA
    # ------------------------------------------

    return {
        "total_income": float(total_income),
        "total_expenses": float(total_expenses),
        "balance": float(balance),
        "savings_rate": round(float(savings_rate), 2),

        "monthly_chart": monthly_chart,
        "comparison_chart": comparison_chart,
        "category_chart": category_chart,

        "income_expense_trend_chart": income_expense_trend_chart,
        "salary_trend_chart": salary_trend_chart,

        "financial_insights": financial_insights,

        "salary_change": (
            round(float(salary_change), 2)
            if salary_change is not None else None
        ),

        "salary_change_percent": (
            round(float(salary_change_percent), 2)
            if salary_change_percent is not None else None
        ),

        "latest_salary": latest_salary,
        "selected_month": selected_month
    }