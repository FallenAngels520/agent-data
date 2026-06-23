# Cross Verification

## Purpose

Cross verification turns weak sources, such as X, Reddit, Hacker News, or unknown blogs, into reviewable multi-source evidence. It does not make a social post authoritative by itself. It checks whether factual claims from the original source are also supported by an independent linked source.

## Current Pipeline

The single-document pipeline now runs:

```text
source -> parse -> extract -> evidence -> gates -> quality_profile
       -> cross_verification -> score -> export
```

Cross verification runs when `quality_profile.source_trust.requires_cross_verification` is true.

## MVP Behavior

1. Discover candidate URLs from Markdown links and raw URLs in the parsed document.
2. Filter known navigation and authentication noise, including X home, login, signup, terms, privacy, onboarding links, profile links, and image/CDN assets such as `pbs.twimg.com`.
3. Resolve each candidate URL through the existing `SourceResolver`.
4. Parse the candidate source through the existing parser registry.
5. Reuse the deterministic `EvidenceVerifier` to check whether verified fact claims are present in the candidate source.
6. Mark the result:
   - `not_required`: source policy does not require cross verification.
   - `not_attempted`: no verified fact claims or no candidate links.
   - `supported`: all verified fact claims are supported by at least one independent candidate source.
   - `insufficient`: candidates were checked but did not support all fact claims.
   - `failed`: all candidate checks failed technically.

## Storage Policy

For X and other C-tier social sources:

- Without support: keep `store_target=signal_pool`.
- With independent support: upgrade to `store_target=verified_knowledge_base`.
- Keep `agent_ready=false` because the original source remains a signal source.
- Use soft claim gates: ungrounded or unstable social claims are preserved in `claim_results` for review, but they do not reject the whole package when the source already requires cross verification.

This avoids treating X as a fact source while still preserving useful leads when an official or authoritative linked source confirms them.

## Social Source Notes

X pages often include navigation, login, signup, legal, profile, image, and engagement-count text. The extractor prompt tells the model not to emit view counts, reply counts, repost counts, likes, bookmarks, login prompts, signup prompts, or terms/privacy links as fact claims. Candidate discovery skips X profile links and media assets, while preserving `x.com/i/article/...` article links for review. The deterministic gate still treats such sources as `needs_review`, not `ready`.

## Current Limits

The MVP only verifies linked sources already present in the parsed document. It does not yet search the web, expand `t.co` beyond what source resolution exposes, detect semantic paraphrases, compare conflicting claims, or aggregate multiple social/community mentions. Those should be added as separate discovery and topic-package capabilities.
