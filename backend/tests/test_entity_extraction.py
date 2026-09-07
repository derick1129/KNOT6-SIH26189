from app.nlp.entity_extraction import extract_from_text
from app.nlp.patterns import find_phones, find_vehicles


def test_finds_phone_numbers():
    text = "The suspect was contacted on 9876543210 and also uses +91 98234 56781."
    phones = find_phones(text)
    assert "9876543210" in phones
    assert "9823456781" in phones


def test_finds_vehicle_plates():
    text = "He was driving MP09AB1234 near the market."
    assert "MP09AB1234" in find_vehicles(text)


def test_extracts_person_and_relation():
    text = "Vikram Rathore called Ramesh Kumar near Bhawarkuan Chowk."
    result = extract_from_text(text)
    entity_texts = {e.text for e in result.entities}
    assert "Vikram Rathore" in entity_texts
    assert "Ramesh Kumar" in entity_texts
    # A "called" cue should produce a CALLED relation between the two people
    call_relations = [r for r in result.relations if r.type == "CALLED"]
    assert any(
        {r.source_text, r.target_text} == {"Vikram Rathore", "Ramesh Kumar"} for r in call_relations
    )


def test_every_entity_carries_evidence_sentence():
    text = "Suresh Yadav transferred funds to Anita Deshmukh in Rau Indore."
    result = extract_from_text(text)
    assert all(e.sentence for e in result.entities)
