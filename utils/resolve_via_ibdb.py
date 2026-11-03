import re
import time
from pathlib import Path
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNRESOLVED_PATH = PROJECT_ROOT / "outputs" / "tables" / "unresolved_names.csv"
SPARQL_URL = "https://query.wikidata.org/sparql"
HEADERS = {
    "User-Agent": "BroadwayPipeline/1.0 (https://github.com/broadway-data)",
    "Accept": "application/json",
}

# Known manual edge-case overrides (takes immediate priority)
MANUAL_OVERRIDES = {
    "alan johnson": "Q4706981",  # Choreographer, not politician
}

# Known non-person strings / corporate entries to ignore
NON_PERSON_PATTERNS = [
    r"^\d{4}\s+version$",             # e.g., '1956 version'
    r"^various\s+artists$",            # explicitly catch 'various artists'
    r"^artistic(\s+director)?",        # 'artistic director', 'artistic director michael weber'
    r"^artistic\s+director\s+.*",      # any string starting with 'artistic director'
    r"^assistant\s+.*",                # 'assistant latin choreographer', etc.
    r"^adaptation$",                   # 'adaptation'
    r"^adapted\s+score$",              # 'adapted score'
    r"^additional\s+(lyrics|music)",   # 'additional lyrics betty comden', 'additional music jule styne'
    r"^american$",                     # nationality descriptor
    r"^atelier$",                      # studio
    r"^atlantis\s+productions$",       # company
    r"^base\s+entertainment$",         # company
    r"^btw\s+productions$",            # company
    r"^brt$",                          # organization / company
    r"^chromolume$",                   # company
]

REVIVAL_TOUR_KEYWORDS = [
    r"\btour\b",
    r"\btouring\b",
    r"\brevival\b",
    r"\blondon\b",
    r"\bwest\s+end\b",
    r"\buk\s+tour\b",
    r"\bnational\s+tour\b",
    r"\bconcert\b",
    r"\bworkshop\b",
    r"\bfilm\b",
    r"\badaptation\b",
    r"\bcast\s+recording\b",
    r"\bsoundtrack\b",
]


def is_non_person_string(name: str) -> bool:
    """Checks if a string is clearly a non-person noise label."""
    norm = name.strip().lower()
    return any(re.search(pat, norm) for pat in NON_PERSON_PATTERNS)

def is_revival_or_tour_context(row: pd.Series) -> bool:
    """Checks context, role, or section for explicit revival/tour/non-original keywords."""
    # Combine text fields where context cues appear
    text_to_check = " ".join([
        str(row.get("context", "")),
        str(row.get("role", "")),
        str(row.get("person_name", ""))
    ]).lower()

    return any(re.search(kw, text_to_check) for kwparam in REVIVAL_TOUR_KEYWORDS for kw in [kwparam])


def fetch_broadway_qids_batch(person_names: list[str]) -> dict[str, str]:
    """Queries Wikidata in batches for human items with Broadway/theatre IDs matching exact labels."""
    if not person_names:
        return {}

    def escape_name(n):
        safe_str = str(n).replace('"', '\\"')
        return f'"{safe_str}"@en'

    formatted_names = " ".join(escape_name(n) for n in person_names)

    # Strictly select items that are human (Q5) AND hold at least one theatre property
    sparql_query = f"""
    SELECT ?name ?item WHERE {{
      VALUES ?name {{ {formatted_names} }}
      ?item rdfs:label ?name .
      ?item wdt:P31 wd:Q5 .
      
      # Must match at least one Broadway/theatre/performing arts property
      {{ ?item wdt:P1220 ?ibdb . }} UNION        # IBDB person ID
      {{ ?item wdt:P6132 ?playbill . }} UNION    # Playbill person ID
      {{ ?item wdt:P5033 ?iobdb . }} UNION       # IOBDB person ID
      {{ ?item wdt:P5684 ?lort . }}              # LORT person ID
    }}
    """

    for attempt in range(3):
        try:
            r = requests.get(
                SPARQL_URL,
                params={"query": sparql_query},
                headers=HEADERS,
                timeout=15,
            )
            if r.status_code == 200:
                results = {}
                bindings = r.json().get("results", {}).get("bindings", [])
                for b in bindings:
                    raw_name = b["name"]["value"]
                    qid = b["item"]["value"].split("/")[-1]
                    # Assign the first entity that explicitly holds a theatre identifier
                    if raw_name not in results:
                        results[raw_name] = qid
                return results
            elif r.status_code == 429:  # Rate limited
                time.sleep(2**attempt * 3)
        except Exception:
            time.sleep(2)

    return {}

def main():
    if not UNRESOLVED_PATH.exists():
        print(f"Error: Could not find {UNRESOLVED_PATH}")
        return

    df = pd.read_csv(UNRESOLVED_PATH, dtype=str).fillna("")

    # Ensure column exists
    if "resolved_qid_manual" not in df.columns:
        df["resolved_qid_manual"] = ""

    # Identify candidate rows to look up
    todo_mask = (
        df["resolved_qid_manual"].str.strip() == ""
    ) & ~df["person_name"].map(is_non_person_string)

    unique_names = [
        n.strip() for n in df.loc[todo_mask, "person_name"].unique() if n.strip()
    ]
    print(
        f"Processing {len(unique_names)} unique candidate names via Wikidata SPARQL..."
    )

    # Batch SPARQL requests in chunks of 40 to avoid URI length and timeout limits
    batch_size = 40
    qid_results = {}
    for i in range(0, len(unique_names), batch_size):
        chunk = unique_names[i : i + batch_size]
        found = fetch_broadway_qids_batch(chunk)
        qid_results.update(found)
        time.sleep(0.5)  # Respect Wikidata rate limits

    # Apply results back to the DataFrame
    updated_count = 0
    for idx, row in df.iterrows():
        p_name = row.get("person_name", "").strip()
        p_norm = row.get("normalized", "").strip().lower()

        # 1. Skip if already manually filled
        if row.get("resolved_qid_manual", "").strip():
            continue

        # 2. Check hardcoded manual overrides
        if p_norm in MANUAL_OVERRIDES:
            df.at[idx, "resolved_qid_manual"] = MANUAL_OVERRIDES[p_norm]
            updated_count += 1
            continue

        # 3. Check SPARQL Broadway lookup results
        if p_name in qid_results:
            df.at[idx, "resolved_qid_manual"] = qid_results[p_name]
            updated_count += 1

        # 4. Exclude if not person 
        # Check non-person noise patterns
        if is_non_person_string(p_name):
            df.at[idx, "resolved_qid_manual"] = "EXCLUDE"
            updated_count += 1
            continue

        if is_revival_or_tour_context(row):
            df.at[idx, "resolved_qid_manual"] = "EXCLUDE"
            updated_count += 1
            continue


    df.to_csv(UNRESOLVED_PATH, index=False)
    print(f"Done! Updated {updated_count} rows in {UNRESOLVED_PATH}")


if __name__ == "__main__":
    main()