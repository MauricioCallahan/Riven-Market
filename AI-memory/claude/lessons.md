# Lessons Learned

## ⚖️ GLOBAL RULES
- **Commit Formatting**: Never include `Co-Authored-By` lines; use `type(scope): description`.
- **Task Intent**: The "todo" prefix in a user prompt means "add to `todo.md` only"—do not implement code.
- **Environment**: Always verify available tools (e.g., `pip list`) and package paths before running scripts.
- **Documentation**: Update `lessons.md` and `todo.md` immediately after any correction or task completion.
- **Protocol**: → See CLAUDE.md § SESSION PROTOCOL.

---

## 📜 ARCHIVAL LOG (not prescriptive)
| Date       | What went wrong                                      | Rule to prevent it                                           |
|------------|------------------------------------------------------|--------------------------------------------------------------|
| 2026-03-16 | Didn't read lessons.md/todo.md at session start      | Always follow SESSION START protocol before any work |
| 2026-03-16 | Included Co-Authored-By in commit without asking      | Never add co-author lines to commits — user doesn't want them |
| 2026-03-16 | Didn't update lessons.md after user correction        | Immediately update lessons.md after any correction |
| 2026-03-16 | Implemented code when user said "todo ..."            | "todo" prefix means add to todo.md only — never implement |
| 2026-03-17 | Ran test script directly without verifying imports    | Use `python -m package.module` for internal scripts |
| 2026-03-17 | Assumed `pytest` was available without checking       | Verify tools before assuming availability |
| 2026-03-17 | Didn't update todo.md after completing a task         | Mark tasks complete in todo.md immediately |