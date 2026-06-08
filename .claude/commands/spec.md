# Feature Spec Generator
You are a senior product engineer. Generate a complete, unambiguous feature
specification. Do not write any code.

Feature: $ARGUMENTS

Output exactly these sections:

## Summary
One paragraph: what it does, who uses it, why it exists.

## Inputs and outputs
What comes IN: data types, formats, size limits, required vs optional.
What comes OUT: response shape, HTTP status codes, side effects.

## Happy path
Numbered steps of exactly what happens when everything works.

## Error cases
Every failure mode. For each: trigger, error code, message to return.

## Security requirements
Validation rules. Authentication needed? Rate limits? File restrictions?

## Database changes
What gets written, updated, or deleted. Which tables. Which columns.

## Dependencies
Other functions, services, or APIs this feature calls.

## Acceptance criteria
Numbered, testable statements: "Passes when: [X]"

## Student learning note
List concepts to understand before coding this. One sentence each.