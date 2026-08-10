# ---------------------------------------------------------------------------
# PR Mapping Rules Table
# ---------------------------------------------------------------------------
PR_MAPPINGS = {
    "648-1": {
        "Customer/Project": "JF Taylor : 648 USAF FA FuTs",
        "Custom WBS Task": "648-1 Materials",
    },
    "648-2": {
        "Customer/Project": "JF Taylor : 648 USAF FA FuTs",
        "Custom WBS Task": "648-2 Materials",
    },
    "648-3": {
        "Customer/Project": "JF Taylor : 648 USAF FA FuTs",
        "Custom WBS Task": "648-3 Materials",
    },
    "777": {
        "Customer/Project": "Newton Design, LLC : 777 Overhead",
        "Custom WBS Task": "777 Materials",
    },
    "505": {
        "Customer/Project": "Lockheed Martin : 505 FuT 5",
        "Custom WBS Task": "Materials",
    },
    "506": {
        "Customer/Project": "Lockheed Martin : 506 FuT 6",
        "Custom WBS Task": "506 Materials",
    },
}

def apply_pr_mappings(df: pd.DataFrame) -> pd.DataFrame:
    """Enforces WBS and Customer/Project mappings based on the final PR # value."""
    if "PR #" not in df.columns:
        return df

    for idx, row in df.iterrows():
        pr_val = str(row.get("PR #", ""))
        for key, mapping in PR_MAPPINGS.items():
            if key in pr_val:
                df.at[idx, "Customer/Project"] = mapping["Customer/Project"]
                df.at[idx, "Custom WBS Task"] = mapping["Custom WBS Task"]
                break
    return df
