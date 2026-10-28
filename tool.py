import polars as pl
from pathlib import Path
from typing import Optional
import traceback

import config
from sandbox import get_sandbox

DATA_DIR = config.DATA_DIR
DEFAULT_CSV = config.DEFAULT_CSV


def get_csv_context(csv_path: Optional[str] = None) -> str:
    """
    Read CSV data using Polars and return context about the data.
    This includes schema, sample rows, and basic statistics.

    Args:
        csv_path: Path to the CSV file. If None, uses default sales_data.csv

    Returns:
        A string containing data context for the LLM to generate code.
    """
    file_path = Path(csv_path) if csv_path else DEFAULT_CSV

    if not file_path.exists():
        return f"Error: CSV file not found at {file_path}"

    try:
        df = pl.read_csv(file_path)

        context_parts = []

        # File path info
        context_parts.append(f"CSV File: {file_path}")
        context_parts.append(f"CSV Path for code: '{file_path}'")

        context_parts.append("\n=== SCHEMA ===")
        context_parts.append(f"Columns ({len(df.columns)}):")
        for col_name, dtype in zip(df.columns, df.dtypes):
            context_parts.append(f"  - {col_name}: {dtype}")

        context_parts.append(f"\nShape: {df.shape[0]} rows × {df.shape[1]} columns")

        context_parts.append("\n=== SAMPLE DATA (first 5 rows) ===")
        context_parts.append(str(df.head(5)))

        # Basic statistics for numeric columns
        context_parts.append("\n=== NUMERIC STATISTICS ===")
        numeric_cols = df.select(pl.col(pl.NUMERIC_DTYPES)).columns
        if numeric_cols:
            stats_df = df.select(numeric_cols).describe()
            context_parts.append(str(stats_df))
        else:
            context_parts.append("No numeric columns found.")

        context_parts.append("\n=== CATEGORICAL COLUMNS (unique values) ===")
        string_cols = df.select(pl.col(pl.Utf8)).columns
        for col in string_cols:
            unique_vals = df[col].unique().to_list()
            if len(unique_vals) <= 10:
                context_parts.append(f"  - {col}: {unique_vals}")
            else:
                context_parts.append(f"  - {col}: {unique_vals[:10]} ... ({len(unique_vals)} unique values)")

        return "\n".join(context_parts)

    except Exception as e:
        return f"Error reading CSV: {str(e)}\n{traceback.format_exc()}"



def run_python_code(code: str, csv_path: Optional[str] = None) -> str:
    """
    Execute Polars/Python code in the configured sandbox and return its output.

    The backend (local subprocess or remote Daytona) is chosen in config.py via
    ``SANDBOX_BACKEND``. Either way the code runs with `pl` (polars) and
    `csv_path` predefined, and anything it `print()`s is returned.

    Args:
        code: Python code to execute. Should use Polars (imported as pl).
        csv_path: Path to the CSV file to be used in the code.

    Returns:
        String containing the execution stdout or an error message.
    """
    file_path = Path(csv_path) if csv_path else DEFAULT_CSV
    return get_sandbox().run(code, str(file_path))


def create_polars_tools():
    """
    Create the Polars data-analytics tools as Google ADK callable functions.

    A single tool: the agent discovers the schema by running
    ``collect_schema()`` inside the executor, so no separate context tool is
    needed. (``get_csv_context`` remains as a plain helper for the Streamlit UI.)
    """
    def execute_polars_code(
        code: str,
        csv_path: str = "",
    ) -> str:
        """
        Execute Python code using Polars for data analysis in an isolated subprocess.

        The code has access to `pl` (polars) and `csv_path` (path to the CSV file).
        Use Polars (NOT pandas) and always print() results, e.g.:
            df = pl.read_csv(csv_path)
            print(df.group_by("category").agg(pl.col("total_revenue").sum()))
        """
        return run_python_code(code, csv_path if csv_path else None)

    return [execute_polars_code]


if __name__ == "__main__":
    # Test the tools
    print("Testing get_csv_context:")
    print(get_csv_context())
    print("\n" + "="*50 + "\n")

    print("Testing run_python_code (isolated subprocess):")
    test_code = """
df = pl.read_csv(csv_path)
print("Total revenue by category:")
result = df.group_by("category").agg(pl.col("total_revenue").sum().alias("total"))
print(result)
"""
    print(run_python_code(test_code))
