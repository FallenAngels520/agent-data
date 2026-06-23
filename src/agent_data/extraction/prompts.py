SYSTEM_PROMPT = """You extract grounded knowledge from document blocks.
Return one JSON object using exactly this shape and no additional fields:
{
  "summary": "string",
  "key_points": ["string"],
  "claims": [
    {
      "text": "string",
      "claim_type": "fact|opinion|prediction|instruction|derived",
      "confidence": 0.0,
      "quote": "exact source text",
      "candidate_block_id": "source block_id"
    }
  ],
  "entities": ["string"],
  "topics": ["string"],
  "tags": ["string"],
  "relevance": null,
  "actionability": null
}
Every claim must quote source text exactly and use an existing candidate_block_id.
For every fact claim, text MUST be byte-for-byte identical to quote.
Do not correct OCR, spelling, punctuation, or whitespace in fact claim text.
Do not invent evidence or block identifiers. Confidence is in [0, 1].
When task_context is provided, relevance and actionability must be numbers in [0, 1].
Without task_context, relevance and actionability must be null."""

PROMPT_VERSION = "extract-v1"
