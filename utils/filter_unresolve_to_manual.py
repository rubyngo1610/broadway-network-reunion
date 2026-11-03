import pandas as pd
from pathlib import Path

# Paths
UNRESOLVED_PATH = Path("outputs/tables/unresolved_names.csv")

def prioritize_unresolved():
    if not UNRESOLVED_PATH.exists():
        print(f"Error: Could not find {UNRESOLVED_PATH}")
        return

    df = pd.read_csv(UNRESOLVED_PATH, dtype=str).fillna("")

    # Ensure required column exists
    if "resolved_qid_manual" not in df.columns:
        df["resolved_qid_manual"] = ""

    # Identify rows that still need manual input
    needs_review_mask = df["resolved_qid_manual"].str.strip() == ""

    # Calculate distinct show count per normalized name among unreviewed rows
    unreviewed_df = df[needs_review_mask]
    show_counts = unreviewed_df.groupby("normalized")["show_id"].nunique().to_dict()

    # Map show counts back to the entire DataFrame
    df["unresolved_show_count"] = df["normalized"].map(show_counts).fillna(0).astype(int)

    # Sort priorities:
    # 1. Unresolved/blank rows first (needs_review_mask True -> 1, False -> 0)
    # 2. Highest recurring show count first (n_shows >= 2 at top)
    # 3. Alphabetical by normalized name
    df["is_unresolved"] = needs_review_mask.astype(int)

    df_sorted = df.sort_values(
        by=["is_unresolved", "unresolved_show_count", "normalized"],
        ascending=[False, False, True]
    ).drop(columns=["is_unresolved", "unresolved_show_count"])

    # Overwrite CSV with prioritized order
    df_sorted.to_csv(UNRESOLVED_PATH, index=False)

    # Summary report
    recurring_count = (show_counts_val >= 2 for show_counts_val in show_counts.values())
    print(f"Success! Reordered {UNRESOLVED_PATH}")
    print(f"Top rows now contain the unresolved names appearing in 2+ shows.")

if __name__ == "__main__":
    prioritize_unresolved()