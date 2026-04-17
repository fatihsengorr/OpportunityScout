"""
Wildcatter Mod 1 — ThreadForge Beslemesi

5 disciplined task categories that feed ThreadForge's 3 columns
(Advisory, Platform, Cross-Border Delivery).

Output: weekly single report (~A4, 10-min read) saved to Open Brain at
`projects/threadforge/feed/YYYY-WW`, summary sent to Telegram.

Tasks:
  1. Vertical Expansion — next compliance vertical (MEES, Net Zero, CSRD, ...)
  2. Pilot Hunt — real UK developers with Golden Thread pain points
  3. Delivery Scale — TR engineering capacity for Cross-Border column
  4. Capital Match — active UK PropTech VCs / angel networks
  5. Competition Defense — rivals' moves (Aconex, Procore, Plannerly, ...)

Weekly rotation (from config/threadforge_tasks.yaml):
  Week 1: Tasks 1+5 (strategic)
  Week 2: Tasks 2+3 (operational)
  Week 3: Task 4 (capital)
  Week 4: All tasks (lightweight sweep)
"""

import json
import logging
import yaml
from datetime import datetime
from pathlib import Path
from .llm_router import LLMRouter

logger = logging.getLogger("scout.mode1")

TASKS_PATH = Path("./config/threadforge_tasks.yaml")


class WildcatterMode1:
    """ThreadForge-focused disciplined discovery."""

    def __init__(self, config: dict, knowledge_base, brain_client=None):
        self.config = config
        self.kb = knowledge_base
        self.brain = brain_client
        self.llm = LLMRouter(config)
        self.model = self.llm.get_model('daily')  # Gemini Flash — cheap, with web search
        self.tasks_config = self._load_tasks()

    def _load_tasks(self) -> dict:
        try:
            return yaml.safe_load(TASKS_PATH.read_text(encoding='utf-8'))
        except FileNotFoundError:
            logger.error(f"threadforge_tasks.yaml missing at {TASKS_PATH}")
            return {"tasks": [], "scheduling": {}}

    # ─── Public API ────────────────────────────────────────

    def run_weekly(self, week_number: int = None) -> dict:
        """Execute Mod 1 weekly rotation.

        If week_number is not provided, uses current ISO week mod 4.
        Returns a compiled report dict.
        """
        if week_number is None:
            now = datetime.utcnow()
            week_number = ((now.isocalendar()[1] - 1) % 4) + 1

        # Select tasks for this week
        rotation = self.tasks_config.get('scheduling', {}).get('weekly_rotation', [])
        selected_task_ids = []
        for entry in rotation:
            if entry.get('week') == week_number:
                selected_task_ids = entry.get('tasks', [])
                break
        if not selected_task_ids:
            selected_task_ids = [1, 5]  # Default

        tasks_by_id = {t['id']: t for t in self.tasks_config.get('tasks', [])}
        selected_tasks = [tasks_by_id[tid] for tid in selected_task_ids
                          if tid in tasks_by_id]

        logger.info(
            f"🎯 Mod 1 Week {week_number}: running {len(selected_tasks)} tasks — "
            f"{[t['short'] for t in selected_tasks]}"
        )

        # Run each task
        task_results = []
        for task in selected_tasks:
            try:
                result = self._run_task(task)
                task_results.append(result)
            except Exception as e:
                logger.error(f"Task {task['short']} failed: {e}")
                task_results.append({
                    'task_id': task['id'],
                    'task_name': task['name'],
                    'error': str(e),
                })

        # Compile final report
        report = {
            'mode': 'mod1_threadforge',
            'week_number': week_number,
            'week_label': datetime.utcnow().strftime('%Y-W%V'),
            'tasks_run': len(selected_tasks),
            'task_results': task_results,
            'generated_at': datetime.utcnow().isoformat(),
        }

        # Generate human-readable summary
        report['summary_md'] = self._compile_summary(report)

        # Push to Open Brain if available
        if self.brain:
            self._push_to_brain(report)

        return report

    # ─── Single task execution ─────────────────────────────

    def _run_task(self, task: dict) -> dict:
        """Run one task: executes its search queries, synthesizes findings."""
        task_id = task['id']
        task_name = task['name']
        logger.info(f"🎯 Task {task_id}: {task_name}")

        # Build prompt with search queries and focus
        queries = task.get('search_queries', [])
        query_list = "\n".join(f"- {q}" for q in queries[:5])  # Max 5 searches per task

        prompt = f"""ThreadForge compliance technology şirketi için **{task_name}** görevini yürüt.

GÖREV AÇIKLAMASI:
{task.get('description', '')}

FOCUS:
{task.get('mode_prompt_focus', '')}

Aşağıdaki web aramalarını yap ve bulgularını sentezle:

{query_list}

Her kaynak için:
1. Spesifik şirket/kişi/proje/haber (jenerik ifade yok)
2. Tarih (2025-2026 arası, mümkünse ay)
3. Neden ThreadForge için değerli (1 cümle)

SADECE valid JSON döndür:

{{
  "findings": [
    {{
      "what": "Spesifik bulgu (30-50 kelime)",
      "who": "Şirket/kişi/proje ismi",
      "when": "Tarih / dönem",
      "source_hint": "Nereden geldi (URL değil, kaynak türü)",
      "threadforge_relevance": "Neden önemli (1 cümle)",
      "action_hint": "Fatih'in alacağı aksiyon önerisi (1 cümle)"
    }}
  ],
  "top_signals": [
    "En önemli 1-3 bulgunun ID'si (index olarak)"
  ],
  "overall_assessment": "2-3 cümle — bu hafta bu görev için ThreadForge için stratejik önem"
}}

En az 3, en fazla 8 bulgu döndür. Sadece gerçekten spesifik, aksiyon alınabilir bulgular."""

        # Execute with web search (Gemini has built-in Google Search grounding)
        response = self.llm.create(
            model=self.model,
            max_tokens=3072,
            messages=[{"role": "user", "content": prompt}],
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
        )

        # Gemini returns text directly (Google Search grounds in single call)
        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text += block.text

        parsed = self._parse_json(text)
        if not parsed or 'findings' not in parsed:
            return {
                'task_id': task_id,
                'task_name': task_name,
                'error': 'JSON parse failed',
                'raw_snippet': text[:500],
            }

        return {
            'task_id': task_id,
            'task_name': task_name,
            'task_short': task.get('short', ''),
            'findings': parsed.get('findings', []),
            'top_signals': parsed.get('top_signals', []),
            'overall_assessment': parsed.get('overall_assessment', ''),
        }

    # ─── Report compilation ───────────────────────────────

    def _compile_summary(self, report: dict) -> str:
        """Generate human-readable markdown report."""
        week = report['week_label']
        lines = [
            f"# ThreadForge Feed — Week {week}",
            f"*Mod 1 — ThreadForge-focused feed · {report['tasks_run']} tasks executed*",
            "",
        ]

        for task_result in report.get('task_results', []):
            task_name = task_result.get('task_name', '?')
            if task_result.get('error'):
                lines.append(f"## ⚠️ {task_name}")
                lines.append(f"_Error: {task_result['error']}_")
                continue

            lines.append(f"## {task_name}")
            if task_result.get('overall_assessment'):
                lines.append(f"*{task_result['overall_assessment']}*")
                lines.append("")

            findings = task_result.get('findings', [])
            for i, f in enumerate(findings, 1):
                lines.append(f"**{i}. {f.get('who', '?')}** — {f.get('when', '?')}")
                lines.append(f"   {f.get('what', '')}")
                if f.get('threadforge_relevance'):
                    lines.append(f"   *Neden önemli:* {f['threadforge_relevance']}")
                if f.get('action_hint'):
                    lines.append(f"   *Aksiyon:* {f['action_hint']}")
                lines.append("")

        # Top signals across all tasks
        lines.append("---")
        lines.append("## Öncelikli Aksiyonlar")
        priority_items = []
        for task_result in report.get('task_results', []):
            findings = task_result.get('findings', [])
            top_ids = task_result.get('top_signals', [])
            for tid in top_ids[:2]:
                try:
                    idx = int(tid) if isinstance(tid, (str, int)) else 0
                    if isinstance(idx, str) and idx.isdigit():
                        idx = int(idx)
                    if 0 <= idx < len(findings):
                        f = findings[idx]
                        priority_items.append(
                            f"- [{task_result['task_name']}] **{f.get('who', '?')}**: "
                            f"{f.get('action_hint', f.get('what', ''))[:150]}"
                        )
                except Exception:
                    pass
        if priority_items:
            lines.extend(priority_items[:5])
        else:
            lines.append("_Haftanın net öncelik aksiyonu yok._")

        return "\n".join(lines)

    def _push_to_brain(self, report: dict):
        """Push weekly report to Open Brain."""
        if not self.brain:
            return
        week = report['week_label']
        path = f"projects/threadforge/feed/{week}"
        try:
            import asyncio
            asyncio.create_task(self.brain._ingest({
                "path": path,
                "content": report.get('summary_md', ''),
                "metadata": {
                    "source": "wildcatter_mode1",
                    "week": week,
                    "tasks_run": report.get('tasks_run', 0),
                }
            }))
        except Exception as e:
            logger.warning(f"Brain push failed: {e}")

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        import re
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        start = text.find('{')
        if start >= 0:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i+1])
                        except json.JSONDecodeError:
                            break
        return {}
