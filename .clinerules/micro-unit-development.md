## Brief overview
Guidelines for micro-unit development methodology focused on building real-time systems with strict quality gates and incremental module development.

## Development workflow
- Follow THINK → PLAN_STEP → CODE → TEST cycle for each module
- Never propose more than one module per Act cycle
- Each module must be ≤150 LOC with no external I/O operations
- Prefer pure functions and dataclass structures
- Complete one module fully before moving to the next

## Testing requirements
- Mandatory pytest + hypothesis with ≥25 random property-based test cases
- Achieve ≥90% code coverage on new modules (verified with coverage reports)
- Include comprehensive test suites covering unit, integration, and error scenarios
- Use mock-based testing for external dependencies
- Test async functionality with proper async integration tests

## Code quality standards
- Use comprehensive type hints throughout all code
- Implement extensive docstrings for classes and methods
- Prefer dataclass structures for data modeling
- Include factory functions for easy instantiation
- Implement robust error handling and recovery mechanisms
- Follow clear separation of concerns with modular design

## Real-time system patterns
- Design for sub-2 second latency requirements in streaming systems
- Implement non-blocking operations and concurrent processing
- Include backpressure control and queue management
- Provide health monitoring and performance metrics
- Enable session-based coordination for multi-user scenarios

## Documentation approach
- Create comprehensive technical reports after module completion
- Include architecture diagrams and integration examples
- Document performance characteristics and deployment considerations
- Provide production tuning guidelines and scaling recommendations
- Include future enhancement roadmaps

## Module integration strategy
- Build integration layers that coordinate multiple modules
- Enable pipeline parallelization for performance optimization
- Implement comprehensive statistics aggregation across components
- Design for production deployment with monitoring capabilities
