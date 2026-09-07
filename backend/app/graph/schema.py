"""Graph schema constants: the entity/relation vocabulary the whole system agrees on."""

# --- Node types --------------------------------------------------------
PERSON = "PERSON"
PHONE = "PHONE"
VEHICLE = "VEHICLE"
LOCATION = "LOCATION"
ORGANIZATION = "ORGANIZATION"
FINANCIAL_ACCOUNT = "FINANCIAL_ACCOUNT"
EVENT = "EVENT"
CASE = "CASE"

ALL_NODE_TYPES = [PERSON, PHONE, VEHICLE, LOCATION, ORGANIZATION, FINANCIAL_ACCOUNT, EVENT, CASE]

# --- Relation types ------------------------------------------------------
CALLED = "CALLED"
TRANSACTED_WITH = "TRANSACTED_WITH"
ASSOCIATED_WITH = "ASSOCIATED_WITH"
OWNS = "OWNS"
PRESENT_AT = "PRESENT_AT"
MEMBER_OF = "MEMBER_OF"
MENTIONED_WITH = "MENTIONED_WITH"
LINKED_TO_CASE = "LINKED_TO_CASE"
AUTHORED = "AUTHORED"

ALL_RELATION_TYPES = [
    CALLED, TRANSACTED_WITH, ASSOCIATED_WITH, OWNS, PRESENT_AT,
    MEMBER_OF, MENTIONED_WITH, LINKED_TO_CASE, AUTHORED,
]

# Weight given to each source when computing an entity's confidence /
# risk score -- structured records (CDR, financial, criminal-history) are
# trusted more than free-text NLP extraction, which can mis-attribute a
# relation to the wrong nearby entity in a sentence.
SOURCE_TRUST = {
    "cdr": 1.0,
    "financial": 1.0,
    "criminal_history": 0.95,
    "fir": 0.6,
    "surveillance": 0.55,
    "social_media": 0.4,
    "intel_report": 0.65,
}
