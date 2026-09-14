---
name: staged-run
description: Use to run an ordered artifact pipeline where each stage reads its predecessor's artifact and produces its own — a validating entry guard admits the run, completed stages drop resume checkpoints, and re-entry resumes from the last completed boundary rather than restarting.
user-invocable: false
---

# staged-run

staged-run runs an ordered artifact pipeline, resuming from any completed boundary.

## Steps

This skill realizes the `pipeline` L1 shape (§4.3). Drive it as follows:

1. **Guard the entry.** Before the first stage runs, validate the entry: confirm the inputs the
   pipeline needs are present and well-formed, and on re-entry `read` the existing checkpoint
   `marker` to learn which stages already completed. The guard admits the run and decides where it
   begins — at the head on a fresh run, or just past the last completed boundary on a resume.
2. **Run the stages in sequence.** Drive the stages in their fixed order; each stage runs only
   after its predecessor has produced its artifact. The order is the contract — never reorder or
   parallelize stages.
3. **Each stage reads, then produces.** Every stage `read`s the predecessor's artifact as its sole
   input and `produce`s its own artifact as output. The artifact handed forward is the only seam
   between stages.
4. **Checkpoint each boundary.** On completing a stage, drop a `checkpoint` `marker` recording the
   boundary reached. The marker is durable: it is what the entry guard reads on re-entry so a
   resumed run skips the completed stages and continues from the last checkpoint instead of
   restarting the pipeline.

Calm imperatives only. Describe the target form; the stages do the work.

## Vocabulary

```relay-vocab
l1-shape: pipeline
l0-deps: sequence, produce, read, checkpoint, marker
acpx-leg-required: false
```
