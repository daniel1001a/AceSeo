"""Terms gate (W4 4, V12; PLAN 5.4.1).

Only terms_status "verified-allowed" passes. Anything else, including a missing
or misspelled status, is treated as not allowed: unclear terms mean no writes.
An opt-in engine must also be selected for the run.
"""

ALLOWED = "verified-allowed"
RESTRICTED = "verified-restricted"
UNVERIFIED = "unverified"
TERMS_STATUSES = (ALLOWED, RESTRICTED, UNVERIFIED)

# W4 placeholder with no value yet (W5-02 open). None disables the age check;
# the gate does not invent a number.
TERMS_MAX_AGE_DAYS = None

SKIP_REASON = "terms_gate"

REASON_RESTRICTED = "terms_restricted"
REASON_UNVERIFIED = "terms_unverified"
REASON_OPT_IN = "opt_in_not_selected"


def gate(snapshot, opt_in_selected):
    """Return (allowed, reason). reason is None when allowed."""
    status = snapshot.get("terms_status")
    if status == RESTRICTED:
        return False, REASON_RESTRICTED
    if status != ALLOWED:
        return False, REASON_UNVERIFIED
    if snapshot.get("opt_in") is not False and snapshot.get("engine") not in set(opt_in_selected):
        # opt_in must be exactly False to skip selection; a missing flag counts as opt-in.
        return False, REASON_OPT_IN
    return True, None
