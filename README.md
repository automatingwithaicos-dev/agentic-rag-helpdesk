# Agentic RAG Help Desk Agent

An IT help desk agent that investigates before it answers. Plain RAG retrieves documents once and writes a reply. This agent decides on its own which tools to use. It can search the runbooks, check the user's account and devices, search again with a better query, and open a ticket when a human needs to step in. Every tool call is logged so a technician can audit what it did.

It builds on [Embedding](https://github.com/automatingwithaicos-dev/Embedding), my retrieval-augmented generation (RAG) project, which provides the knowledge base search.

## Example

A real run on `qwen2.5-7b-instruct`, a 7B model running locally in LM Studio:

```
> uv run run.py ask "jsmith can't sign in"

  step 1: get_user_status({"username": "jsmith"})
          -> {"username": "jsmith", "display_name": "Jordan Smith", "department": "Finance", "enabled": true,
              "locked_out": true, "failed_sign_ins_last_hour": 12, "mfa_methods": ["Microsoft Authenticator"], ...}
  step 2: search_knowledge_base({"query": "user account lockout troubleshooting"})
          -> {"passages": [{"source": "password-reset.md", "title": "Password Reset and Account Lockout", "score": 0.762, ...}]}
  step 3: create_ticket({"summary": "High Failed Sign-Ins on Account jsmith (Possible Compromise)", "priority": "high",
              "queue": "Security", "details": "User jsmith has logged 12 failed sign-in attempts in the last hour. This
              exceeds the typical threshold and may indicate a brute force or credential stuffing attempt. Account is
              currently locked out. I recommend immediate review by the security team before any manual action (like
              unlocking) is taken. ..."})
          -> {"created": true, "ticket_id": "TCK-1001", "queue": "Security"}

Jordan Smith's account is currently locked out due to multiple failed sign-in attempts (12 in the last hour).

Because of the high number of failed logins, I have opened a ticket with our Security team for immediate review
as this could indicate an unauthorized attempt on your credentials: TCK-1001. They must review and authorize any
action regarding account unlock or password resets.

According to the runbook `password-reset.md`, repeated lockouts are often caused by old passwords saved on synced
devices (like phones or laptops). Once Security clears this issue, please update your password across all personal
devices that sync email. Do not attempt to sign in again until the Security team has reviewed ticket TCK-1001.
```

Other real runs on the same model:

| Request | What the agent did |
| --- | --- |
| "mgarcia can't get email on her laptop" | Found her laptop noncompliant because BitLocker is off, cited `intune-enrollment.md`, and had her restart to start encryption. No ticket needed. |
| "tnguyen's Windows laptop is blocked from Teams" | Picked the noncompliant laptop out of his two devices (no check-in for 7+ days) and walked him through a Company Portal sync. |
| "rpatel can't log in" | Found the account disabled and opened a Tier 2 ticket, since it can't re-enable accounts itself. |

Testing early versions on small local models is what shaped the guardrails below. One model faked its tool calls and invented ticket numbers, another recommended unlocking an account that looked compromised, and one run looped until it had opened 17 tickets. Each of those is now caught in code. Those runs also showed two gaps that are now fixed: the agent didn't mention that mgarcia has no MFA registered, and it didn't recognize that a disabled account with no license usually means rpatel was offboarded, which needs HR or manager approval before re-enabling.

## How it works

```
request ──► model decides ──► tool call ──► result back to model ──► repeat ──► final answer
                 │                                                    (up to 8 steps)
                 ├── search_knowledge_base   runbook search (embeddings + cosine similarity)
                 ├── get_user_status         account, lockout, MFA, groups, license
                 ├── get_device_compliance   Intune devices and failing policies
                 └── create_ticket           escalate to Tier 2 or Security
```

- **Tool use loop** (`agent/loop.py`): the model receives the tool definitions and returns either a tool call or a final answer. Each tool result goes back to the model, matched to its call, until it answers or reaches the step limit.
- **Read-only by design** (`agent/tools.py`): the agent can look but not touch. It can't unlock accounts, reset passwords, or wipe devices. When a fix needs a change, it opens a ticket with its findings and a recommendation, and a technician makes the change. That keeps a human in charge of anything risky.
- **Guardrails in code, not just the prompt** (`review_answer` in `agent/loop.py`): small local models don't always follow instructions, so every answer is checked before it's shown. If the model mentions a ticket number that `create_ticket` never returned, or skips the Security escalation for an account with 10 or more failed sign-ins in an hour, doesn't mention an account with no MFA, or suggests re-enabling a disabled account without HR or manager approval, the agent sends it back to fix the problem. Invented ticket numbers that survive are removed, and if the model answers without using any tools at all, the answer is withheld. Repeating the same tool call returns the earlier result, only one ticket can be opened per queue per request, and a cap on total tool calls stops a model that gets stuck in a loop.
- **Grounded in procedure**: the system prompt tells the agent to follow the runbooks and cite them by file name, and to send signs of compromise, like unexpected MFA prompts or many failed sign-ins, to the Security queue.
- **Local or cloud model** (`agent/local_client.py`): an adapter translates between the OpenAI-compatible format that local servers use and the format the loop uses, so the same agent runs on Ollama, LM Studio, or the Claude API.
- **Sample data** (`data/mock/directory.json`): four users and their devices stand in for Microsoft Graph and Intune, so the project runs anywhere. In production, each tool would call the real API with a least-privilege, read-only service account.

## Quick start

You need [uv](https://docs.astral.sh/uv/) and, for local use, Ollama or LM Studio running a model that supports tool calling (qwen2.5, llama3.1, or mistral-nemo). No API key is needed.

**1. Install uv** (it installs Python for you, so you don't need to install Python first):

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Mac or Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close and reopen your terminal after installing.

**2. Install the project's dependencies** from the project folder:

```bash
uv sync
```

This creates a `.venv` folder with the right Python version and every package locked to tested versions in `uv.lock`.

**Before you run it, edit `config.ini`.**

Open it in any text editor. Every setting has a comment above it. Most people only change the first three:

| Setting | What to put there |
| --- | --- |
| `provider` | `local` for a model on your machine, `claude` for the Claude API |
| `base_url` | Ollama: `http://localhost:11434/v1`. LM Studio: `http://localhost:1234/v1` |
| `model` | Your model's name exactly as your server lists it. `uv run run.py check` prints the names |
| `docs` | The folder of runbooks to search. Change it to use your own `.md` or `.txt` files |
| `embedding` | `fastembed` for semantic search (one-time 70 MB download) or `tfidf` for keyword search |
| `max_steps` | Most tool calls the agent can make before it stops and suggests a ticket |
| `trace` | `true` shows every tool call the agent makes |

**3. Run it:**

```bash
uv run run.py setup                # build the knowledge base index
uv run run.py check                # confirm your model server is running and the model name matches
uv run run.py ask "jsmith can't sign in"
uv run run.py chat                 # interactive mode
uv run run.py rag "how do I clear stuck print jobs"   # plain RAG with no tools, for comparison
```

If you change `docs` or `embedding`, delete the `index` folder so it rebuilds on the next run.

To use the Claude API instead, set `provider = claude` in `config.ini` and set your key:

```bash
export ANTHROPIC_API_KEY=your-key       # Windows PowerShell: $env:ANTHROPIC_API_KEY="your-key"
```

Smaller local models (7B to 8B) handle the simple cases but sometimes skip a step or pick the wrong tool. A 14B model or larger follows the runbooks more reliably. With `trace = true` you can see exactly what the agent did, which makes it easy to compare models.

Try these requests with the sample users:

| Request | What the agent should find |
| --- | --- |
| "jsmith can't sign in" | Locked out after 12 failed sign-ins, so it escalates to Security |
| "mgarcia can't get email on her laptop" | Laptop is noncompliant because BitLocker is off |
| "tnguyen's Windows laptop is blocked from Teams" | Laptop hasn't checked in for over 7 days |
| "Set up MFA for mgarcia" | She has no MFA methods registered, so it walks through setup |
| "rpatel can't log in" | Account is disabled, so it confirms with a ticket rather than re-enabling |

## Tests

```bash
uv run pytest
```

The agent tests use a scripted fake model, so they run offline with no API key or local server. They check that tools return the right data and handle bad input, that tool results are passed back to the model with the right IDs, that tickets are created, and that the loop stops at its step limit. The RAG tests check chunking, retrieval, and saving and loading the index.

## Project layout

```
run.py          one script to set up and run everything
pyproject.toml  dependencies (uv sync installs them; uv.lock pins exact versions)
config.ini      your settings: model, server, documents
agent/
  tools.py      tool definitions and read-only implementations
  loop.py       tool-use loop, system prompt, audit trail
  local_client.py  adapter for Ollama, LM Studio, and other local servers
  cli.py        ask and chat commands with --trace
rag/            knowledge base search (from the Embedding project)
data/kb/        IT help desk runbooks
data/mock/      sample users and devices
tests/          pytest suites for the RAG layer and the agent
```

## Ideas for next steps

- Replace the sample data with Microsoft Graph and Intune calls through a read-only app registration.
- Create tickets in ConnectWise PSA or ServiceNow instead of in memory.
- Add approval-gated actions, such as unlocking an account only after a technician confirms.
