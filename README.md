# OpenRouter Decisions for Home Assistant

A community integration for evaluating questions with OpenRouter's native Decisions API. Requires **Home Assistant 2026.11.2 or newer**.

This is an experimental integration: the upstream Decisions API is in alpha and may change. Evaluation requests can incur OpenRouter charges. Returned probabilities are model estimates, not guarantees.

## What it does

- Answers yes/no questions (`noul`), chooses among named alternatives (`choice`), and scores ordered levels (`score`).
- Uses the standard `ai_task.evaluate` action.
- Accepts text and JSON data, plus images or PDF files when the selected model supports them.
- Validates the returned answers and probabilities before exposing them to automations.

It uses its own `openrouter_decisions` domain. You can keep the built-in OpenRouter integration for conversations and generation; this integration does not replace it or patch Home Assistant.

## Install

The repository is not in the default Marketplace catalog. On Home Assistant 2026.11.2 or newer:

1. Open **Settings > Marketplace**.
2. Select **Add from link** and enter `https://github.com/sibest19/hass-openrouter-decisions`.
3. Install **OpenRouter Decisions**. Accept the community software notice if prompted.
4. Restart Home Assistant if requested.

Before a release is published, install from the default branch. For beta releases, enable pre-releases in the repository's Marketplace settings.

For manual installation, copy `custom_components/openrouter_decisions` into your Home Assistant configuration's `custom_components` directory and restart.

## Configure

1. Open **Settings > Devices & services > Add integration** and select **OpenRouter Decisions**.
2. Enter an OpenRouter API key. Setup only queries the model catalog; it does not send a paid evaluation.
3. Select a decision model. Before selecting it, check its supported input types on [OpenRouter](https://openrouter.ai/models). Only models advertising Decisions output are offered.

One setup creates one evaluation entity. Add the integration again to configure another model. Use **Reconfigure** to change the key or model. This integration stores its own API key configuration; it does not read credentials from the built-in OpenRouter integration.

## Use

In an automation or script, add the **Evaluate** action. Select your new AI task entity, enter a task name, and supply **State**, **Attachments**, or both. Add named questions and set a **Response variable** to keep the answers.

For **Questions**, a yes/no question can be entered as:

```yaml
delivered:
  type: noul
  instructions: "Has the package arrived?"
```

A `noul` answer is a probability between 0 and 1. A `choice` question uses a mapping of at least two alternative IDs to descriptions. A `score` question uses a list of at least two descriptions ordered from lowest to highest; its score is the probability-weighted average of their zero-based positions.

### YAML action example

Replace `ai_task.decision_model` with the entity created in your installation.

```yaml
action: ai_task.evaluate
data:
  task_name: "Delivery assessment"
  entity_id: ai_task.decision_model
  state: "Your package was left at the front door."
  questions:
    delivered:
      type: noul
      instructions: "Has the package arrived?"
response_variable: evaluation
```

The probability is available as `evaluation.answers.delivered.noul`. Your automation chooses a threshold and what to do next. The entity's state is its last-use timestamp, not the answer itself.

## Limitations and privacy

- Text-only models cannot evaluate attachments. Other models may support images, PDF files, or both. Audio and video attachments are not supported by this integration.
- Home Assistant must resolve attachments to permitted local media. Camera snapshots use the existing media selector.
- Input text and files are sent to OpenRouter and the selected model provider. Check their policies before sending private information.
- Invalid API keys require reauthentication. Models that disappear from the catalog require reconfiguration.
- An API alpha change may require an integration update. Pinning an old integration version cannot preserve an API that the upstream service removes.

## Development and releases

See [CONTRIBUTING.md](CONTRIBUTING.md). CI runs real Home Assistant lifecycle and service tests with mocked OpenRouter HTTP responses; it does not spend API credits.

Releases follow the same review-first approach as [hass-meteoam](https://github.com/sibest19/hass-meteoam): dispatch **Prepare release**, review the draft release PR and notes, mark it ready, verify CI, then merge. **Publish release** creates the tag and GitHub release from the reviewed merge commit. The default channel is beta. No release is published just by pushing code.

## Credits and license

Apache-2.0. Adapted from the Home Assistant OpenRouter work in [PR #186289](https://github.com/home-assistant/core/pull/186289), originally opened by [joostlek](https://github.com/joostlek), and the follow-up validation and Decisions implementation by [sibest19](https://github.com/sibest19). See [NOTICE](NOTICE).

This community integration is not affiliated with or endorsed by OpenRouter or Home Assistant.
