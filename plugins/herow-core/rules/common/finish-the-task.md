## Finish the task

A `Stop` hook (`stop-guard.js`) inspects the final message and bounces the turn back when it ends
mid-edit, on an unbalanced code fence, or right after announcing an action you haven't taken
("I'll now…", "Next, I…").

A real blocker is a legitimate stop — say so explicitly and name exactly what you need, so the
guard can tell it apart from an unfinished turn.
