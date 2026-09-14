"""
KNOT6 Case Intelligence / AI Investigation Copilot.

A small, deliberately practical retrieval-augmented pipeline over data the
app already has -- never a general-purpose chatbot, never a call to an LLM
with the whole database dumped in. See each module's docstring:

  llm_provider.py           -- the swappable LLM interface (no app code
                                depends on "Anthropic" specifically)
  retriever.py              -- InvestigationRetriever: entities, graph
                                neighborhoods, evidence, timeline, signals
  context_builder.py        -- InvestigationContextBuilder: turns a
                                retrieval result + conversation history into
                                a compact, citable context block
  conversation_repository.py -- ConversationRepository: per-(investigation,
                                user) conversation memory
  copilot.py                -- InvestigationCopilot: orchestrates intent ->
                                retrieval -> context -> LLM -> validated
                                citations/actions
"""
