# Repository instructions

This repository contains only the OpenRouter Decisions custom integration.
Use Python 3.14+, async I/O, and Home Assistant's public AI Task contract.
Keep the `openrouter_decisions` domain independent of built-in OpenRouter.
Never patch Home Assistant modules or override built-in services.
Use translated user-facing errors and never log API keys or input attachments.
Run `make lint` and `make test` before committing.
Keep releases human reviewed: prepare a release PR, then publish after merge.
Do not run paid live API calls without explicit authorization.
