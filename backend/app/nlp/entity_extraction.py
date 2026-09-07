"""
Entity + relation extraction from unstructured text: FIR narratives,
surveillance reports, social-media posts, intelligence summaries.

Pipeline for one document:
  1. spaCy statistical NER -> PERSON, ORG, GPE/LOC candidates
  2. Regex extractors      -> PHONE, VEHICLE, financial identifiers
  3. Sentence-level relation extraction:
       - explicit verb cue ("called", "transferred", "met") maps to a
         typed relation between the two nearest entities in the sentence
       - otherwise, two entities that co-occur in the same sentence get a
         weaker ASSOCIATED_WITH / MENTIONED_WITH edge
  4. Every extracted entity/relation carries `evidence`: the source
     document id + the exact sentence, so an investigator can always
     trace an inference back to the original report (this matters for
     anything that might end up in front of a court).

This is intentionally a strong rule-augmented baseline rather than a
fine-tuned model: it needs no training data or GPU to run, which matters
for a hackathon demo and for a first field deployment where labelled
Indian-crime-report training data won't exist yet. `extract_from_text`
is the single seam a real project would swap for a fine-tuned
transformer / LLM-based extractor later without touching anything
downstream (resolution, graph building, analytics all consume the same
`ExtractedEntity` / `ExtractedRelation` shape).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import spacy
from spacy.language import Language

from app.nlp.patterns import (
    RELATION_VERB_MAP,
    find_account_numbers,
    find_phones,
    find_upi_handles,
    find_vehicles,
)

_NLP: Language | None = None


def get_nlp() -> Language:
    """Lazily load the spaCy pipeline once per process."""
    global _NLP
    if _NLP is None:
        try:
            _NLP = spacy.load("en_core_web_sm")
        except OSError:
            # Model not downloaded (e.g. fresh environment). Fall back to a
            # blank English pipeline with just a sentencizer so regex-based
            # extraction and relation logic still work; PERSON/ORG/GPE
            # recall will be lower until `python -m spacy download
            # en_core_web_sm` is run (see backend/README setup step).
            _NLP = spacy.blank("en")
            _NLP.add_pipe("sentencizer")
    return _NLP


_TYPE_MAP = {
    "PERSON": "PERSON",
    "ORG": "ORGANIZATION",
    "GPE": "LOCATION",
    "LOC": "LOCATION",
    "FAC": "LOCATION",
    "NORP": "ORGANIZATION",  # nationalities / groups -> treat as org/affiliation
}


@dataclass
class ExtractedEntity:
    text: str
    type: str
    sentence: str
    start_char: int = 0


@dataclass
class ExtractedRelation:
    source_text: str
    target_text: str
    type: str
    sentence: str
    confidence: float = 0.6


@dataclass
class ExtractionResult:
    entities: list[ExtractedEntity] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)


def _lemma_relation(sentence_doc) -> str | None:
    for token in sentence_doc:
        if token.pos_ == "VERB":
            rel = RELATION_VERB_MAP.get(token.lemma_.lower())
            if rel:
                return rel
    return None


def extract_from_text(text: str) -> ExtractionResult:
    nlp = get_nlp()
    doc = nlp(text)
    result = ExtractionResult()

    for sent in doc.sents:
        sent_text = sent.text.strip()
        if not sent_text:
            continue

        sentence_entities: list[ExtractedEntity] = []

        # 1. spaCy NER candidates
        for ent in sent.ents:
            mapped = _TYPE_MAP.get(ent.label_)
            if mapped:
                sentence_entities.append(
                    ExtractedEntity(text=ent.text.strip(), type=mapped, sentence=sent_text)
                )

        # 2. Regex-based structured identifiers
        for phone in find_phones(sent_text):
            sentence_entities.append(ExtractedEntity(text=phone, type="PHONE", sentence=sent_text))
        for vehicle in find_vehicles(sent_text):
            sentence_entities.append(ExtractedEntity(text=vehicle, type="VEHICLE", sentence=sent_text))
        for upi in find_upi_handles(sent_text):
            sentence_entities.append(
                ExtractedEntity(text=upi, type="FINANCIAL_ACCOUNT", sentence=sent_text)
            )
        for acct in find_account_numbers(sent_text):
            sentence_entities.append(
                ExtractedEntity(text=acct, type="FINANCIAL_ACCOUNT", sentence=sent_text)
            )

        # de-duplicate within the sentence, preserve order
        seen = set()
        deduped = []
        for e in sentence_entities:
            key = (e.text.lower(), e.type)
            if key not in seen:
                seen.add(key)
                deduped.append(e)
        sentence_entities = deduped
        result.entities.extend(sentence_entities)

        # 3. Relation extraction between every pair in this sentence
        if len(sentence_entities) >= 2:
            verb_relation = _lemma_relation(sent)
            for i in range(len(sentence_entities)):
                for j in range(i + 1, len(sentence_entities)):
                    a, b = sentence_entities[i], sentence_entities[j]
                    if a.text.lower() == b.text.lower():
                        continue
                    rel_type = verb_relation or "ASSOCIATED_WITH"
                    confidence = 0.75 if verb_relation else 0.4
                    result.relations.append(
                        ExtractedRelation(
                            source_text=a.text,
                            target_text=b.text,
                            type=rel_type,
                            sentence=sent_text,
                            confidence=confidence,
                        )
                    )

    return result
