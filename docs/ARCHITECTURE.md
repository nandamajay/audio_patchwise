# PatchWise Architecture

## 1. A2A Design Pattern
PatchWise uses a critic-actor loop where CHANAKYA critiques and ARYABHATA applies fixes. This pattern reduces hallucinated code changes by requiring each round to be validated by a dedicated reviewer persona.

## 2. CHANAKYA Responsibilities
- Parse raw patches and file hunks
- Detect style, logic, memory safety, LKML, and commit message issues
- Retrieve similar historical patches from LKML/Gerrit/local KB
- Produce structured findings with severity and actionable guidance
- Set round verdict and quality score

## 3. ARYABHATA Responsibilities
- Consume all CHANAKYA findings per round
- Apply deterministic one-pass fixes to current patch candidate
- Emit inline fix summaries and detailed justification cards
- Update patch artifact and increment current round

## 4. LangGraph State Machine
Nodes:
- `chanakya_review`
- `aryabhata_fix`

Edges:
- Entry at `chanakya_review`
- Conditional edge from `chanakya_review` to `aryabhata_fix` or `END`
- Back edge `aryabhata_fix -> chanakya_review`

Condition:
- End when verdict is `LGTM` or `current_round >= max_rounds`

## 5. PatchWise Skill Sub-skills
- Kernel style checker (`tabs`, line width)
- Logic checker (`TODO`, suspicious condition patterns)
- Memory safety checker (`kmalloc/kzalloc` null handling)
- LKML compliance checker (DCO trailers)
- Commit message checker (subject quality and fix trailers)

## 6. Knowledge Base Design
### ChromaDB
Collection: `patchwise_alsa_asoc`.
Document schema:
- `patch_id`
- `title`
- `author`
- `date`
- `subsystem`
- `verdict`
- `url`
- `content`

### SQLite
Tables:
- `patch_sessions`
- `review_findings`
- `fix_patterns`
- `similar_patch_refs`
- `sessions` (session snapshot persistence)

## 7. WebSocket Streaming
Endpoint: `/ws/agent-stream/{session_id}`

Message schema:
```json
{
  "agent": "chanakya | aryabhata | system",
  "type": "thinking | finding | fix | justification | similar_patch | verdict | lgtm | session_paused | session_resumed",
  "round": 1,
  "content": "token or message",
  "metadata": {}
}
```

## 8. Session Lifecycle
1. User submits patch + context + config
2. Session snapshot persisted
3. Graph executes round loop with live streaming
4. User can soft-interrupt with hint and resume
5. Final report and patch are stored
6. Optional submission to GitHub/Gerrit/Upstream
7. Learning artifacts fed into ChromaDB + SQLite
