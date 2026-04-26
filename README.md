# claude-mnemos

Long-term structured per-project knowledge base for Claude Code sessions.

Преемник [LLM Wiki Control Panel](../OBSIDIAN/.shared/). Самостоятельный проект, не Obsidian-companion.

## Статус

`0.0.1` — bootstrap. Кода ещё нет, идёт минимальный e2e «1 чат → 1 страница».

## Запуск тестов

```bash
pip install -e ".[dev]"
pytest
```

## Структура

```
claude_mnemos/
  core/      # примитивы: locks, atomic_write, frontmatter
  state/     # state-файлы и их инварианты
  ingest/    # pipeline ингеста чатов в vault
  wiki/      # модель vault'а (страницы, wikilinks)
tests/
```
