"""Independent synthetic source-contract vectors; never imports the target.

The groups below freeze answers from synthetic_rules.cob. Seed is accepted for
the generator interface; exhaustive, fixed enumeration needs no randomness.
This authoring example does not claim an independent human or mainframe review.
"""


def generate_cases(rule, seed):
    rule_id = rule["rule_id"]
    if rule_id == "R-ELIGIBILITY":
        # Source PIC 9(4) and IF >= 100: the entire false domain is 0..99.
        for amount in range(100):
            tags = ["below_threshold"]
            if amount == 0:
                tags.append("minimum_amount")
            if amount == 99:
                tags.append("just_below_threshold")
            yield {"case_id": f"ELIG-N-{amount:04d}", "category": "negative",
                   "inputs": {"amount": amount}, "expected": {"eligible": False},
                   "coverage_tags": tags}
        # 99 successive true inputs and the largest representable source amount.
        for amount in [*range(100, 199), 9999]:
            tags = ["at_or_above_threshold"]
            if amount == 100:
                tags.append("at_threshold")
            if amount == 9999:
                tags.append("maximum_amount")
            yield {"case_id": f"ELIG-P-{amount:04d}", "category": "positive",
                   "inputs": {"amount": amount}, "expected": {"eligible": True},
                   "coverage_tags": tags}
    elif rule_id == "R-NAME-FORMAT":
        # Expected positions follow alphanumeric MOVE, independently of the
        # target's slicing/ljust implementation. The contents affect the output.
        fitting_names = ["", "Q", "A" * 19, "B" * 20]
        fitting_names.extend(f"ROW{index:03d}" for index in range(96))
        for index, name in enumerate(fitting_names):
            positions = [" "] * 20
            for column, character in enumerate(name):
                positions[column] = character
            tags = ["fits_width"]
            if len(name) == 0:
                tags.append("empty_input")
            elif len(name) == 1:
                tags.append("one_character")
            elif len(name) == 19:
                tags.append("width_minus_one")
            elif len(name) == 20:
                tags.append("exact_width")
            yield {"case_id": f"NAME-P-{index:03d}", "category": "positive",
                   "inputs": {"name": name},
                   "expected": {"display_name": "".join(positions), "truncated": False},
                   "coverage_tags": tags}
        for index in range(100):
            # Every retained 20-character prefix differs. Variations are not
            # confined to discarded suffixes, record IDs or other padding.
            retained = f"N{index:03d}-" + "K" * 15
            suffix_length = 1 if index == 0 else 20 if index == 99 else 5
            tags = ["over_width"]
            if index == 0:
                tags.append("width_plus_one")
            if index == 99:
                tags.append("maximum_input_width")
            yield {"case_id": f"NAME-N-{index:03d}", "category": "negative",
                   "inputs": {"name": retained + "Z" * suffix_length},
                   "expected": {"display_name": retained, "truncated": True},
                   "coverage_tags": tags}
    else:
        raise ValueError("unknown synthetic rule ID")
