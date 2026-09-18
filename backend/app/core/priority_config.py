PRIORITY_WEIGHTS = {
    "instructional_need": 35,
    "evidence_severity": 25,
    "uncertainty": 15,
    "missed_instruction": 10,
    "group_complexity": 10,
    "reach": 5
}

INSTRUCTIONAL_NEED_VALUES = {
    "recovery": 1.00,
    "check": 0.85,
    "guided": 0.60,
    "practice": 0.30,
    "extension": 0.05,
}

PREREQUISITE_SEVERITY_VALUES = {
    "confirmed_gap": 1.00,
    "likely_gap": 0.80,
    "insufficient_evidence": 0.65,
    "developing": 0.45,
    "ready": 0.00
}

TARGET_SEVERITY_VALUES = {
    "stale_or_unknown": 0.55,
    "low_score": 0.70,
    "practice": 0.35,
    "extension": 0.00
}

UNCERTAINTY_VALUES = {
    "assessment": 1.00,
    "quick_check": 0.60,
    "stale_or_unknown": 0.70,
    "none": 0.00
}

COMPLEXITY_VALUES = {
    "mixed_support": 1.00,
    "mixed_needs": 0.70,
    "multiple_original": 0.50,
    "simple": 0.00
}

PRIORITY_REFERENCE_GROUP_SIZE = 8

PRIORITY_TIER_THRESHOLDS = {
    "urgent": 70,
    "high": 50,
    "moderate": 30,
    "low": 0
}

FACTOR_ORDER = [
    "instructional_need",
    "evidence_severity",
    "uncertainty",
    "missed_instruction",
    "group_complexity",
    "reach"
]

def validate_priority_config():
    if sum(PRIORITY_WEIGHTS.values()) != 100:
        raise ValueError("Configuration error: Priority weights do not sum to 100.")
        
    for val_dict in [INSTRUCTIONAL_NEED_VALUES, PREREQUISITE_SEVERITY_VALUES, TARGET_SEVERITY_VALUES, UNCERTAINTY_VALUES, COMPLEXITY_VALUES]:
        for v in val_dict.values():
            if not (0 <= v <= 1):
                raise ValueError("Configuration error: Normalized value must be between 0 and 1.")
                
    if PRIORITY_REFERENCE_GROUP_SIZE <= 0:
        raise ValueError("Configuration error: Priority reference group size must be > 0.")
        
    u, h, m, l = (
        PRIORITY_TIER_THRESHOLDS["urgent"], 
        PRIORITY_TIER_THRESHOLDS["high"], 
        PRIORITY_TIER_THRESHOLDS["moderate"], 
        PRIORITY_TIER_THRESHOLDS["low"]
    )
    
    if not (u > h > m > l):
        raise ValueError("Configuration error: Priority tier thresholds are not strictly ordered.")
        
    for t in [u, h, m, l]:
        if not (0 <= t <= 100):
            raise ValueError("Configuration error: Tier thresholds must be between 0 and 100.")

def get_tier_for_score(score: float) -> str:
    if score >= PRIORITY_TIER_THRESHOLDS["urgent"]: return "urgent"
    if score >= PRIORITY_TIER_THRESHOLDS["high"]: return "high"
    if score >= PRIORITY_TIER_THRESHOLDS["moderate"]: return "moderate"
    return "low"
