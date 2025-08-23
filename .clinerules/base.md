# Micro-Unit Rules

## Iteration policy
- Never propose more than **one module** per Act cycle.
- Each module **≤ 150 LOC**; pure functions preferred.
- Mandatory tests:
  - pytest + hypothesis, ≥ 25 random cases
  - coverage ≥ 90 % on the new file
- Never use mock-based testing

## Development workflow
## Follow THINK → PLAN_STEP → CODE → TEST cycle for each module
1. **THINK**:  Cline and User figure out intent and constraints.
2. **PLAN_STEP**: Cline drafts roadmap for *one* file + its tests.
3. **CODE** (Act mode): Cline writes code & tests.
4. **TEST**: Cline runs pytest; must pass coverage gate.
5. Loop to step 1 for the next module.

## Documentation approach
- Create comprehensive technical reports after module completion
- Include architecture diagrams and integration examples
- Document performance characteristics and deployment considerations
- Provide production tuning guidelines and scaling recommendations