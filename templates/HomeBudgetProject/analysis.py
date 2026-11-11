
import pandas as pd
import plotly.express as px
from database import get_db_connection


def get_analysis(selected_month="all"):
    connection = get_db_connection()
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT type, description, amount,
                   transaction_date, category
            FROM transactions
            ORDER BY transaction_date
        """)

        rows = cursor.fetchall()

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()

    df = pd.DataFrame(rows)

    # Default values when there are no transactions
    if df.empty:
        return {
            "total_income": 0,
            "total_expenses": 0,
            "balance": 0,
            "savings_rate": 0,
            "monthly_chart": None,
            "comparison_chart": None,
            "category_chart": None,
            "selected_month": selected_month,
        }

    # Clean and prepare data
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

    # Filter transactions by selected month
    if selected_month != "all":
        df = df[
            df["transaction_date"].dt.strftime("%Y-%m")
            == selected_month
        ].copy()

    # Handle a month with no transactions
    if df.empty:
        return {
            "total_income": 0,
            "total_expenses": 0,
            "balance": 0,
            "savings_rate": 0,
            "monthly_chart": None,
            "comparison_chart": None,
            "category_chart": None,
            "selected_month": selected_month,
        }

    # Calculate income and expenses
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

    # Get expense transactions only
    expenses = df[
        df["type"] == "expense"
    ].copy()

    # ==========================================
    # 1. MONTHLY EXPENSES CHART
    # ==========================================

    monthly_chart = None

    valid_expenses = expenses.dropna(
        subset=["transaction_date"]
    ).copy()

    if not valid_expenses.empty:
        valid_expenses["month"] = (
            valid_expenses["transaction_date"]
            .dt.strftime("%Y-%m")
        )

        monthly = (
            valid_expenses
            .groupby("month", as_index=False)["amount"]
            .sum()
            .sort_values("month")
        )

        if not monthly.empty:
            fig = px.bar(
                monthly,
                x="month",
                y="amount",
                title="Monthly Expenses",
                labels={
                    "month": "Month",
                    "amount": "Expenses (₹)"
                },
                color_discrete_sequence=["#10B981"],
            )

            fig.update_layout(
                plot_bgcolor="white",
                paper_bgcolor="white",
                font=dict(
                    color="#064E3B",
                    size=13
                ),
                margin=dict(
                    l=30, r=20, t=60, b=40
                ),
                xaxis_title="Month",
                yaxis_title="Expenses (₹)",
            )

            monthly_chart = fig.to_html(
                full_html=False,
                include_plotlyjs=True,
                config={"responsive": True},
            )

    # ==========================================
    # 2. INCOME VS EXPENSES CHART
    # ==========================================

    comparison_chart = None

    comparison = pd.DataFrame({
        "Type": ["Income", "Expenses"],
        "Amount": [
            float(total_income),
            float(total_expenses),
        ],
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
                "Income": "#10B981",
                "Expenses": "#EF4444",
            },
        )

        fig.update_traces(
            textposition="inside",
            textinfo="label+percent",
            hovertemplate=(
                "<b>%{label}</b><br>"
                "Amount: ₹%{value:.2f}<br>"
                "Share: %{percent}"
                "<extra></extra>"
            ),
        )

        fig.update_layout(
            paper_bgcolor="white",
            plot_bgcolor="white",
            font=dict(color="#064E3B"),
            margin=dict(
                l=20, r=20, t=60, b=40
            ),
        )

        comparison_chart = fig.to_html(
            full_html=False,
            include_plotlyjs=False,
            config={"responsive": True},
        )

    # ==========================================
    # 3. CATEGORY-WISE EXPENSES CHART
    # ==========================================

    category_chart = None

    if not expenses.empty:
        category_totals = (
            expenses
            .groupby("category", as_index=False)["amount"]
            .sum()
        )

        # Display categories with positive expenses
        category_totals = category_totals[
            category_totals["amount"] > 0
        ].copy()

        if not category_totals.empty:
            category_totals = category_totals.sort_values(
                "amount", ascending=False
            )

            fig = px.pie(
                category_totals,
                names="category",
                values="amount",
                title="Expenses by Category",
                hole=0.4,
                color_discrete_sequence=[
                    "#047857",
                    "#2563EB",
                    "#F59E0B",
                    "#DC2626",
                    "#7C3AED",
                    "#0891B2",
                    "#EA580C",
                    "#4F46E5",
                    "#DB2777",
                    "#65A30D",
                ],
            )

            fig.update_traces(
                textposition="inside",
                textinfo="label+percent",
                hovertemplate=(
                    "<b>%{label}</b><br>"
                    "Amount: ₹%{value:.2f}<br>"
                    "Share: %{percent}"
                    "<extra></extra>"
                ),
                marker=dict(
                    line=dict(
                        color="white",
                        width=2
                    )
                ),
            )

            fig.update_layout(
                paper_bgcolor="white",
                plot_bgcolor="white",
                font=dict(
                    color="#064E3B",
                    size=14
                ),
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.1,
                    xanchor="center",
                    x=0.5,
                ),
                margin=dict(
                    l=20,
                    r=20,
                    t=70,
                    b=70,
                ),
            )

            category_chart = fig.to_html(
                full_html=False,
                include_plotlyjs=False,
                config={"responsive": True},
            )

    # ==========================================
    # RETURN ANALYSIS DATA
    # ==========================================

    return {
        "total_income": float(total_income),
        "total_expenses": float(total_expenses),
        "balance": float(balance),
        "savings_rate": round(
            float(savings_rate), 2
        ),
        "monthly_chart": monthly_chart,
        "comparison_chart": comparison_chart,
        "category_chart": category_chart,
        "selected_month": selected_month,
    }
