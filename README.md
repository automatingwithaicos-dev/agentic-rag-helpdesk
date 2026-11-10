# Agentic RAG Help Desk Agent

An IT help desk agent that investigates before it answers. Plain RAG retrieves documents once and writes a reply. This agent decides on its own which tools to use. It can search the runbooks, check the user's account and devices, search again with a better query, and open a ticket when a human needs to step in. Every tool call is logged so a technician can audit what it did.

It builds on [Embedding](https://github.com/automatingwithaicos-dev/Embedding), my retrieval-augmented generation (RAG) project, which provides the knowledge base search.

## Example

```
$ python -m agent ask "jsmith says she can't sign in to anything" --trace

  step 1: get_user_status({"username": "jsmith"})
          -> {"locked_out": true, "failed_sign_ins_last_hour": 12, "mfa_methods": ["Microsoft Authenticator"], ...}
  step 2: search_knowledge_base({"query": "account lockout repeated failed sign-ins"})
          -> {"passages": [{"source": "password-reset.md", ...}]}
  step 3: create_ticket({"summary": "jsmith locked out after 12 failed sign-ins", "queue": "Security", "priority": "high", ...})
          -> {"created": true, "ticket_id": "TCK-1001"}

Your account is locked after 12 failed sign-ins in the last hour. That many attempts can come from an
old password saved on a phone, but it can also be someone guessing your password, so I've opened
TCK-1001 with Security. Until they follow up, update your password on any phone or tablet that syncs
email (password-reset.md).
```

The answer above illustrates the flow. The agent's exact wording varies from run to run.

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
- **Grounded in procedure**: the system prompt tells the agent to follow the runbooks and cite them by file name, and to send signs of compromise, like unexpected MFA prompts or many failed sign-ins, to the Security queue.
- **Local or cloud model** (`agent/local_client.py`): an adapter translates between the OpenAI-compatible format that local servers use and the format the loop uses, so the same agent runs on Ollama, LM Studio, or the Claude API.
- **Sample data** (`data/mock/directory.json`): four users and their devices stand in for Microsoft Graph and Intune, so the project runs anywhere. In production, each tool would call the real API with a least-privilege, read-only service account.

## Quick start

The agent runs on a **local model by default**, so it needs no API key and no data leaves your machine. Any OpenAI-compatible local server works: Ollama, LM Studio, llama.cpp, or vLLM.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m rag ingest             # build the knowledge base index
```

**Local model with Ollama (default):**

```bash
ollama pull qwen2.5:7b           # any model with tool calling works: qwen2.5, llama3.1, mistral-nemo
python -m agent ask "mgarcia can't get email on her laptop" --trace
python -m agent chat --trace
```

**Local model with LM Studio:** load a tool-calling model, start the server, then:

```bash
python -m agent ask "jsmith can't sign in" --trace --base-url http://localhost:1234/v1 --model <model name in LM Studio>
```

**Claude API instead:**

```bash
export ANTHROPIC_API_KEY=your-key
python -m agent ask "jsmith can't sign in" --trace --provider claude
```

Smaller local models (7B to 8B) handle the simple cases well but sometimes skip a step or pick the wrong tool. A 14B model or larger follows the runbooks more reliably. The `--trace` flag shows exactly what the agent did, which makes it easy to compare models.

Try these with the sample users:

| Request | What the agent should find |
| --- | --- |
| "jsmith can't sign in" | Locked out after 12 failed sign-ins, so it escalates to Security |
| "mgarcia can't get email on her laptop" | Laptop is noncompliant because BitLocker is off |
| "tnguyen's Windows laptop is blocked from Teams" | Laptop hasn't checked in for over 7 days |
| "Set up MFA for mgarcia" | She has no MFA methods registered, so it walks through setup |
| "rpatel can't log in" | Account is disabled, so it confirms with a ticket rather than re-enabling |

## Tests

```bash
pytest
```

The agent tests use a scripted fake model, so they run offline with no API key or local server. They check that tools return the right data and handle bad input, that tool results are passed back to the model with the right IDs, that tickets are created, and that the loop stops at its step limit. The RAG tests check chunking, retrieval, and saving and loading the index.

## Project layout

```
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
