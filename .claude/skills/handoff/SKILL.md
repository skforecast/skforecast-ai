---
name: handoff
description: Write a handoff document in dev/ so the work can continue in another session (cloud to local, local to cloud, or a later session).
disable-model-invocation: true
argument-hint: "<topic slug>"
---

# Handoff

Write `dev/$ARGUMENTS.md` (ask for a slug if none was given) following the
structure of `dev/mcp-preparation.md`, in the language of the conversation:

1. Title and one line of state: date, branch, whether the changes are
   committed (and on which branch) or in the working tree.
2. Goal and decisions: what we are trying to achieve and why each
   non-obvious decision was taken, including the options discarded.
3. Done: grouped by topic, with the public names and files that changed,
   and whether each block has tests and a release note.
4. Pending: for the author (review, commit, real-model runs) and for the
   next session, in order, each item concrete enough to start without
   rereading this conversation.
5. Environment and verification: the exact commands to check the state
   (from `/verify`), and the result at the end of this session (test count,
   lint).

Keep it factual and short; link to files instead of copying code. Do not
commit it unless asked (in a cloud session it goes into the session branch
with the rest of the work).
