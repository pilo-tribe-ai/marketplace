# OSAAT (One Step At A Time)

Execute any series of steps one at a time with explicit confirmation between each step.

## Quick Start

```bash
# Install from LFA marketplace
claude plugin install osaat@lfa

# Use the skill
"Execute these database migrations one step at a time"
"Walk me through this refactoring step-by-step with confirmation"
```

## Overview

OSAAT provides a controlled execution mode where Claude breaks down complex tasks into individual steps and waits for your confirmation before executing each one. This gives you maximum visibility and control over the process.

## When to Use

- **Critical Operations**: When performing operations that require careful oversight
- **Learning Mode**: When you want to understand a complex process step-by-step
- **Decision Points**: When you need to make decisions between steps based on intermediate results
- **Risk Management**: When you want the ability to stop or modify the process at any point

## How It Works

1. **Task Breakdown**: Claude analyzes your request and breaks it into discrete, atomic steps
2. **Step Presentation**: Each step is clearly described before execution
3. **User Confirmation**: Claude waits for your approval before executing
4. **Result Display**: The outcome of each step is shown
5. **Next Step**: Process continues with the next step upon confirmation

## Examples

### Database Migration

```
User: "Execute these database migrations one step at a time"

Claude: "I'll execute the migrations with confirmation at each step.

Step 1/5: Create backup of current database
Ready to execute? [y/n]"
```

### Code Refactoring

```
User: "Refactor the authentication module step-by-step"

Claude: "I'll break down this refactoring into steps:

Step 1/4: Extract authentication logic into separate service
This will:
- Create new AuthService class
- Move validateToken() and refreshToken() methods
- Update imports in affected files

Ready to execute? [y/n]"
```

### Infrastructure Setup

```
User: "Set up the CI/CD pipeline one step at a time"

Claude: "I'll set up the pipeline with confirmation at each step.

Step 1/6: Create .github/workflows directory
Ready to execute? [y/n]"
```

## Features

- **Explicit Control**: Nothing executes without your confirmation
- **Clear Communication**: Each step is described in detail before execution
- **Flexible Pacing**: Take time to review, ask questions, or modify the approach
- **Early Exit**: Stop the process at any point if needed
- **Learning Opportunity**: Understand complex operations by seeing them decomposed

## Best Practices

1. **Use for Complex Tasks**: Most beneficial for multi-step operations
2. **Review Carefully**: Read the step description before confirming
3. **Ask Questions**: If a step is unclear, ask for clarification before confirming
4. **Verify Results**: Check the output of each step before proceeding
5. **Save Progress**: For long processes, results are preserved between steps

## Contributing

Contributions welcome! Please visit our [GitHub repository](https://github.com/lamadeo/lfa-cc-marketplace) to report issues or submit pull requests.

## License

MIT © LFA
