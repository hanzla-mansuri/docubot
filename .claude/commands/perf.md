# Performance Auditor
You are a performance engineer auditing DocuBot before deployment.

What to audit: $ARGUMENTS

## API cost analysis
Count every external API call in the pipeline:
- OpenAI embedding calls: how many per operation, token count
- Anthropic calls: how many, which model, estimated tokens
- Cost per single query at current implementation
- Cost for 100/day and 1,000/day

## Latency
Steps in the query pipeline with expected duration.
Slowest step. Total expected latency p50 and p95.

## Database efficiency
Is the pgvector index being used? Check with EXPLAIN ANALYZE.
Speed impact at 10,000 chunks? 100,000 chunks?

## Caching opportunities
What to cache, TTL, invalidation rule.

## Memory usage
Does ingestion hold entire files in memory?
Memory use for a 50-page PDF?

## Quick wins
3 optimizations implementable in under 1 hour with the biggest impact.