# Data Injector
You are a QA engineer creating realistic test data for DocuBot.

Data to generate: $ARGUMENTS

Generate these files:

## data\sample_faq.txt
Realistic FAQ for a fictional SaaS called TaskFlow (project management).
20 Q&A pairs: account setup, billing, features, troubleshooting, integrations.
Plain text, clearly formatted.

## data\sample_guide.txt
Product feature guide, 3 pages equivalent.
Getting started, core features, advanced settings, API reference summary.

## data\test_questions.json
{
  "should_answer": [
    {"question": "...", "expected_source": "sample_faq.txt",
     "key_phrase_in_answer": "..."}
  ],  (10 questions IN the documents)
  "should_not_answer": [
    {"question": "...", "reason": "..."}
  ],  (5 questions NOT in the documents)
  "adversarial": [
    {"question": "...", "attack_type": "prompt injection / scope bypass"}
  ]   (5 questions trying to break the bot)
}

## scripts\inject_test_data.py
Script that:
1. Reads sample files from data\
2. POSTs them to http://localhost:8000/api/documents/upload
3. Waits for processing
4. Runs all should_answer questions against /api/chat
5. Prints: correct answers, failed answers, pass rate

Runnable with: python scripts\inject_test_data.py