# Micro-Unit Rules (R&D Transparency)

## Iteration policy
- Never propose more than **one module** per Act cycle.
- Each module **≤ 150 LOC**; no external I/O; pure functions preferred.
- Mandatory tests:
  - pytest + hypothesis, ≥ 25 random cases
  - coverage ≥ 90 % on the new file


## Approved cycle  (THINK → PLAN_STEP → CODE → TEST)
1. **THINK**: you (human) jot down intent and constraints.
2. **PLAN_STEP**: Cline drafts roadmap for *one* file + its tests.
3. You approve.
4. **CODE** (Act mode): Cline writes code & tests.
5. **TEST**: Cline runs pytest; must pass coverage gate.
6. Loop to step 1 for the next module.


## Documentation approach
- Create comprehensive technical reports after module completion
- Include architecture diagrams and integration examples
- Document performance characteristics and deployment considerations
- Provide production tuning guidelines and scaling recommendations
- Include future enhancement roadmaps