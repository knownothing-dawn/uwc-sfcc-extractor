# UWC/SFCC Extractor v1.0

**Release class:** Human-Reviewed Production.

Designed for:

PDF → automated UWC/SFCC extraction → Excel + concise report → human scientific
review → master database.

It is not intended for fully autonomous database import without review.
`database_ready` remains the strict autonomous-import gate; a scientifically useful
paper may instead be `usable_with_review` or `partial`.

## Known limitations

- Overlapping or shared continuous vector paths may require human review.
- Unresolved continuous-trace intervals may be excluded rather than guessed.
- Ambiguous UWC variable basis may remain unknown.
- Derived conversions require verified scientific property roles and specimen applicability.
- Difficult source figures may yield `usable_with_review` or `partial` status.

## Post-v1.0 change policy

Do not modify v1.0 production logic for a single unusual paper unless the failure
is severe and clearly generic, or the same failure class appears repeatedly across
multiple independent papers. Prefer accumulating real-paper evidence in the
[v1.1 backlog](v1.1-backlog.md). This protects the production release from
benchmark overfitting.
