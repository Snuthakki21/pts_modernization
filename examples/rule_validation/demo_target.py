"""Synthetic Python target for the two source-fixture rules; no external I/O."""


def eligibility(amount):
    """R-ELIGIBILITY: the fixture's unsigned four-digit amount contract."""
    if type(amount) is not int or not 0 <= amount <= 9999:
        raise ValueError("amount must be an integer between 0 and 9999")
    return {"eligible": amount >= 100}


def format_name(name):
    """R-NAME-FORMAT: ASCII MOVE to a twenty-character display field."""
    if not isinstance(name, str) or not name.isascii() or len(name) > 40:
        raise ValueError("name must be an ASCII string of at most 40 characters")
    return {"display_name": name[:20].ljust(20), "truncated": len(name) > 20}


def evaluate(rule_id, inputs):
    if rule_id == "R-ELIGIBILITY":
        actual = eligibility(inputs["amount"])
        category = "positive" if actual["eligible"] else "negative"
    elif rule_id == "R-NAME-FORMAT":
        actual = format_name(inputs["name"])
        category = "negative" if actual["truncated"] else "positive"
    else:
        raise ValueError("unknown synthetic rule ID")
    return {"actual": actual,
            "rule_events": [{"rule_id": rule_id, "category": category}]}
